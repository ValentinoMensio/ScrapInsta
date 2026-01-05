"""
Configuración de logging estructurado con formato JSON.
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
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_format is None:
        json_format = (
            os.getenv("LOG_FORMAT", "").lower() == "json"
            or not sys.stdout.isatty()
        )

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_correlation_context,
    ]

    if include_process_id:
        processors.append(structlog.processors.add_log_level)
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

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(colors=True)
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

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
    structlog.contextvars.clear_contextvars()

