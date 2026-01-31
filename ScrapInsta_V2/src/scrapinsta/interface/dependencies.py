"""
Contenedor de dependencias para la aplicación.

Proporciona un lugar centralizado para crear y gestionar dependencias,
facilitando testing y configuración dinámica.
"""
from __future__ import annotations

from typing import Optional
import os
from passlib.context import CryptContext

from scrapinsta.config.settings import Settings
from scrapinsta.domain.ports.job_store import JobStorePort
from scrapinsta.domain.ports.client_repo import ClientRepo
from scrapinsta.domain.ports.profile_repo import ProfileRepository
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL
from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL
from scrapinsta.infrastructure.db.profile_repo_sql import ProfileRepoSQL
from scrapinsta.infrastructure.db.connection_provider import ConnectionProvider
from scrapinsta.infrastructure.redis import RedisClient, DistributedRateLimiter
from scrapinsta.crosscutting.logging_config import get_logger

logger = get_logger("dependencies")

APP_ENV = os.getenv("APP_ENV", "development").lower()
REQUIRE_REDIS_RATE_LIMITER = os.getenv(
    "REQUIRE_REDIS_RATE_LIMITER",
    "true" if APP_ENV == "production" else "false",
).lower() in ("1", "true", "yes")


class Dependencies:
    """
    Contenedor de dependencias de la aplicación.
    
    Centraliza la creación y gestión de dependencias para facilitar
    testing, configuración dinámica y reusabilidad.
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        job_store: Optional[JobStorePort] = None,
        client_repo: Optional[ClientRepo] = None,
        profile_repo: Optional[ProfileRepository] = None,
        redis_client: Optional[RedisClient] = None,
        distributed_rate_limiter: Optional[DistributedRateLimiter] = None,
    ) -> None:
        """
        Inicializa el contenedor de dependencias.
        
        Args:
            settings: Configuración de la aplicación (se crea si no se provee)
            job_store: JobStore a usar (se crea si no se provee)
            client_repo: ClientRepo a usar (se crea si no se provee)
            redis_client: Cliente Redis (se crea si no se provee)
            distributed_rate_limiter: Rate limiter distribuido (se crea si no se provee)
        """
        self._settings = settings or Settings()
        self._job_store = job_store
        self._client_repo = client_repo
        self._profile_repo = profile_repo
        self._redis_client_wrapper = redis_client
        self._distributed_rate_limiter = distributed_rate_limiter
        self._pwd_context: Optional[CryptContext] = None
        
    @property
    def settings(self) -> Settings:
        """Configuración de la aplicación."""
        return self._settings
    
    @property
    def job_store(self) -> JobStorePort:
        """Repositorio de jobs y tareas."""
        if self._job_store is None:
            self._job_store = JobStoreSQL(self._settings.db_dsn)
            logger.debug("job_store_created", db_dsn=self._settings.db_dsn)
        return self._job_store
    
    @property
    def client_repo(self) -> ClientRepo:
        """Repositorio de clientes."""
        if self._client_repo is None:
            self._client_repo = ClientRepoSQL(self._settings.db_dsn)
            logger.debug("client_repo_created", db_dsn=self._settings.db_dsn)
        return self._client_repo

    @property
    def profile_repo(self) -> ProfileRepository:
        """Repositorio de perfiles."""
        if self._profile_repo is None:
            self._profile_repo = ProfileRepoSQL(ConnectionProvider(self._settings.db_dsn))
            logger.debug("profile_repo_created", db_dsn=self._settings.db_dsn)
        return self._profile_repo
    
    @property
    def redis_client_wrapper(self) -> RedisClient:
        """Wrapper del cliente Redis."""
        if self._redis_client_wrapper is None:
            self._redis_client_wrapper = RedisClient(self._settings)
            logger.debug("redis_client_created")
        return self._redis_client_wrapper
    
    @property
    def redis_client(self):
        """Cliente Redis (puede ser None si Redis no está disponible)."""
        return self.redis_client_wrapper.client
    
    @property
    def distributed_rate_limiter(self) -> DistributedRateLimiter:
        """Rate limiter distribuido (Redis o fallback en memoria)."""
        if self._distributed_rate_limiter is None:
            self._distributed_rate_limiter = DistributedRateLimiter(self.redis_client)
            if not self._distributed_rate_limiter.enabled:
                if REQUIRE_REDIS_RATE_LIMITER:
                    raise RuntimeError("Redis requerido para rate limiting en producción")
                logger.warning("redis_unavailable", fallback="memory_rate_limiter")
        return self._distributed_rate_limiter
    
    @property
    def pwd_context(self) -> CryptContext:
        """Contexto para hashing de contraseñas."""
        if self._pwd_context is None:
            self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return self._pwd_context


# Instancia global para compatibilidad hacia atrás
# Se puede sobrescribir en tests
_dependencies: Optional[Dependencies] = None


def get_dependencies() -> Dependencies:
    """
    Obtiene la instancia global de dependencias.
    
    Crea una nueva instancia si no existe (lazy initialization).
    Útil para compatibilidad hacia atrás con código existente.
    """
    global _dependencies
    if _dependencies is None:
        _dependencies = Dependencies()
    return _dependencies


def set_dependencies(deps: Dependencies) -> None:
    """
    Establece la instancia global de dependencias.
    
    Útil para testing o configuración dinámica.
    
    Args:
        deps: Instancia de Dependencies a usar
    """
    global _dependencies
    _dependencies = deps


def reset_dependencies() -> None:
    """
    Resetea la instancia global de dependencias.
    
    Útil para testing entre tests.
    """
    global _dependencies
    _dependencies = None

