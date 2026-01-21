from __future__ import annotations

import random
import time
import os
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Iterable, Optional, Tuple, Type, TypeVar, Literal

from scrapinsta.config.settings import Settings
from scrapinsta.crosscutting.logging_config import get_logger

_log = get_logger("retry")


T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])

JitterStrategy = Literal["relative", "full", "decorrelated"]


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    base_delay: float
    backoff: float
    jitter: float


class RetryError(RuntimeError):
    """Fallo definitivo tras agotar reintentos. Preserva la causa en __cause__."""

    def __init__(self, message: str, last_error: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.last_error = last_error


class _RetryByResult(RuntimeError):
    pass


# --------------------------------------------------------------------------------------
# Helpers de política/tiempos
# --------------------------------------------------------------------------------------
def _policy_from_settings() -> RetryPolicy:
    """
    Obtiene la política desde Settings(), usando defaults seguros si faltan campos.
    """
    s = Settings()
    # Fallbacks seguros si el Settings no define alguno
    max_retries = int(getattr(s, "retry_max_retries", 3))
    base_delay = float(getattr(s, "retry_base_delay", 1.0))
    backoff = float(getattr(s, "retry_backoff", 2.0))
    jitter = float(getattr(s, "retry_jitter", 0.3))
    return RetryPolicy(max_retries=max_retries, base_delay=base_delay, backoff=backoff, jitter=jitter)


def _compute_sleep(
    *,
    attempt: int,
    base_delay: float,
    backoff: float,
    jitter: float,
    strategy: JitterStrategy,
) -> float:
    """
    Calcula el tiempo de espera para el intento actual.
    """
    nominal = base_delay * (backoff ** (attempt - 1))
    nominal = max(0.0, nominal)

    if strategy == "full":
        # Full Jitter (AWS): uniforme entre 0 y nominal
        sleep_s = random.uniform(0.0, nominal)
    elif strategy == "decorrelated":
        # Decorrelated Jitter (simplificado): uniforme entre base_delay y nominal * (1 + jitter)
        upper = max(base_delay, nominal * (1.0 + max(0.0, jitter)))
        sleep_s = random.uniform(base_delay, upper)
    else:
        # Relative (comportamiento histórico): ± jitter * nominal
        delta = random.uniform(-jitter, jitter) * nominal
        sleep_s = nominal + delta

    sleep_s = max(0.05, sleep_s)  # Evitar sleeps ínfimos (busy-loop)

    # structlog no expone isEnabledFor() como logging stdlib: usamos LOG_LEVEL.
    if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
        _log.debug(
            "retry_compute_sleep",
            attempt=attempt,
            base_delay=base_delay,
            backoff=backoff,
            jitter=jitter,
            strategy=str(strategy),
            sleep_s=sleep_s,
        )
    return sleep_s


# --------------------------------------------------------------------------------------
# API pública (retrocompatible)
# --------------------------------------------------------------------------------------
def retry(
    exceptions: Tuple[Type[BaseException], ...] | Type[BaseException] | Iterable[Type[BaseException]],
    *,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    backoff: Optional[float] = None,
    jitter: Optional[float] = None,
    jitter_strategy: JitterStrategy = "relative",
    max_elapsed: Optional[float] = None,
    retry_if_result: Optional[Callable[[Any], bool]] = None,
    sleeper: Optional[Callable[[float], None]] = None,
) -> Callable[[F], F]:
    """
    Decorador de reintentos con backoff y jitter.

    - `exceptions`: excepción o tupla/iterable de excepciones a reintentar.
    - Parámetros None se resuelven desde Settings() en **cada llamada** (permite ajustar por env sin reinstanciar).
    - `jitter_strategy`: "relative" (legacy), "full" o "decorrelated".
    - `max_elapsed`: deadline total en segundos (opcional).
    - `retry_if_result`: predicado para reintentar según el resultado (p.ej. lista vacía).
    - `sleeper`: función para dormir (por defecto time.sleep). En tests se puede inyectar `lambda _: None`.
    """
    # Normalizamos exceptions a tupla
    if not isinstance(exceptions, tuple):
        if isinstance(exceptions, type) and issubclass(exceptions, BaseException):
            _exceptions_tuple: Tuple[Type[BaseException], ...] = (exceptions,)
        else:
            _exceptions_tuple = tuple(exceptions)  # type: ignore[arg-type]
    else:
        _exceptions_tuple = exceptions

    sleep_fn = sleeper or time.sleep

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            policy = _policy_from_settings()
            _max = int(max_retries if max_retries is not None else policy.max_retries)
            _base = float(base_delay if base_delay is not None else policy.base_delay)
            _back = float(backoff if backoff is not None else policy.backoff)
            _jit = float(jitter if jitter is not None else policy.jitter)

            _max = max(1, _max)
            _base = max(0.0, _base)
            _back = max(1.0, _back)
            _jit = max(0.0, _jit)

            start = time.monotonic()
            last_exc: Optional[BaseException] = None

            for attempt in range(1, _max + 1):
                try:
                    result = func(*args, **kwargs)

                    if retry_if_result and retry_if_result(result):
                        raise _RetryByResult("retry_if_result: resultado reintetable")

                    return result

                except _exceptions_tuple as exc:
                    last_exc = exc
                    if attempt >= _max:
                        _log.error(
                            "Retry agotado: %s (intentos=%d, error=%s)",
                            getattr(func, "__name__", "callable"),
                            attempt,
                            type(exc).__name__,
                        )
                        raise RetryError(
                            f"Se agotaron los reintentos en {getattr(func, '__name__', 'callable')}",
                            last_error=exc,
                        ) from exc

                    sleep_s = _compute_sleep(
                        attempt=attempt, base_delay=_base, backoff=_back, jitter=_jit, strategy=jitter_strategy
                    )

                    if max_elapsed is not None:
                        elapsed = time.monotonic() - start
                        if elapsed + sleep_s > max_elapsed:
                            _log.error(
                                "Retry cancelado por deadline: func=%s elapsed=%.2fs next_sleep=%.2fs",
                                getattr(func, "__name__", "callable"),
                                elapsed,
                                sleep_s,
                            )
                            raise RetryError(
                                f"Deadline excedido en {getattr(func, '__name__', 'callable')}",
                                last_error=exc,
                            ) from exc

                    _log.warning(
                        "Retry intento=%d/%d func=%s exc=%s sleep=%.2fs",
                        attempt,
                        _max,
                        getattr(func, "__name__", "callable"),
                        type(exc).__name__,
                        sleep_s,
                    )
                    sleep_fn(sleep_s)

                except _RetryByResult as exc:
                    last_exc = exc
                    if attempt >= _max:
                        _log.error(
                            "Retry agotado (por resultado): %s (intentos=%d)",
                            getattr(func, "__name__", "callable"),
                            attempt,
                        )
                        raise RetryError(
                            f"Se agotaron los reintentos en {getattr(func, '__name__', 'callable')} (resultado)",
                            last_error=exc,
                        ) from exc

                    sleep_s = _compute_sleep(
                        attempt=attempt, base_delay=_base, backoff=_back, jitter=_jit, strategy=jitter_strategy
                    )
                    if max_elapsed is not None:
                        elapsed = time.monotonic() - start
                        if elapsed + sleep_s > max_elapsed:
                            _log.error(
                                "Retry cancelado por deadline (resultado): func=%s elapsed=%.2fs next_sleep=%.2fs",
                                getattr(func, "__name__", "callable"),
                                elapsed,
                                sleep_s,
                            )
                            raise RetryError(
                                f"Deadline excedido en {getattr(func, '__name__', 'callable')} (resultado)",
                                last_error=exc,
                            ) from exc

                    _log.warning(
                        "Retry (resultado) intento=%d/%d func=%s sleep=%.2fs",
                        attempt,
                        _max,
                        getattr(func, "__name__", "callable"),
                        sleep_s,
                    )
                    sleep_fn(sleep_s)

            raise RetryError(f"Fallo inesperado en {getattr(func, '__name__', 'callable')}", last_error=last_exc)

        return wrapper

    return decorator


def retry_auto(
    *,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    backoff: Optional[float] = None,
    jitter: Optional[float] = None,
    jitter_strategy: JitterStrategy = "decorrelated",
    max_elapsed: Optional[float] = None,
    retry_if_result: Optional[Callable[[Any], bool]] = None,
    sleeper: Optional[Callable[[float], None]] = None,
) -> Callable[[F], F]:
    """
    Decorador de reintentos que reintenta automáticamente *solo* si:
      - la excepción lanzada tiene atributo `retryable=True`, o
      - `retry_if_result(result)` devuelve True para el resultado de la función.

    Útil cuando las capas de dominio marcan sus errores como reintetables
    (p. ej., FollowingsPersistenceError.retryable=True, TransientBlock.retryable=True).
    """
    sleep_fn = sleeper or time.sleep

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            policy = _policy_from_settings()
            _max = int(max_retries if max_retries is not None else policy.max_retries)
            _base = float(base_delay if base_delay is not None else policy.base_delay)
            _back = float(backoff if backoff is not None else policy.backoff)
            _jit = float(jitter if jitter is not None else policy.jitter)

            _max = max(1, _max)
            _base = max(0.0, _base)
            _back = max(1.0, _back)
            _jit = max(0.0, _jit)

            start = time.monotonic()
            last_exc: Optional[BaseException] = None

            for attempt in range(1, _max + 1):
                try:
                    result = func(*args, **kwargs)

                    if retry_if_result and retry_if_result(result):
                        raise _RetryByResult("retry_if_result: resultado reintetable")

                    return result

                except _RetryByResult as exc:
                    last_exc = exc
                    if attempt >= _max:
                        _log.error(
                            "Retry-auto agotado (resultado): %s (intentos=%d)",
                            getattr(func, "__name__", "callable"),
                            attempt,
                        )
                        raise RetryError(
                            f"Se agotaron los reintentos en {getattr(func, '__name__', 'callable')} (resultado)",
                            last_error=exc,
                        ) from exc

                    sleep_s = _compute_sleep(
                        attempt=attempt, base_delay=_base, backoff=_back, jitter=_jit, strategy=jitter_strategy
                    )
                    if max_elapsed is not None:
                        elapsed = time.monotonic() - start
                        if elapsed + sleep_s > max_elapsed:
                            _log.error(
                                "Retry-auto cancelado por deadline (resultado): func=%s elapsed=%.2fs next_sleep=%.2fs",
                                getattr(func, "__name__", "callable"),
                                elapsed,
                                sleep_s,
                            )
                            raise RetryError(
                                f"Deadline excedido en {getattr(func, '__name__', 'callable')} (resultado)",
                                last_error=exc,
                            ) from exc

                    _log.warning(
                        "Retry-auto (resultado) intento=%d/%d func=%s sleep=%.2fs",
                        attempt,
                        _max,
                        getattr(func, "__name__", "callable"),
                        sleep_s,
                    )
                    sleep_fn(sleep_s)

                except BaseException as exc:
                    last_exc = exc
                    retryable = bool(getattr(exc, "retryable", False))
                    if not retryable:
                        raise

                    if attempt >= _max:
                        _log.error(
                            "Retry-auto agotado: %s (intentos=%d, error=%s)",
                            getattr(func, "__name__", "callable"),
                            attempt,
                            type(exc).__name__,
                        )
                        raise RetryError(
                            f"Se agotaron los reintentos en {getattr(func, '__name__', 'callable')}",
                            last_error=exc,
                        ) from exc

                    sleep_s = _compute_sleep(
                        attempt=attempt, base_delay=_base, backoff=_back, jitter=_jit, strategy=jitter_strategy
                    )
                    if max_elapsed is not None:
                        elapsed = time.monotonic() - start
                        if elapsed + sleep_s > max_elapsed:
                            _log.error(
                                "Retry-auto cancelado por deadline: func=%s elapsed=%.2fs next_sleep=%.2fs",
                                getattr(func, "__name__", "callable"),
                                elapsed,
                                sleep_s,
                            )
                            raise RetryError(
                                f"Deadline excedido en {getattr(func, '__name__', 'callable')}",
                                last_error=exc,
                            ) from exc

                    _log.warning(
                        "Retry-auto intento=%d/%d func=%s exc=%s sleep=%.2fs",
                        attempt,
                        _max,
                        getattr(func, "__name__", "callable"),
                        type(exc).__name__,
                        sleep_s,
                    )
                    sleep_fn(sleep_s)

            raise RetryError(f"Fallo inesperado en {getattr(func, '__name__', 'callable')}", last_error=last_exc)

        return wrapper

    return decorator


def retry_call(
    func: Callable[..., T],
    *args: Any,
    exceptions: Tuple[Type[BaseException], ...] | Type[BaseException] | Iterable[Type[BaseException]],
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    backoff: Optional[float] = None,
    jitter: Optional[float] = None,
    jitter_strategy: JitterStrategy = "relative",
    max_elapsed: Optional[float] = None,
    retry_if_result: Optional[Callable[[Any], bool]] = None,
    sleeper: Optional[Callable[[float], None]] = None,
    **kwargs: Any,
) -> T:
    wrapped = retry(
        exceptions=exceptions,
        max_retries=max_retries,
        base_delay=base_delay,
        backoff=backoff,
        jitter=jitter,
        jitter_strategy=jitter_strategy,
        max_elapsed=max_elapsed,
        retry_if_result=retry_if_result,
        sleeper=sleeper,
    )(func)
    return wrapped(*args, **kwargs)
