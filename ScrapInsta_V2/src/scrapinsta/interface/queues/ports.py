from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Callable, Tuple

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope

AckFn = Callable[[], None]
NackFn = Callable[[], None]


class TaskQueuePort(ABC):
    """
    Puerto: cola de tareas -> produce TaskEnvelope para los workers.
    receive() debe devolver (env, ack, nack) o None si hay timeout.
    """

    @abstractmethod
    def send(self, env: TaskEnvelope) -> None:
        """Encola una tarea (bloqueante/seguro)."""
        raise NotImplementedError

    @abstractmethod
    def receive(self, timeout_s: float) -> Optional[Tuple[TaskEnvelope, AckFn, NackFn]]:
        """Desencola una tarea y devuelve (env, ack, nack) o None en timeout."""
        raise NotImplementedError


class ResultQueuePort(ABC):
    """Puerto de cola de resultados -> produce ResultEnvelope hacia el router."""

    @abstractmethod
    def send(self, res: ResultEnvelope) -> None:
        """Encola un resultado (bloqueante/seguro)."""
        raise NotImplementedError

    @abstractmethod
    def try_get_nowait(self) -> Optional[ResultEnvelope]:
        """Lee un resultado sin bloquear; None si está vacía."""
        raise NotImplementedError
