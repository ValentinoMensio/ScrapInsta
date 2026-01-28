"""Middleware para limitar el tamaño del cuerpo de la request."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from scrapinsta.crosscutting.logging_config import get_logger

logger = get_logger("middleware.request_limits")

APP_ENV = os.getenv("APP_ENV", "development").lower()
DEFAULT_MAX_BODY_BYTES = 1_000_000 if APP_ENV == "production" else 5_000_000


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rechaza requests con body mayor a MAX_BODY_BYTES."""

    def __init__(self, app, max_body_bytes: Optional[int] = None) -> None:
        super().__init__(app)
        env_limit = os.getenv("MAX_BODY_BYTES")
        if max_body_bytes is None:
            try:
                max_body_bytes = int(env_limit) if env_limit else DEFAULT_MAX_BODY_BYTES
            except Exception:
                max_body_bytes = DEFAULT_MAX_BODY_BYTES
        self._max_body_bytes = max(0, int(max_body_bytes))

    async def dispatch(self, request: Request, call_next):
        if self._max_body_bytes <= 0:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._max_body_bytes:
                    logger.warning(
                        "request_body_too_large",
                        path=request.url.path,
                        content_length=content_length,
                        max_body_bytes=self._max_body_bytes,
                    )
                    return Response(
                        status_code=413,
                        content='{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request body too large"}}',
                        media_type="application/json",
                    )
            except Exception:
                pass

        body = await request.body()
        if len(body) > self._max_body_bytes:
            logger.warning(
                "request_body_too_large",
                path=request.url.path,
                content_length=len(body),
                max_body_bytes=self._max_body_bytes,
            )
            return Response(
                status_code=413,
                content='{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request body too large"}}',
                media_type="application/json",
            )

        request._body = body
        return await call_next(request)

