import time
import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from queue import Queue  # Evitar import circular

from core.worker.messages import (
    TASK_FETCH_FOLLOWINGS, TASK_ANALYZE, TASK_SEND_MESSAGE
)


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


class Router:
    """
    Reparte tareas entre cuentas disponibles.
    - Token bucket por cuenta para rate limit “suave”.
    - Selección por menor inflight entre cuentas con token disponible (fairness real).
    - Mantiene mapping task_id -> (account, username, job_id).
    """
    def __init__(self, accounts: List[dict], worker_queues: Dict[str, "Queue"]):
        self.accounts = accounts
        self.worker_queues = worker_queues
        # Inflights visibles para fairness
        self.inflight: Dict[str, int] = {a["username"]: 0 for a in accounts}
        # Token bucket simple por cuenta (ajustá a gusto)
        self.limiters: Dict[str, TokenBucket] = {
            a["username"]: TokenBucket(capacity=60, refill_per_sec=1.0)  # ~60 tareas/min
            for a in accounts
        }
        self._rr = itertools.cycle([a["username"] for a in accounts])
        self.jobs: Dict[str, Job] = {}
        self.task_map: Dict[str, Dict] = {}  # task_id -> {account, username, job_id}

    def add_job(self, job: Job):
        self.jobs[job.job_id] = job

    def _pick_account(self) -> Optional[str]:
        """
        Elige la cuenta con token disponible y MENOR inflight.
        Recorre a partir del round-robin para no sesgar siempre al mismo inicio.
        Solo consume token de la cuenta elegida.
        """
        tried = set()
        candidates: List[str] = []

        for _ in range(len(self.accounts)):
            acc = next(self._rr)
            if acc in tried:
                continue
            tried.add(acc)
            if self.limiters[acc].has(1):
                candidates.append(acc)

        if not candidates:
            return None

        # Elegir la de menor inflight (fairness real)
        best = min(candidates, key=lambda a: self.inflight.get(a, 0))
        # Consumir un token de la cuenta elegida
        if self.limiters[best].consume(1):
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

    def dispatch(self):
        """Intenta despachar hasta un batch por job."""
        for job in self.jobs.values():
            if job.done or not job.pending:
                continue

            dispatched = 0
            to_send = list(itertools.islice(iter(job.pending), job.batch_size))
            for username in to_send:
                account = self._pick_account()
                if not account:
                    break  # sin tokens ahora; probá en el próximo tick

                # Asegurar unicidad de task_id: incluir job_id
                task_id = f"{job.job_id}:{job.kind}:{username}"
                task = {
                    "id": task_id,
                    "type": self._task_type_for(job),
                    "profile": username,
                }
                if job.extra:
                    task.update(job.extra)
                self.worker_queues[account].put(task)

                self.task_map[task_id] = {"account": account, "username": username, "job_id": job.job_id}
                self.inflight[account] = self.inflight.get(account, 0) + 1
                job.pending.discard(username)
                dispatched += 1

            # Si ya no quedan pendientes, marcamos done solo si tampoco hay inflights activos del job
            if not job.pending:
                still = any(m.get("job_id") == job.job_id for m in self.task_map.values())
                job.done = not still

    def on_result(self, result: dict):
        """
        Llamar con cada mensaje del result_queue.
        Actualiza inflight y estado de jobs usando el mapeo guardado.
        """
        task_id = result.get("task_id")
        meta = None

        if task_id and task_id in self.task_map:
            meta = self.task_map.pop(task_id)
            acc = meta["account"]
            self.inflight[acc] = max(0, self.inflight.get(acc, 0) - 1)

        # Detectar fin del job usando el job_id real desde meta o, si no está, parsear
        job_id = None
        if meta:
            job_id = meta.get("job_id")
        elif task_id:
            # Fallback: intentar parsear "jobId:kind:username"
            parts = task_id.split(":", 2)
            if len(parts) >= 1:
                job_id = parts[0]

        if job_id and job_id in self.jobs:
            job = self.jobs[job_id]
            if not job.pending:
                still = any(m.get("job_id") == job_id for m in self.task_map.values())
                if not still:
                    job.done = True

    def all_done(self) -> bool:
        return all(j.done for j in self.jobs.values())
