# -*- coding: utf-8 -*-
"""
Configuración de logging estructurado con formato JSON.

Proporciona:
- Logging estructurado en formato JSON
- Correlación de requests (request_id, trace_id, span_id)
- Integración con structlog
- Formato legible en desarrollo, JSON en producción
"""
from __future__ import annotations

import os
import sys
import logging
from typing import Any, Dict, Optional
import structlog
from structlog.types import Processor


def _add_correlation_context(
    logger: logging.Logger, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Agrega contexto de correlación (request_id, trace_id) si está disponible."""
    # Intentar obtener del contexto de structlog
    context = structlog.contextvars.get_contextvars()
    if context:
        event_dict.update(context)
    return event_dict


def configure_structured_logging(
    level: str = "INFO",
    json_format: Optional[bool] = None,
    include_process_id: bool = True,
    include_thread_id: bool = False,
) -> None:
    """
    Configura logging estructurado con structlog.

    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Si True, usa formato JSON. Si None, detecta automáticamente
                     (JSON si LOG_FORMAT=json o si no hay TTY)
        include_process_id: Incluir ID de proceso en logs
        include_thread_id: Incluir ID de thread en logs
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Detectar si usar JSON (producción) o formato legible (desarrollo)
    if json_format is None:
        json_format = (
            os.getenv("LOG_FORMAT", "").lower() == "json"
            or not sys.stdout.isatty()
        )

    # Configurar procesadores de structlog
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # Merge context vars
        structlog.stdlib.add_log_level,  # Agregar nivel de log
        structlog.stdlib.add_logger_name,  # Agregar nombre del logger
        structlog.processors.TimeStamper(fmt="iso"),  # Timestamp ISO 8601
        _add_correlation_context,  # Agregar correlación
    ]

    if include_process_id:
        processors.append(structlog.processors.add_log_level)
        # Agregar process ID manualmente
        def add_process_id(logger, method_name, event_dict):
            event_dict["pid"] = os.getpid()
            return event_dict
        processors.append(add_process_id)

    if include_thread_id:
        import threading
        def add_thread_id(logger, method_name, event_dict):
            event_dict["thread_id"] = threading.current_thread().ident
            return event_dict
        processors.append(add_thread_id)

    # Procesador final: formatear
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(colors=True)
        )

    # Configurar structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configurar logging estándar
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silenciar loggers ruidosos
    for noisy in (
        "selenium",
        "seleniumwire",
        "undetected_chromedriver",
        "urllib3",
        "asyncio",
        "httpcore",
        "httpx",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Obtiene un logger estructurado.

    Args:
        name: Nombre del logger (típicamente __name__)

    Returns:
        Logger estructurado de structlog
    """
    return structlog.get_logger(name)


def bind_request_context(
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    client_id: Optional[str] = None,
    account: Optional[str] = None,
    job_id: Optional[str] = None,
    task_id: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Vincula contexto de request/trace al logger actual.

    Estos valores estarán presentes en todos los logs del contexto actual.

    Args:
        request_id: ID único del request HTTP
        trace_id: ID del trace distribuido
        span_id: ID del span actual
        client_id: ID del cliente
        account: Cuenta de Instagram
        job_id: ID del job
        task_id: ID de la tarea
        **kwargs: Campos adicionales de contexto
    """
    context: Dict[str, Any] = {}
    if request_id:
        context["request_id"] = request_id
    if trace_id:
        context["trace_id"] = trace_id
    if span_id:
        context["span_id"] = span_id
    if client_id:
        context["client_id"] = client_id
    if account:
        context["account"] = account
    if job_id:
        context["job_id"] = job_id
    if task_id:
        context["task_id"] = task_id
    context.update(kwargs)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**context)


def clear_request_context() -> None:
    """Limpia el contexto de request/trace."""
    structlog.contextvars.clear_contextvars()

