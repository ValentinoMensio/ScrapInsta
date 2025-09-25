import time
import itertools
import threading
import heapq
import random
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from queue import Queue  # Evitar import circular

from core.worker.messages import (
    TASK_FETCH_FOLLOWINGS, TASK_ANALYZE, TASK_SEND_MESSAGE,
    RES_ERROR, RES_FOLLOWINGS_FETCHED, RES_MESSAGE_SENT, RES_PROFILE_ANALYZED
)


# =========================
#   CONFIGURACIÓN TUNABLE
# =========================
MAX_INFLIGHT_PER_ACCT = 2

# Backoff
MAX_BACKOFF_S = 15 * 60     # 15 min cap
BASE_BACKOFF_S = 15         # primer backoff
JITTER_S = 5

# Aging (anti-starvation)
AGING_STEP = 0.05           # cuánto sube la urgencia por ciclo
AGING_CAP = 1.0

# Observabilidad
ROUTER_LOG_JSON = False     # si True, imprime stats periódicamente en JSON


@dataclass(order=True)
class PrioritizedJobRef:
    priority: int
    created_at: float
    job_id: str=field(compare=False)


@dataclass
class Job:
    job_id: str
    kind: str                  # 'fetch_followings' | 'analyze' | 'send_message'
    items: List[str]
    batch_size: int = 25
    pending: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    done: bool = False
    extra: Optional[dict] = None

    dispatched: int = 0
    completed: int = 0
    errors: int = 0

    # NUEVO: prioridad (1 = más alto, 10 = bajo)
    priority: int = 5

    def __post_init__(self):
        if not self.pending:
            self.pending = set(self.items)


class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = capacity
        self.last = time.time()

    def _refill(self):
        now = time.time()
        elapsed = now - self.last
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.last = now

    def has(self, n: int = 1) -> bool:
        """Chequea si hay tokens suficientes (no consume)."""
        self._refill()
        return self.tokens >= n

    def consume(self, n: int = 1) -> bool:
        """Consume tokens si hay disponibles."""
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    # Backward-compat, por si se usa en otro lado
    def allow(self, n: int = 1) -> bool:
        return self.consume(n)


def _now() -> float:
    return time.time()


