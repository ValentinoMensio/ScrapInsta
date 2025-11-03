from __future__ import annotations
import multiprocessing as mp
from queue import Empty
from typing import Optional, Tuple, Callable

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope
from .ports import TaskQueuePort, ResultQueuePort, AckFn, NackFn


class LocalTaskQueue(TaskQueuePort):
    """Adaptador local basado en multiprocessing.Queue con ACK/NACK no-op."""
    def __init__(self, maxsize: int = 0) -> None:
        self._q: mp.Queue = mp.Queue(maxsize)

    def send(self, env: TaskEnvelope) -> None:
        self._q.put(env, block=True)

    def receive(self, timeout_s: float) -> Optional[Tuple[TaskEnvelope, AckFn, NackFn]]:
        try:
            env: TaskEnvelope = self._q.get(timeout=timeout_s)
        except Empty:
            return None

        def _ack() -> None:
            # no-op: ya lo extrajimos de la cola local
            return None

        def _nack() -> None:
            # no reencolamos por simplicidad; mantener determinismo local
            return None

        return (env, _ack, _nack)

    @property
    def raw(self) -> mp.Queue:
        return self._q


class LocalResultQueue(ResultQueuePort):
    """Adaptador local basado en multiprocessing.Queue."""
    def __init__(self, maxsize: int = 0) -> None:
        self._q: mp.Queue = mp.Queue(maxsize)

    def send(self, res: ResultEnvelope) -> None:
        self._q.put(res, block=True)

    def try_get_nowait(self) -> Optional[ResultEnvelope]:
        try:
            return self._q.get_nowait()
        except Empty:
            return None

    @property
    def raw(self) -> mp.Queue:
        return self._q
