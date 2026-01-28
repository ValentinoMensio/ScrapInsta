"""
Cliente Redis configurable con connection pooling y manejo de errores.
"""
from __future__ import annotations

from typing import Optional
import os
from redis import Redis, ConnectionPool
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from scrapinsta.config.settings import Settings
from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.retry import retry, RetryError
from scrapinsta.crosscutting.metrics import redis_connection_status

logger = get_logger(__name__)
REDIS_INIT_RETRIES = int(os.getenv("REDIS_INIT_RETRIES", "2"))

_redis_client: Optional[Redis] = None
_redis_pool: Optional[ConnectionPool] = None


def create_redis_pool(settings: Settings) -> Optional[ConnectionPool]:
    """
    Crea un connection pool de Redis basado en la configuración.
    
    Args:
        settings: Configuración de la aplicación
        
    Returns:
        ConnectionPool configurado o None si Redis no está disponible
    """
    try:
        # Si hay REDIS_URL, usarla directamente (para Redis Cloud, etc.)
        if settings.redis_url:
            pool = ConnectionPool.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                socket_timeout=settings.redis_socket_timeout,
                socket_connect_timeout=settings.redis_socket_connect_timeout,
                socket_keepalive=settings.redis_socket_keepalive,
                health_check_interval=settings.redis_health_check_interval,
                decode_responses=settings.redis_decode_responses,
            )
            logger.info("redis_pool_created", source="redis_url")
            return pool
        
        # Configuración manual
        pool = ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            socket_keepalive=settings.redis_socket_keepalive,
            health_check_interval=settings.redis_health_check_interval,
            decode_responses=settings.redis_decode_responses,
        )
        logger.info(
            "redis_pool_created",
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
        )
        return pool
    except Exception as e:
        logger.error("redis_pool_creation_failed", error=str(e))
        return None


class RedisClient:
    """
    Cliente Redis con manejo de errores y health checks.
    """
    
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._enabled = False
        
        self._initialize()
    
    def _initialize(self) -> None:
        """Inicializa el pool y cliente de Redis."""
        self._pool = create_redis_pool(self.settings)
        if not self._pool:
            logger.warning("redis_disabled", reason="pool_creation_failed")
            return
        
        try:
            self._client = Redis(connection_pool=self._pool)
            # Test de conexión con reintentos
            @retry((RedisConnectionError, RedisError), max_retries=REDIS_INIT_RETRIES)
            def _ping() -> bool:
                return self._client.ping()

            _ping()
            self._enabled = True
            redis_connection_status.set(1)
            logger.info("redis_client_initialized", enabled=True)
        except RetryError as e:
            logger.warning("redis_connection_failed", error=str(e.last_error or e), enabled=False)
            self._enabled = False
            redis_connection_status.set(0)
        except RedisConnectionError as e:
            logger.warning("redis_connection_failed", error=str(e), enabled=False)
            self._enabled = False
            redis_connection_status.set(0)
        except Exception as e:
            logger.error("redis_initialization_error", error=str(e), enabled=False)
            self._enabled = False
            redis_connection_status.set(0)
    
    @property
    def client(self) -> Optional[Redis]:
        """
        Retorna el cliente Redis o None si no está disponible.
        """
        if not self._enabled or not self._client:
            return None
        return self._client
    
    @property
    def enabled(self) -> bool:
        """Indica si Redis está habilitado y conectado."""
        return self._enabled
    
    def ping(self) -> bool:
        """
        Verifica la conectividad con Redis.
        
        Returns:
            True si Redis está disponible, False en caso contrario
        """
        if not self._enabled or not self._client:
            redis_connection_status.set(0)
            return False
        try:
            result = self._client.ping()
            redis_connection_status.set(1 if result else 0)
            return result
        except Exception:
            self._enabled = False
            redis_connection_status.set(0)
            return False
    
    def close(self) -> None:
        """Cierra las conexiones del pool."""
        if self._pool:
            try:
                self._pool.disconnect()
                logger.info("redis_pool_closed")
            except Exception as e:
                logger.warning("redis_pool_close_error", error=str(e))
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_redis_client(settings: Optional[Settings] = None) -> Optional[Redis]:
    """
    Obtiene un cliente Redis singleton.
    
    Args:
        settings: Configuración opcional (usa Settings() por defecto)
        
    Returns:
        Cliente Redis o None si no está disponible
    """
    global _redis_client, _redis_pool
    
    if _redis_client is not None and _redis_client.ping():
        return _redis_client
    
    if settings is None:
        settings = Settings()
    
    pool = create_redis_pool(settings)
    if not pool:
        return None
    
    try:
        _redis_pool = pool
        _redis_client = Redis(connection_pool=pool)
        _redis_client.ping()
        redis_connection_status.set(1)
        logger.info("redis_singleton_initialized")
        return _redis_client
    except Exception as e:
        redis_connection_status.set(0)
        logger.warning("redis_singleton_init_failed", error=str(e))
        return None


def reset_redis_client() -> None:
    """Resetea el cliente singleton (útil para tests)."""
    global _redis_client, _redis_pool
    
    if _redis_client:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None
    
    if _redis_pool:
        try:
            _redis_pool.disconnect()
        except Exception:
            pass
        _redis_pool = None
    
    redis_connection_status.set(0)

