from __future__ import annotations

import signal
import time
from typing import Callable, Optional

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope
from scrapinsta.application.services.task_dispatcher import TaskDispatcher
from scrapinsta.crosscutting.logging_config import get_logger
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
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL

log = get_logger("worker")

def _is_retryable_browser_crash(err: str) -> bool:
    s = (err or "").lower()
    return (
        "invalid session id" in s
        or "not connected to devtools" in s
        or "session deleted as the browser has closed the connection" in s
        or "from disconnected" in s and "devtools" in s
    )


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
        log.warning("worker_stop_signal", worker=self._name)
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
                log.debug("worker_heartbeat_send_failed", worker=self._name)
            self._last_hb = now

    # ---------------------------
    # Bucle principal
    # ---------------------------
    def run(self) -> None:
        settings = Settings()
        job_store = JobStoreSQL(settings.db_dsn)
        log.info(
            "worker_starting",
            worker=self._name,
            selenium_url=getattr(settings, "selenium_url", None),
            poll_s=self._poll,
            heartbeat_s=self._hb,
        )

        self._install_signals()
        self._running = True
        self._last_hb = 0.0

        while self._running:
            if self._stop_event and self._stop_event():
                log.info("worker_stop_event", worker=self._name)
                break

            pack = None
            try:
                pack = self._receive(self._poll)
            except Exception as e:
                log.warning("worker_receive_failed", worker=self._name, error=str(e))
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
                    log.debug("worker_ack_failed_poison_pill", worker=self._name)
                log.info("worker_poison_pill", worker=self._name)
                break

            task_kind = getattr(env, "task", "unknown")
            account = getattr(env, "account_id", "unknown")
            start_time = time.time()

            try:
                # Cinturón y tirantes: idempotencia en consumer ante doble delivery (SQS/colas).
                corr = getattr(env, "correlation_id", None)
                task_id = getattr(env, "id", None)
                if corr and task_id and isinstance(account, str) and account.strip():
                    try:
                        started = job_store.begin_task(
                            job_id=str(corr),
                            task_id=str(task_id),
                            account_id=str(account),
                            leased_by=self._name,
                        )
                        if not started:
                            try:
                                ack()
                            except Exception:
                                pass
                            self._maybe_heartbeat()
                            continue
                    except Exception:
                        # Si no podemos verificar, preferimos NO ejecutar para evitar side-effects duplicados.
                        try:
                            ack()
                        except Exception:
                            pass
                        self._maybe_heartbeat()
                        continue

                result = self._dispatcher.dispatch(env)
                # Retry controlado: si el browser se cae, marcamos como retryable para que el Router reencole con cap.
                if (not result.ok) and _is_retryable_browser_crash(getattr(result, "error", "") or ""):
                    try:
                        payload = result.result if isinstance(result.result, dict) else {}
                        payload = dict(payload)
                        payload.update({"retryable": True, "retry_reason": "driver_dead"})
                        result.result = payload
                    except Exception:
                        pass
                duration = time.time() - start_time
                
                task_duration_seconds.labels(kind=task_kind, account=account).observe(duration)
                
                status = "success" if result.ok else "failed"
                tasks_processed_total.labels(kind=task_kind, status=status, account=account).inc()
                
                try:
                    self._send(result)
                except Exception as e:
                    log.error("worker_send_failed", worker=self._name, error=str(e))
                    try:
                        nack()
                    except Exception:
                        log.debug("worker_nack_failed_after_send_error", worker=self._name)
                    self._maybe_heartbeat()
                    continue

                try:
                    ack()
                except Exception:
                    log.debug("worker_ack_failed", worker=self._name)

            except Exception as e:
                duration = time.time() - start_time
                error_type = type(e).__name__
                
                task_duration_seconds.labels(kind=task_kind, account=account).observe(duration)
                tasks_processed_total.labels(kind=task_kind, status="error", account=account).inc()
                worker_errors_total.labels(account=account, error_type=error_type).inc()
                
                log.error("worker_dispatch_failed", worker=self._name, error=str(e), error_type=error_type)
                try:
                    self._send(ResultEnvelope(
                        ok=False,
                        error="dispatch failure",
                        attempts=1,
                        task_id=getattr(env, "id", None),
                        correlation_id=getattr(env, "correlation_id", None),
                    ))
                except Exception:
                    log.debug("worker_send_failure_result_failed", worker=self._name)
                try:
                    nack()
                except Exception:
                    log.debug("worker_nack_failed_after_dispatch_error", worker=self._name)

            self._maybe_heartbeat()

        log.info("worker_stopped", worker=self._name)

