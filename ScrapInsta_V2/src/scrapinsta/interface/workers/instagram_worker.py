from __future__ import annotations

import logging
import signal
import time
from typing import Callable, Optional

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope
from scrapinsta.application.services.task_dispatcher import TaskDispatcher
from scrapinsta.crosscutting.metrics import (
    tasks_processed_total,
    task_duration_seconds,
    worker_errors_total,
)

try:
    from scrapinsta.application.services.task_dispatcher import UseCaseFactory
except Exception:
    from typing import Protocol
    class UseCaseFactory(Protocol):
        def create_analyze_profile(self): ...
        def create_send_message(self): ...
        def create_fetch_followings(self): ...

from scrapinsta.config.settings import Settings

logger = logging.getLogger(__name__)


class InstagramWorker:
    """
    Worker de propósito general, desacoplado de Selenium/SQL.

    Responsabilidades:
      - Bloquear en receive() hasta obtener un TaskEnvelope (o timeout/poll corto).
      - Despachar la tarea al caso de uso mediante TaskDispatcher.
      - Enviar el ResultEnvelope por send().
      - Heartbeats y parada ordenada (stop_event o señal).

    No hace:
      - Manejo directo de Selenium o DB (lo hacen adapters inyectados en la Factory).
      - Reintentos ad-hoc (los decoradores y puertos ya marcan retryable).
      - Persistencia/log de negocio (eso está en los use cases/adapters).
    """

    def __init__(
        self,
        *,
        name: str,
        factory: UseCaseFactory,
        receive: Callable[[float], Optional[TaskEnvelope]],
        send: Callable[[ResultEnvelope], None],
        stop_event: Optional[Callable[[], bool]] = None,
        poll_interval_s: float = 1.5,
        heartbeat_s: float = 30.0,
    ) -> None:
        self._name = name
        self._factory = factory
        self._dispatcher = TaskDispatcher(factory)
        self._receive = receive
        self._send = send
        self._stop_event = stop_event
        self._poll = max(0.1, float(poll_interval_s))
        self._hb = max(5.0, float(heartbeat_s))
        self._last_hb = 0.0
        self._running = False

    # ---------------------------
    # Señales (SIGINT/SIGTERM)
    # ---------------------------
    def _install_signals(self) -> None:
        try:
            signal.signal(signal.SIGINT, self._on_stop_signal)   # Ctrl+C
            signal.signal(signal.SIGTERM, self._on_stop_signal)  # kill/termination
        except Exception:
            pass

    def _on_stop_signal(self, *_: object) -> None:
        logger.warning("[%s] stop signal received", self._name)
        self._running = False

    # ---------------------------
    # Heartbeat
    # ---------------------------
    def _maybe_heartbeat(self) -> None:
        now = time.time()
        if (now - self._last_hb) >= self._hb:
            try:
                self._send(ResultEnvelope(
                    ok=True,
                    result={"type": "heartbeat", "worker": self._name, "ts": int(now)},
                    attempts=1,
                ))
            except Exception:
                logger.debug("[%s] heartbeat send failed", self._name, exc_info=True)
            self._last_hb = now

    # ---------------------------
    # Bucle principal
    # ---------------------------
    def run(self) -> None:
        settings = Settings()
        logger.info(
            "[%s] starting worker | selenium_url=%s poll=%.1fs hb=%.1fs",
            self._name, getattr(settings, "selenium_url", None), self._poll, self._hb
        )

        self._install_signals()
        self._running = True
        self._last_hb = 0.0

        while self._running:
            if self._stop_event and self._stop_event():
                logger.info("[%s] stop_event set -> exiting loop", self._name)
                break

            pack = None
            try:
                pack = self._receive(self._poll)
            except Exception as e:
                logger.warning("[%s] receive() failed: %s", self._name, e, exc_info=True)
                self._maybe_heartbeat()
                continue

            if pack is None:
                self._maybe_heartbeat()
                continue

            env, ack, nack = pack

            if getattr(env, "task", None) is None and getattr(env, "id", None) is None:
                try:
                    ack() 
                except Exception:
                    logger.debug("[%s] ack failed on poison pill", self._name, exc_info=True)
                logger.info("[%s] poison pill received -> exiting", self._name)
                break

            task_kind = getattr(env, "task", "unknown")
            account = getattr(env, "account_id", "unknown")
            start_time = time.time()

            try:
                result = self._dispatcher.dispatch(env)
                duration = time.time() - start_time
                
                task_duration_seconds.labels(kind=task_kind, account=account).observe(duration)
                
                status = "success" if result.ok else "failed"
                tasks_processed_total.labels(kind=task_kind, status=status, account=account).inc()
                
                try:
                    self._send(result)
                except Exception as e:
                    logger.error("[%s] send() failed: %s", self._name, e, exc_info=True)
                    try:
                        nack()
                    except Exception:
                        logger.debug("[%s] nack failed after send error", self._name, exc_info=True)
                    self._maybe_heartbeat()
                    continue

                try:
                    ack()
                except Exception:
                    logger.debug("[%s] ack failed", self._name, exc_info=True)

            except Exception as e:
                duration = time.time() - start_time
                error_type = type(e).__name__
                
                task_duration_seconds.labels(kind=task_kind, account=account).observe(duration)
                tasks_processed_total.labels(kind=task_kind, status="error", account=account).inc()
                worker_errors_total.labels(account=account, error_type=error_type).inc()
                
                logger.exception("[%s] dispatch failed: %s", self._name, e)
                try:
                    self._send(ResultEnvelope(
                        ok=False,
                        error="dispatch failure",
                        attempts=1,
                        task_id=getattr(env, "id", None),
                        correlation_id=getattr(env, "correlation_id", None),
                    ))
                except Exception:
                    logger.debug("[%s] send() of failure result also failed", self._name, exc_info=True)
                try:
                    nack()
                except Exception:
                    logger.debug("[%s] nack failed after dispatch error", self._name, exc_info=True)

            self._maybe_heartbeat()

        logger.info("[%s] worker stopped", self._name)

