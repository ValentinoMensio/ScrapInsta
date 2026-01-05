from __future__ import annotations

import time
import logging
import heapq
import itertools
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Callable, Deque, Tuple
from collections import defaultdict, deque

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope
from scrapinsta.domain.ports.job_store import JobStorePort
from scrapinsta.crosscutting.metrics import tasks_queued, jobs_active

# =========================
#   PARÁMETROS AJUSTABLES
# =========================

@dataclass
class RouterConfig:
    """
    Config de runtime para repartir trabajo entre cuentas sin quemarlas.
    
    Qué se puede tocar acá:
    - Concurrencia por cuenta (cuántas tareas simultáneas se permiten)
    - Rate limiting suave con tokens por segundo
    - Backoff exponencial cuando algo viene fallando
    - "Aging" para que ninguna cuenta quede sin usar por mucho tiempo
    - Tamaño de lote al despachar
    """
    # Concurrencia por cuenta (tareas en vuelo por cuenta)
    max_inflight_per_account: int = 4
    
    # TokenBucket por cuenta (rate-limit suave sin serrucho)
    tokens_capacity: int = 60
    tokens_refill_per_sec: float = 0.7 
    # Backoff exponencial por cuenta cuando aparecen errores
    max_backoff_s: float = 15 * 60
    base_backoff_s: float = 20
    jitter_s: float = 5.0
    
    # Anti-starvation: subimos la "urgencia" de cuentas que hace rato no despachan
    aging_step: float = 0.05
    aging_cap: float = 1.0

    # Tamaño por lote (cuántos usernames intentamos empujar por ciclo/job)
    default_batch_size: int = 25
    
    # Preferencia de carga balanceada entre cuentas
    load_balance_weight: float = 0.7
    token_availability_weight: float = 0.2
    urgency_weight: float = 0.1


_DEFAULT_CONFIG = RouterConfig()


# =========================
#   TIPOS Y MODELOS
# =========================

@dataclass(order=True)
class _PrioritizedJobRef:
    priority: int
    created_at: float
    job_id: str = field(compare=False)

@dataclass
class Job:
    """
    Unidad de trabajo de alto nivel: analizar/enviar/scrapear para una lista de usuarios.
    - kind: "analyze_profile" | "send_message" | "fetch_followings"
    - items: usernames a procesar
    - extra: payload común que se mezcla en cada TaskEnvelope (p.ej. flags, template)
    - priority: 1 es más alto (min-heap), 10 es más bajo
    """
    job_id: str
    kind: str
    items: List[str]
    batch_size: int = _DEFAULT_CONFIG.default_batch_size
    pending: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    done: bool = False
    extra: Optional[dict] = None
    priority: int = 5

    # Métricas livianas para observabilidad
    dispatched: int = 0
    completed: int = 0
    errors: int = 0

    def __post_init__(self):
        if not self.pending:
            self.pending = set(self.items)


class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = max(1, int(capacity))
        self.refill_per_sec = float(refill_per_sec)
        self.tokens = float(capacity)
        self.last = time.time()

    def _refill(self):
        now = time.time()
        elapsed = now - self.last
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.last = now

    def has(self, n: int = 1) -> bool:
        self._refill()
        return self.tokens >= n

    def consume(self, n: int = 1) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


# =========================
#   ROUTER
# =========================