class Router:
    """
    Reparte tareas entre cuentas disponibles.
    - Token bucket por cuenta (rate-limit "suave").
    - Backoff/circuit-breaker por cuenta si hay errores repetidos.
    - Límite de in-flight por cuenta.
    - Anti-starvation con "aging" de urgencia.
    - Prioridades de jobs (min-heap por prioridad + created_at).
    - Mantiene mapping task_id -> (account, username, job_id, start_time).
    - Thread-safe con locks para operaciones críticas.
    - Observabilidad con métricas y shutdown limpio.
    """
    def __init__(self, accounts: List[dict], worker_queues: Dict[str, "Queue"]):
        # Validar entrada
        if not accounts:
            raise ValueError("No se proporcionaron cuentas")
        for account in accounts:
            if not isinstance(account, dict) or 'username' not in account:
                raise ValueError(f"Cuenta inválida: {account}")
            if not account['username'] or not isinstance(account['username'], str):
                raise ValueError(f"Username inválido en cuenta: {account}")
        if not worker_queues:
            raise ValueError("No se proporcionaron colas de workers")

        self.accounts = accounts
        self.worker_queues = worker_queues

        # Estado por cuenta
        self.inflight: Dict[str, int] = {a["username"]: 0 for a in accounts}
        self.limiters: Dict[str, TokenBucket] = {
            a["username"]: TokenBucket(capacity=60, refill_per_sec=1.0)  # ~60 tareas/min
            for a in accounts
        }
        self._rr = itertools.cycle([a["username"] for a in accounts])

        # Backoff state
        self.account_state = defaultdict(lambda: {"error_count": 0, "cooldown_until": 0.0})

        # Urgencia por cuenta (anti-starvation)
        self.urgency = defaultdict(float)

        # Métricas por cuenta (latencia/ratio ok) — ganchos para futuro auto-tuning de batch
        self.acct_metrics = defaultdict(lambda: {"rt_avg": 3.0, "ok_ratio": 1.0})

        self.jobs: Dict[str, Job] = {}
        self._job_heap: List[PrioritizedJobRef] = []  # prioridad global de jobs

        # task_id -> {account, username, job_id, start_time}
        self.task_map: Dict[str, Dict[str, Any]] = {}

        # Control de ciclo
        self._lock = threading.Lock()
        self._stopping = False

        # Cache de usernames (lista para iterar rápido)
        self._all_accounts = [a["username"] for a in accounts]

    # ---------------
    #   UTILIDADES
    # ---------------
    def _is_account_available(self, acct: str) -> bool:
        return _now() >= self.account_state[acct]["cooldown_until"]

    def _mark_account_error(self, acct: str):
        st = self.account_state[acct]
        st["error_count"] += 1
        backoff = min(MAX_BACKOFF_S, BASE_BACKOFF_S * (2 ** (st["error_count"] - 1)))
        jitter = random.uniform(0, JITTER_S)
        st["cooldown_until"] = _now() + backoff + jitter

    def _mark_account_ok(self, acct: str):
        st = self.account_state[acct]
        st["error_count"] = 0
        st["cooldown_until"] = 0.0

    def _age_all_accounts(self):
        for acct in self._all_accounts:
            self.urgency[acct] = min(AGING_CAP, self.urgency[acct] + AGING_STEP)

    def _pick_account(self) -> Optional[str]:
        """
        Elige la cuenta disponible según:
        - Disponible (sin cooldown) y con tokens y con in-flight < MAX_INFLIGHT_PER_ACCT
        - Score = (1 - inflight) + urgency + (tokens * 0.1)
        Se consume 1 token de la cuenta elegida.
        """
        tried = set()
        candidates: List[str] = []

        for _ in range(len(self.accounts)):
            acc = next(self._rr)
            if acc in tried:
                continue
            tried.add(acc)

            if (self._is_account_available(acc) and
                self.inflight.get(acc, 0) < MAX_INFLIGHT_PER_ACCT and
                self.limiters[acc].has(1)):
                candidates.append(acc)

        if not candidates:
            return None

        # Elegir por mejor score (anti-starvation + fairness)
        def _score(a: str) -> float:
            return (1.0 - float(self.inflight.get(a, 0))) + self.urgency[a] + (self.limiters[a].tokens * 0.1)

        best = max(candidates, key=_score)

        # Consumir token y resetear su urgencia (fue atendida)
        if self.limiters[best].consume(1):
            self.urgency[best] = 0.0
            return best
        return None

    def _task_type_for(self, job: Job) -> str:
        if job.kind == 'fetch_followings':
            return TASK_FETCH_FOLLOWINGS
        if job.kind == 'analyze':
            return TASK_ANALYZE
        if job.kind == 'send_message':
            return TASK_SEND_MESSAGE
        raise ValueError(f"Tipo de job desconocido: {job.kind}")

    def _enqueue_job_ref(self, job: Job):
        """Empuja/actualiza referencia del job en el heap de prioridades."""
        heapq.heappush(self._job_heap, PrioritizedJobRef(priority=job.priority, created_at=job.created_at, job_id=job.job_id))

    # ----------------
    #   API DE JOBS
    # ----------------
    def add_job(self, job: Job):
        with self._lock:
            self.jobs[job.job_id] = job
            self._enqueue_job_ref(job)

    # ----------------
    #   DISPATCH LOOP
    # ----------------
    def dispatch(self):
        """Intenta despachar hasta un batch por job (respetando prioridad y aging)."""
        with self._lock:
            if self._stopping:
                return  # no aceptar nuevos envíos si estamos apagando

            # Anti-starvation: sube urgencia de todas
            self._age_all_accounts()

            # Preparar una vista de jobs activos en heap (evitar referencias a jobs ya done)
            # Reinyectar los que no están done y siguen con pending
            temp_heap: List[PrioritizedJobRef] = []
            seen = set()
            while self._job_heap:
                jref = heapq.heappop(self._job_heap)
                if jref.job_id in seen:
                    continue
                seen.add(jref.job_id)
                job = self.jobs.get(jref.job_id)
                if job and not job.done and job.pending:
                    heapq.heappush(temp_heap, jref)
            self._job_heap = temp_heap

            # Recorremos por prioridad (min-heap)
            # Para no quedarnos clavados en el primer job, iteramos como round over heap snapshot
            heap_snapshot = list(self._job_heap)
            heapq.heapify(heap_snapshot)

            # Intentar un ciclo donde cada job activo recibe algo de atención
            # (si hay cuentas disponibles)
            while heap_snapshot:
                jref = heapq.heappop(heap_snapshot)
                job = self.jobs.get(jref.job_id)
                if not job or job.done or not job.pending:
                    continue

                dispatched = 0
                to_send = list(itertools.islice(iter(job.pending), job.batch_size))
                for username in to_send:
                    account = self._pick_account()
                    if not account:
                        break  # sin cuentas aptas ahora; seguimos con otro job o salimos

                    task_id = f"{job.job_id}:{job.kind}:{username}"
                    task = {
                        "id": task_id,
                        "type": self._task_type_for(job),
                        "profile": username,
                    }
                    if job.extra:
                        task.update(job.extra)

                    # Enviar tarea a la cola del worker de la cuenta
                    self.worker_queues[account].put(task)

                    # Bookkeeping
                    self.task_map[task_id] = {
                        "account": account,
                        "username": username,
                        "job_id": job.job_id,
                        "start_time": _now()
                    }
                    self.inflight[account] = self.inflight.get(account, 0) + 1
                    job.pending.discard(username)
                    job.dispatched += 1
                    dispatched += 1

                # Si ya no quedan pendientes y no hay inflights de este job, marcar done
                if not job.pending:
                    still = any(m.get("job_id") == job.job_id for m in self.task_map.values())
                    job.done = not still

                # Reinyectar el job al heap principal si sigue activo
                if not job.done and job.pending:
                    self._enqueue_job_ref(job)

                # Si no hay más cuentas aptas en este momento, podemos cortar
                if not any(self._is_account_available(a)
                           and self.inflight.get(a, 0) < MAX_INFLIGHT_PER_ACCT
                           and self.limiters[a].has(1) for a in self._all_accounts):
                    break

            if ROUTER_LOG_JSON:
                print(json.dumps({"router_stats": self.get_stats()}, ensure_ascii=False))

    # --------------
    #   ON RESULT
    # --------------
    def on_result(self, result: dict):
        """
        Llamar con cada mensaje del result_queue.
        Actualiza inflight, backoff, métricas y estado de jobs.
        Thread-safe con locks.
        """
        with self._lock:
            task_id = result.get("task_id")
            rtype = result.get("type")
            ok = rtype in (RES_FOLLOWINGS_FETCHED, RES_PROFILE_ANALYZED, RES_MESSAGE_SENT)

            meta = None
            if task_id and task_id in self.task_map:
                meta = self.task_map.pop(task_id)
                acc = meta["account"]
                self.inflight[acc] = max(0, self.inflight.get(acc, 0) - 1)

                # Métricas de latencia/éxito por cuenta
                start = meta.get("start_time")
                if start:
                    rt = max(0.0, _now() - start)
                else:
                    rt = 0.0

                # Update metrics
                m = self.acct_metrics[acc]
                m["rt_avg"] = (m["rt_avg"] * 0.8) + (rt * 0.2)
                m["ok_ratio"] = (m["ok_ratio"] * 0.9) + ((1.0 if ok else 0.0) * 0.1)

                # Backoff reset/raise
                if ok:
                    self._mark_account_ok(acc)
                else:
                    self._mark_account_error(acc)

            # Detectar fin del job usando el job_id
            job_id = None
            if meta:
                job_id = meta.get("job_id")
            elif task_id:
                parts = task_id.split(":", 2)
                if len(parts) >= 1:
                    job_id = parts[0]

            if job_id and job_id in self.jobs:
                job = self.jobs[job_id]
                if rtype == RES_ERROR:
                    job.errors += 1
                elif ok:
                    job.completed += 1

                if not job.pending:
                    still = any(m.get("job_id") == job_id for m in self.task_map.values())
                    if not still:
                        job.done = True

    # --------------
    #   STATS / KPIs
    # --------------
    def all_done(self) -> bool:
        return all(j.done for j in self.jobs.values())

    def kpis(self) -> Dict[str, dict]:
        """
        KPIs agregados por tipo de job y totales.
        """
        by_kind: Dict[str, dict] = {}
        total = {"dispatched": 0, "completed": 0, "errors": 0, "jobs": 0}

        for j in self.jobs.values():
            k = j.kind
            if k not in by_kind:
                by_kind[k] = {"dispatched": 0, "completed": 0, "errors": 0, "jobs": 0}
            by_kind[k]["dispatched"] += j.dispatched
            by_kind[k]["completed"] += j.completed
            by_kind[k]["errors"] += j.errors
            by_kind[k]["jobs"] += 1

            total["dispatched"] += j.dispatched
            total["completed"] += j.completed
            total["errors"] += j.errors
            total["jobs"] += 1

        return {"by_kind": by_kind, "total": total}

    def get_stats(self) -> Dict[str, Any]:
        """
        Estado detallado del router para observabilidad/monitoreo.
        """
        return {
            "ts": _now(),
            "accounts": {
                a: {
                    "tokens": round(self.limiters[a].tokens, 2),
                    "inflight": self.inflight[a],
                    "cooldown_until": self.account_state[a]["cooldown_until"],
                    "error_count": self.account_state[a]["error_count"],
                    "rt_avg": round(self.acct_metrics[a]["rt_avg"], 3),
                    "ok_ratio": round(self.acct_metrics[a]["ok_ratio"], 3),
                    "urgency": round(self.urgency[a], 2),
                }
                for a in self._all_accounts
            },
            "jobs": {
                j.job_id: {
                    "kind": j.kind,
                    "priority": j.priority,
                    "pending": len(j.pending),
                    "dispatched": j.dispatched,
                    "completed": j.completed,
                    "errors": j.errors,
                    "done": j.done,
                } for j in self.jobs.values()
            },
            "inflight_total": sum(self.inflight.values()),
            "task_map_size": len(self.task_map),
            "queue_jobs": len(self._job_heap),
        }

    # --------------
    #   SHUTDOWN
    # --------------
    def stop_accepting(self):
        """No aceptar nuevos envíos (permite drenar inflights)."""
        with self._lock:
            self._stopping = True

    def can_accept_new_jobs(self) -> bool:
        return not self._stopping

    def drain_and_shutdown(self, timeout_s: int = 60):
        """
        Espera a que bajen a cero los inflights o se alcance el timeout.
        Cierra con estado consistente.
        """
        deadline = _now() + timeout_s
        while _now() < deadline:
            with self._lock:
                inflights = sum(self.inflight.values())
                if inflights == 0:
                    break
            time.sleep(0.2)
