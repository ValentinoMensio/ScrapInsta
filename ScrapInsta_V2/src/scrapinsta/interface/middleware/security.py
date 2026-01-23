"""Middleware para headers de seguridad HTTP."""
from __future__ import annotations

import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

REQUIRE_HTTPS = os.getenv("REQUIRE_HTTPS", "false").lower() in ("1", "true", "yes")


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware para agregar headers de seguridad HTTP (HSTS, CSP, etc.)."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        if REQUIRE_HTTPS:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # CSP restrictivo por defecto - ajustar si necesitas recursos externos
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response

