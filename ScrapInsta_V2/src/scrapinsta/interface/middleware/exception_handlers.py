"""
Exception handlers para FastAPI.
Módulo separado para evitar imports circulares entre api.py y app_factory.py.
"""
from __future__ import annotations

import json
from fastapi import Request, Response, HTTPException

from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.exceptions import ScrapInstaHTTPError

logger = get_logger("api.exceptions")


async def scrapinsta_http_exception_handler(request: Request, exc: ScrapInstaHTTPError):
    """Handler para excepciones HTTP personalizadas de ScrapInsta."""
    logger.warning(
        "http_error",
        error_code=exc.error_code,
        status_code=exc.status_code,
        message=exc.message,
        path=request.url.path,
        method=request.method,
        details=exc.details,
    )
    
    return Response(
        content=json.dumps(exc.to_dict()),
        status_code=exc.status_code,
        media_type="application/json",
    )


async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    """
    Handler para HTTPException de FastAPI.
    Convierte a formato consistente de ScrapInsta.
    """
    error_code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    
    error_code = error_code_map.get(exc.status_code, "HTTP_ERROR")
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    
    logger.warning(
        "http_exception",
        error_code=error_code,
        status_code=exc.status_code,
        detail=detail,
        path=request.url.path,
        method=request.method,
    )
    
    return Response(
        content=json.dumps({
            "error": {
                "code": error_code,
                "message": detail,
            }
        }),
        status_code=exc.status_code,
        media_type="application/json",
    )


async def general_exception_handler(request: Request, exc: Exception):
    """
    Handler genérico para excepciones no manejadas.
    Usa ExceptionMapper para convertir excepciones de dominio a HTTP.
    """
    from scrapinsta.crosscutting.exception_mapping import get_exception_mapper
    
    mapper = get_exception_mapper()
    http_exc = mapper.map(exc)
    
    logger.exception(
        "unhandled_exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
        method=request.method,
        http_error_code=http_exc.error_code,
    )
    
    return await scrapinsta_http_exception_handler(request, http_exc)

