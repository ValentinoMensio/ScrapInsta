"""Rate limiting para la API."""
from __future__ import annotations

import time
import threading
from typing import Dict, Any

from fastapi import Request

from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.exceptions import RateLimitError
from scrapinsta.crosscutting.metrics import rate_limit_hits_total
from scrapinsta.interface.dependencies import get_dependencies

logger = get_logger("auth.rate_limiting")


class _RateLimiter:
    """
    Rate limiter thread-safe en memoria (fallback cuando Redis no está disponible).
    
    NOTA: Este limiter es local al proceso y no protege contra abuso en entornos
    multi-worker. Se recomienda usar Redis para producción.
    """
    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()  # Thread-safe

    def allow(self, key: str, rpm: int) -> bool:
        """
        Verifica si se permite la request según el rate limit.
        
        Args:
            key: Identificador único (ej: "client:client123" o "ip:192.168.1.1")
            rpm: Requests por minuto permitidas
            
        Returns:
            True si se permite, False si se excede el límite
        """
        with self._lock:  # Thread-safe: acceso exclusivo al dict
            now = time.time()
            period = 60.0
            b = self._buckets.get(key)
            if not b:
                self._buckets[key] = {"tokens": float(rpm), "last": now}
                return True
            elapsed = max(0.0, now - float(b["last"]))
            refill = (elapsed / period) * float(rpm)
            tokens = min(float(rpm), float(b["tokens"]) + refill)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = {"tokens": tokens, "last": now}
                return True
            self._buckets[key] = {"tokens": tokens, "last": now}
            return False


# Instancia global del rate limiter en memoria
_memory_rate_limiter = _RateLimiter()


def rate_limit(client: Dict[str, Any], req: Request) -> None:
    """
    Aplica rate limiting por cliente e IP.
    
    Args:
        client: Dict del cliente (de authenticate_client)
        req: Request de FastAPI
        
    Raises:
        RateLimitError: Si se excede el límite de tasa
    """
    deps = get_dependencies()
    distributed_limiter = deps.distributed_rate_limiter
    
    rpm = int(client.get("rate") or 60)
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "-").split(",")[0].strip()
    endpoint = req.url.path
    
    # Intentar usar rate limiting distribuido (Redis)
    if distributed_limiter.enabled:
        # Rate limit por cliente
        allowed, retry_after = distributed_limiter.allow(f"client:{client['id']}", rpm)
        if not allowed:
            rate_limit_hits_total.labels(
                client_id=client['id'],
                endpoint=endpoint,
            ).inc()
            logger.warning(
                "rate_limit_hit",
                client_id=client['id'],
                endpoint=endpoint,
                limit_type="client",
                retry_after=retry_after,
                backend="redis",
            )
            raise RateLimitError(
                "Límite de tasa excedido para el cliente",
                details={
                    "client_id": client['id'],
                    "endpoint": endpoint,
                    "limit_type": "client",
                    "retry_after": retry_after,
                }
            )
        
        # Rate limit por IP (mínimo 60 RPM)
        ip_rpm = max(60, rpm)
        allowed, retry_after = distributed_limiter.allow(f"ip:{ip}", ip_rpm)
        if not allowed:
            rate_limit_hits_total.labels(
                client_id="ip",
                endpoint=endpoint,
            ).inc()
            logger.warning(
                "rate_limit_hit",
                ip=ip,
                endpoint=endpoint,
                limit_type="ip",
                retry_after=retry_after,
                backend="redis",
            )
            raise RateLimitError(
                "Límite de tasa excedido para la IP",
                details={
                    "ip": ip,
                    "endpoint": endpoint,
                    "limit_type": "ip",
                    "retry_after": retry_after,
                }
            )
    else:
        # Fallback al rate limiter en memoria
        if not _memory_rate_limiter.allow(f"client:{client['id']}", rpm):
            rate_limit_hits_total.labels(
                client_id=client['id'],
                endpoint=endpoint,
            ).inc()
            logger.warning(
                "rate_limit_hit",
                client_id=client['id'],
                endpoint=endpoint,
                limit_type="client",
                backend="memory",
            )
            raise RateLimitError(
                "Límite de tasa excedido para el cliente",
                details={"client_id": client['id'], "endpoint": endpoint, "limit_type": "client"}
            )
        if not _memory_rate_limiter.allow(f"ip:{ip}", max(60, rpm)):
            rate_limit_hits_total.labels(
                client_id="ip",
                endpoint=endpoint,
            ).inc()
            logger.warning(
                "rate_limit_hit",
                ip=ip,
                endpoint=endpoint,
                limit_type="ip",
                backend="memory",
            )
            raise RateLimitError(
                "Límite de tasa excedido para la IP",
                details={"ip": ip, "endpoint": endpoint, "limit_type": "ip"}
            )

