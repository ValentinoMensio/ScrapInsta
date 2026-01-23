"""Middleware para observabilidad (request ID, métricas)."""
from __future__ import annotations

import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from scrapinsta.crosscutting.logging_config import (
    bind_request_context,
    clear_request_context,
    get_logger,
)
from scrapinsta.crosscutting.metrics import (
    http_requests_total,
    http_request_duration_seconds,
)

logger = get_logger("middleware.observability")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware para agregar request ID y medir métricas."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        trace_id = request.headers.get("X-Trace-ID") or uuid4().hex

        bind_request_context(
            request_id=request_id,
            trace_id=trace_id,
        )

        start_time = time.time()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            logger.exception(
                "request_error",
                method=method,
                path=path,
                error=str(e),
            )
            raise
        finally:
            # Calcular duración
            duration = time.time() - start_time

            # Registrar métricas
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status_code=status_code,
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=path,
            ).observe(duration)

            logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration * 1000, 2),
            )

            clear_request_context()

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response