class Router:
    """
    Orquestador simple y seguro (multi-proceso y thread-safe):
      - Distribuye tareas a N workers (uno por cuenta)
      - Respeta límites por cuenta (in-flight), tokens/seg y backoff
      - Prioriza jobs y evita que una cuenta quede sin uso (aging)
      - Mantiene métricas básicas y, si hay store, persiste jobs/tasks

    No sabe nada de Selenium ni SQL: sólo arma TaskEnvelope y decide a qué worker mandar.
    """

    def __init__(
        self,
        *,
        accounts: List[str],
        send_fn_by_account: Dict[str, Callable[[TaskEnvelope], None]],
        job_store: Optional[JobStorePort] = None,
        config: Optional[RouterConfig] = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        if not accounts:
            raise ValueError("Router: se requiere al menos una cuenta")
        for acc in accounts:
            if not isinstance(acc, str) or not acc.strip():
                raise ValueError(f"Router: cuenta inválida: {acc!r}")

        missing = [a for a in accounts if a not in send_fn_by_account]
        if missing:
            raise ValueError(f"Router: faltan send_fn para cuentas: {missing}")

        self._accounts: List[str] = [a.strip().lower() for a in accounts]
        self._send_map = send_fn_by_account
        self._now = now_fn
        self._job_store = job_store
        self._config = config or _DEFAULT_CONFIG

        self._inflight: Dict[str, int] = {a: 0 for a in self._accounts}
        self._limiters: Dict[str, TokenBucket] = {
            a: TokenBucket(
                capacity=self._config.tokens_capacity, 
                refill_per_sec=self._config.tokens_refill_per_sec
            ) for a in self._accounts
        }
        self._rr = itertools.cycle(self._accounts)

        self._acct_state: Dict[str, Dict[str, float | int]] = defaultdict(lambda: {
            "error_count": 0,
            "cooldown_until": 0.0,
        })

        self._urgency: Dict[str, float] = defaultdict(float)

        self._jobs: Dict[str, Job] = {}
        self._job_heap: List[_PrioritizedJobRef] = []

        self._task_meta: Dict[str, Dict[str, Any]] = {}

        self._acct_metrics: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "rt_avg": 3.0,
            "ok_ratio": 1.0,
        })

        self._lock = threading.Lock()
        self._stopping = False

    # ----------------
    #   API PÚBLICA
    # ----------------

    def add_job(self, job: Job) -> None:
        """
        Registra un nuevo Job. Podés llamar esto desde el hilo principal.
        Persiste el Job si hay JobStore.
        """
        with self._lock:
            if job.job_id in self._jobs:
                raise ValueError(f"Job duplicado: {job.job_id}")
            self._jobs[job.job_id] = job
            heapq.heappush(self._job_heap, _PrioritizedJobRef(priority=job.priority, created_at=job.created_at, job_id=job.job_id))

            if self._job_store:
                try:
                    self._job_store.create_job(
                        job_id=job.job_id,
                        kind=job.kind,
                        priority=job.priority,
                        batch_size=job.batch_size,
                        extra=job.extra,
                        total_items=len(job.items),
                    )
                    self._job_store.mark_job_running(job.job_id)
                except Exception:
                    pass

    def dispatch_tick(self) -> None:
        """
        Un tick de despacho: intenta mandar tareas respetando prioridades,
        límites por cuenta, tokens, backoff y aging. Llamalo en un loop.
        """
        with self._lock:
            if self._stopping:
                return

            self._age_all_accounts()
            self._refresh_heap()

            heap_snapshot = list(self._job_heap)
            heapq.heapify(heap_snapshot)

            while heap_snapshot:
                jref = heapq.heappop(heap_snapshot)
                job = self._jobs.get(jref.job_id)
                if not job or job.done or not job.pending:
                    continue

                dispatched_now = self._dispatch_some(job)

                if not job.done and job.pending:
                    heapq.heappush(self._job_heap, _PrioritizedJobRef(priority=job.priority, created_at=job.created_at, job_id=job.job_id))

                if dispatched_now == 0 and not self._any_account_can_send():
                    break

            for acc in self._accounts:
                queued_count = sum(len(job.pending) for job in self._jobs.values() if not job.done)
                tasks_queued.labels(status="queued", account=acc).set(queued_count)

    def on_result(self, res: ResultEnvelope) -> None:
        """
        Se llama por cada resultado que llega de los workers.
        Actualiza inflight, métricas y marca jobs cuando corresponde.
        Si hay JobStore, persiste el estado de la task.
        """
        with self._lock:
            task_id = getattr(res, "task_id", None)
            ok = bool(getattr(res, "ok", False))
            now = self._now()

            if not task_id:
                return

            meta = self._task_meta.pop(task_id, None)
            if meta:
                acc = meta["account"]
                self._inflight[acc] = max(0, self._inflight.get(acc, 0) - 1)

                start = meta.get("start_time")
                rt = max(0.0, (now - float(start))) if start else 0.0
                m = self._acct_metrics[acc]
                m["rt_avg"] = (m["rt_avg"] * 0.8) + (rt * 0.2)
                m["ok_ratio"] = (m["ok_ratio"] * 0.9) + ((1.0 if ok else 0.0) * 0.1)

                if ok:
                    self._mark_account_ok(acc)
                else:
                    self._mark_account_error(acc)

                job_id = meta.get("job_id")
                if job_id and job_id in self._jobs:
                    job = self._jobs[job_id]
                    if ok:
                        job.completed += 1
                    else:
                        job.errors += 1

            if self._job_store:
                try:
                    corr = getattr(res, "correlation_id", None)
                    if ok:
                        self._job_store.mark_task_ok(corr, task_id, res.result if isinstance(res.result, dict) else None)
                    else:
                        self._job_store.mark_task_error(corr, task_id, res.error or "error")

                    if corr and self._job_store.all_tasks_finished(corr):
                        self._job_store.mark_job_done(corr)
                        jobs_active.labels(status="done").inc()
                        jobs_active.labels(status="running").dec()
                except Exception:
                    pass

    def stop_accepting(self) -> None:
        """Deja de aceptar envíos nuevos (se drenan las tareas en vuelo)."""
        with self._lock:
            self._stopping = True

    def all_done(self) -> bool:
        """True si todos los jobs terminaron (sin pendientes ni en vuelo)."""
        with self._lock:
            return all(j.done for j in self._jobs.values())

    def kpis(self) -> Dict[str, Dict[str, float | int]]:
        """KPIs resumidos para ver cómo venimos."""
        with self._lock:
            by_kind: Dict[str, Dict[str, int]] = {}
            total = {"dispatched": 0, "completed": 0, "errors": 0, "jobs": 0}
            for j in self._jobs.values():
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

    def stats(self) -> Dict[str, Any]:
        """Snapshot más detallado (para logs/monitoreo)."""
        with self._lock:
            return {
                "ts": self._now(),
                "accounts": {
                    a: {
                        "tokens": round(self._limiters[a].tokens, 2),
                        "inflight": self._inflight[a],
                        "cooldown_until": float(self._acct_state[a]["cooldown_until"]),
                        "error_count": int(self._acct_state[a]["error_count"]),
                        "rt_avg": round(self._acct_metrics[a]["rt_avg"], 3),
                        "ok_ratio": round(self._acct_metrics[a]["ok_ratio"], 3),
                        "urgency": round(self._urgency[a], 2),
                    } for a in self._accounts
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
                    } for j in self._jobs.values()
                },
                "inflight_total": sum(self._inflight.values()),
                "task_map_size": len(self._task_meta),
                "queue_jobs": len(self._job_heap),
            }

    # ----------------
    #   INTERNOS
    # ----------------

    def _refresh_heap(self) -> None:
        """Limpia referencias a jobs finalizados o vacíos del heap de prioridad."""
        tmp: List[_PrioritizedJobRef] = []
        seen: Set[str] = set()
        while self._job_heap:
            jref = heapq.heappop(self._job_heap)
            if jref.job_id in seen:
                continue
            seen.add(jref.job_id)
            job = self._jobs.get(jref.job_id)
            if job and not job.done and job.pending:
                heapq.heappush(tmp, jref)
        self._job_heap = tmp

    def _any_account_can_send(self) -> bool:
        for a in self._accounts:
            if self._is_account_available(a) and self._inflight[a] < self._config.max_inflight_per_account and self._limiters[a].has(1):
                return True
        return False

    def _age_all_accounts(self) -> None:
        for a in self._accounts:
            self._urgency[a] = min(self._config.aging_cap, self._urgency[a] + self._config.aging_step)

    def _is_account_available(self, acc: str) -> bool:
        return self._now() >= float(self._acct_state[acc]["cooldown_until"])

    def _mark_account_error(self, acc: str) -> None:
        st = self._acct_state[acc]
        st["error_count"] = int(st["error_count"]) + 1
        backoff = min(
            self._config.max_backoff_s, 
            self._config.base_backoff_s * (2 ** (int(st["error_count"]) - 1))
        )
        jitter = random.uniform(0.0, self._config.jitter_s)
        st["cooldown_until"] = self._now() + backoff + jitter

    def _mark_account_ok(self, acc: str) -> None:
        st = self._acct_state[acc]
        st["error_count"] = 0
        st["cooldown_until"] = 0.0

    def _score_for_account(self, acc: str) -> float:
        """
        Scoring para elegir cuenta: mezcla carga, urgencia y tokens disponibles.
        """
        max_inflight = self._config.max_inflight_per_account
        load = float(self._inflight.get(acc, 0)) / max_inflight if max_inflight > 0 else 0.0
        load_score = (1.0 - load) * self._config.load_balance_weight
        
        urgency_score = self._urgency[acc] * self._config.urgency_weight
        
        tokens_norm = min(1.0, self._limiters[acc].tokens / max(1, self._config.tokens_capacity))
        token_score = tokens_norm * self._config.token_availability_weight
        
        return load_score + urgency_score + token_score

    def _pick_account(self) -> Optional[str]:
        """
        Elige la mejor cuenta disponible:
          - sin cooldown,
          - con inflight bajo el máximo configurado,
          - con tokens suficientes.
        Consume 1 token cuando la elige.
        """
        tried: Set[str] = set()
        candidates: List[str] = []
        for _ in range(len(self._accounts)):
            acc = next(self._rr)
            if acc in tried:
                continue
            tried.add(acc)
            if (self._is_account_available(acc) and 
                self._inflight[acc] < self._config.max_inflight_per_account and 
                self._limiters[acc].has(1)):
                candidates.append(acc)

        if not candidates:
            return None

        best = max(candidates, key=self._score_for_account)
        if self._limiters[best].consume(1):
            self._urgency[best] = 0.0
            return best
        return None

    def _dispatch_some(self, job: Job) -> int:
        """
        Intenta despachar hasta job.batch_size tareas del Job.
        Devuelve cuántas se mandaron.
        Si hay JobStore, persiste cada task.
        """
        sent = 0
        to_send = list(itertools.islice(iter(job.pending), job.batch_size))

        for username in to_send:
            # -----------------------------
            # Caso especial: send_message
            #   - NO se envía a workers del servidor
            #   - Se persiste como 'queued' para la cuenta del cliente
            #   - La extensión local hará /api/send/pull y /api/send/result
            # -----------------------------
            if job.kind == "send_message":
                client_acc = (job.extra or {}).get("client_account") if job.extra else None
                if not client_acc:
                    if job.job_id in self._jobs:
                        self._jobs[job.job_id].errors += 1
                    job.pending.discard(username)
                    continue

                if self._job_store:
                    try:
                        if self._job_store.was_message_sent(client_acc, username):
                            job.pending.discard(username)
                            continue
                    except Exception:
                        pass

                payload: Dict[str, Any] = {}
                if job.extra:
                    payload.update(job.extra)
                payload["target_username"] = username

                task_id = f"{job.job_id}:{job.kind}:{username}"

                if self._job_store:
                    try:
                        self._job_store.add_task(
                            job_id=job.job_id,
                            task_id=task_id,
                            correlation_id=job.job_id,
                            account_id=client_acc,
                            username=username,
                            payload=payload if isinstance(payload, dict) else None,
                        )
                        logging.getLogger("router").info("task queued: %s (account=%s)", task_id, client_acc)
                    except Exception:
                        pass

                job.pending.discard(username)
                job.dispatched += 1
                sent += 1
                continue

            # -----------------------------
            # Resto de casos: workers del servidor
            # -----------------------------
            acc = self._pick_account()
            if not acc:
                break

            payload: Dict[str, Any] = {"username": username}
            if job.extra:
                payload.update(job.extra)

            task_id = f"{job.job_id}:{job.kind}:{username}"

            env = TaskEnvelope(
                task=job.kind,
                payload=payload,
                account_id=acc,
                id=task_id,
                correlation_id=job.job_id,
            )

            if self._job_store:
                try:
                    self._job_store.add_task(
                        job_id=job.job_id,
                        task_id=task_id,
                        correlation_id=job.job_id,
                        account_id=acc,
                        username=username,
                        payload=payload if isinstance(payload, dict) else None,
                    )
                    logging.getLogger("router").info("task queued: %s (account=%s)", task_id, acc)
                except Exception:
                    pass

            self._send_map[acc](env)
            logging.getLogger("router").info("task sent: %s -> %s", task_id, acc)

            if self._job_store:
                try:
                    self._job_store.mark_task_sent(job.job_id, task_id)
                except Exception:
                    pass

            self._task_meta[task_id] = {
                "account": acc,
                "username": username,
                "job_id": job.job_id,
                "start_time": self._now(),
            }
            self._inflight[acc] = self._inflight.get(acc, 0) + 1
            job.pending.discard(username)
            job.dispatched += 1
            sent += 1

        if not job.pending:
            still = any(m.get("job_id") == job.job_id for m in self._task_meta.values())
            job.done = not still

        return sent
