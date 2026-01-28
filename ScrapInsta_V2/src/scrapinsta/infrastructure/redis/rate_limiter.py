"""
Rate limiting distribuido usando Redis.
Implementa token bucket algorithm distribuido.
"""
from __future__ import annotations

import time
import os
from typing import Optional
from redis import Redis
from redis.exceptions import RedisError

from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.retry import retry, RetryError

logger = get_logger(__name__)
APP_ENV = os.getenv("APP_ENV", "development").lower()
REDIS_RATE_LIMIT_RETRIES = int(os.getenv("REDIS_RATE_LIMIT_RETRIES", "1"))
FAIL_CLOSED_ON_REDIS_ERROR = os.getenv(
    "FAIL_CLOSED_ON_REDIS_ERROR",
    "true" if APP_ENV == "production" else "false",
).lower() in ("1", "true", "yes")


class DistributedRateLimiter:
    """
    Rate limiter distribuido usando Redis.
    Implementa token bucket algorithm distribuido con precisión atómica.
    """
    
    def __init__(self, redis_client: Optional[Redis]) -> None:
        """
        Inicializa el rate limiter.
        
        Args:
            redis_client: Cliente Redis (puede ser None para fallback en memoria)
        """
        self.redis = redis_client
        self.enabled = redis_client is not None
        
        if self.enabled:
            try:
                redis_client.ping()
                logger.info("distributed_rate_limiter_initialized", enabled=True)
            except Exception as e:
                logger.warning("redis_rate_limiter_init_failed", error=str(e))
                self.enabled = False
                self.redis = None
        else:
            logger.info("distributed_rate_limiter_initialized", enabled=False, mode="fallback")
    
    def allow(
        self,
        key: str,
        rpm: int,
        period_seconds: float = 60.0,
    ) -> tuple[bool, float]:
        """
        Verifica si se permite una solicitud según el rate limit.
        
        Args:
            key: Clave única para el rate limit (ej: "client:123", "ip:1.2.3.4")
            rpm: Requests per minute permitidos
            period_seconds: Período en segundos (default: 60 para RPM)
            
        Returns:
            Tuple (allowed: bool, retry_after: float)
            - allowed: True si se permite la solicitud
            - retry_after: Segundos hasta el próximo slot disponible (0 si allowed=True)
        """
        if not self.enabled or not self.redis:
            # Fallback: permitir siempre si Redis no está disponible
            # (el rate limiting en memoria en api.py actuará como fallback)
            logger.debug("redis_rate_limiter_fallback", key=key, reason="redis_unavailable")
            return True, 0.0
        
        try:
            @retry((RedisError,), max_retries=REDIS_RATE_LIMIT_RETRIES)
            def _allow_retry() -> tuple[bool, float]:
                return self._allow_redis(key, rpm, period_seconds)

            return _allow_retry()
        except RetryError as e:
            logger.warning("redis_rate_limit_error", key=key, error=str(e.last_error or e))
            if FAIL_CLOSED_ON_REDIS_ERROR:
                return False, float(period_seconds)
            return True, 0.0
        except RedisError as e:
            logger.warning("redis_rate_limit_error", key=key, error=str(e))
            if FAIL_CLOSED_ON_REDIS_ERROR:
                return False, float(period_seconds)
            # Fallback: permitir si Redis falla
            return True, 0.0
        except Exception as e:
            logger.error("rate_limit_unexpected_error", key=key, error=str(e))
            return True, 0.0
    
    def _allow_redis(
        self,
        key: str,
        rpm: int,
        period_seconds: float,
    ) -> tuple[bool, float]:
        """
        Implementación de token bucket usando Redis con script Lua atómico.
        """
        redis_key = f"rate_limit:{key}"
        now = time.time()
        tokens = float(rpm)
        refill_rate = tokens / period_seconds  # tokens por segundo
        
        # Script Lua para operación atómica
        # Implementa token bucket: cada segundo se repone refill_rate tokens
        # Máximo tokens es rpm, mínimo 0
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local tokens = tonumber(ARGV[2])
        local refill_rate = tonumber(ARGV[3])
        local period = tonumber(ARGV[4])
        
        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local current_tokens = tonumber(bucket[1]) or tokens
        local last_refill = tonumber(bucket[2]) or now
        
        -- Calcular tokens repuestos desde última vez
        local elapsed = math.max(0, now - last_refill)
        local refilled = elapsed * refill_rate
        current_tokens = math.min(tokens, current_tokens + refilled)
        
        -- Intentar consumir un token
        if current_tokens >= 1.0 then
            current_tokens = current_tokens - 1.0
            redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, math.ceil(period * 2))  -- TTL generoso
            return {1, 0.0}  -- allowed=true, retry_after=0
        else
            -- Calcular cuándo habrá un token disponible
            local needed = 1.0 - current_tokens
            local wait_time = needed / refill_rate
            redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, math.ceil(period * 2))
            return {0, wait_time}  -- allowed=false, retry_after=wait_time
        end
        """
        
        try:
            result = self.redis.eval(
                lua_script,
                1,  # número de keys
                redis_key,
                now,
                tokens,
                refill_rate,
                period_seconds,
            )
            allowed = bool(result[0])
            retry_after = float(result[1])
            return allowed, retry_after
        except Exception as e:
            logger.error("redis_lua_script_error", key=key, error=str(e))
            raise
    
    def get_remaining(self, key: str, rpm: int) -> int:
        """
        Obtiene el número de solicitudes restantes para una clave.
        
        Args:
            key: Clave del rate limit
            rpm: Requests per minute configurados
            
        Returns:
            Número de solicitudes restantes (0 si no está disponible)
        """
        if not self.enabled or not self.redis:
            return rpm  # Fallback: asumir que hay capacidad
        
        redis_key = f"rate_limit:{key}"
        try:
            bucket = self.redis.hmget(redis_key, "tokens")
            if bucket and bucket[0]:
                return int(float(bucket[0]))
        except Exception as e:
            logger.debug("redis_get_remaining_error", key=key, error=str(e))
        
        return rpm

