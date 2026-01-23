from __future__ import annotations

import os
from typing import Optional, Any
import json

from fastapi import FastAPI, HTTPException, Request, Response

from scrapinsta.config.settings import Settings
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL
from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL
from scrapinsta.infrastructure.redis import RedisClient, DistributedRateLimiter
from scrapinsta.interface.dependencies import Dependencies, get_dependencies
from passlib.context import CryptContext
from scrapinsta.crosscutting.logging_config import (
    configure_structured_logging,
    get_logger,
    bind_request_context,
)
from scrapinsta.crosscutting.exceptions import (
    ScrapInstaHTTPError,
    UnauthorizedError,
    RateLimitError,
    InternalServerError,
    BadRequestError,
)

configure_structured_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
)
logger = get_logger("api")

# Variables globales para compatibilidad hacia atrás
# Se pueden sobrescribir usando el app factory con dependencias inyectadas
_settings: Optional[Settings] = None
_job_store: Optional[Any] = None
_client_repo: Optional[Any] = None
_redis_client_wrapper: Optional[RedisClient] = None
_redis_client: Optional[Any] = None
_distributed_rate_limiter: Optional[DistributedRateLimiter] = None
pwd_context: Optional[CryptContext] = None

# Inicialización lazy de dependencias globales (para compatibilidad)
def _init_globals() -> None:
    """Inicializa variables globales si no están ya inicializadas."""
    global _settings, _job_store, _client_repo, _redis_client_wrapper
    global _redis_client, _distributed_rate_limiter, pwd_context
    
    if _settings is None:
        _settings = Settings()
        logger.info("api_started", db_dsn=_settings.db_dsn)
        _job_store = JobStoreSQL(_settings.db_dsn)
        _client_repo = ClientRepoSQL(_settings.db_dsn)
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Redis para rate limiting distribuido y caché
        _redis_client_wrapper = RedisClient(_settings)
        _redis_client = _redis_client_wrapper.client
        _distributed_rate_limiter = DistributedRateLimiter(_redis_client)
        
        # Fallback al rate limiter en memoria si Redis no está disponible
        if not _distributed_rate_limiter.enabled:
            logger.warning("redis_unavailable", fallback="memory_rate_limiter")


def _get_deps_from_request(request: Optional[Request] = None) -> Dependencies:
    """
    Obtiene dependencias desde app.state o usa las globales como fallback.
    
    Útil para endpoints que pueden recibir request y acceder a app.state.dependencies.
    """
    if request and hasattr(request.app.state, 'dependencies'):
        return request.app.state.dependencies
    _init_globals()
    return get_dependencies()


def _setup_app(app: FastAPI, dependencies: Optional[Dependencies] = None) -> None:
    """
    Configura la aplicación FastAPI con middlewares, CORS, exception handlers y routes.
    
    Args:
        app: Aplicación FastAPI a configurar
        dependencies: Dependencias a usar (se obtienen de app.state si no se proveen)
    """
    if dependencies is None:
        dependencies = getattr(app.state, 'dependencies', None) or get_dependencies()
    
    # Configurar CORS
    cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
    if cors_origins:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Trace-ID"],
            max_age=3600,
        )
        logger.info("cors_enabled", origins=cors_origins)
    else:
        logger.info("cors_disabled", message="CORS deshabilitado (ningún origen permitido)")


# Inicializar globales para compatibilidad
_init_globals()

# Crear app usando factory para tener DI container
# Esto permite inyectar dependencias en tests y mantener compatibilidad
try:
    from scrapinsta.interface.app_factory import create_app as _create_app_factory
    _deps = get_dependencies()
    app = _create_app_factory(_deps)
    logger.info("app_created_via_factory", message="App creada usando factory con DI")
except Exception as e:
    # Fallback: crear app directamente si factory falla
    logger.warning("app_factory_failed", error=str(e), message="Usando configuración directa")
    app = FastAPI(title="ScrapInsta Send API", version="0.1.0")
    app.state.dependencies = get_dependencies()


# Middlewares extraídos a interface/middleware/
from scrapinsta.interface.middleware import ObservabilityMiddleware, SecurityMiddleware

# Routers extraídos a interface/routers/
from scrapinsta.interface.routers import (
    auth_router,
    send_router,
    external_router,
    health_router,
)


@app.exception_handler(ScrapInstaHTTPError)
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


@app.exception_handler(HTTPException)
async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    """
    Handler para HTTPException de FastAPI.
    Convierte a formato consistente de ScrapInsta.
    """
    # Mapear códigos comunes a nuestros códigos de error
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


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handler genérico para excepciones no manejadas.
    Captura todas las excepciones y las convierte a respuestas HTTP consistentes.
    
    Usa ExceptionMapper con registry pattern para mapear excepciones de dominio
    a excepciones HTTP de forma centralizada y extensible.
    """
    from scrapinsta.crosscutting.exception_mapping import get_exception_mapper
    
    # Usar el mapper para convertir la excepción
    mapper = get_exception_mapper()
    http_exc = mapper.map(exc)
    
    # Logging estructurado
    logger.exception(
        "unhandled_exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
        method=request.method,
        http_error_code=http_exc.error_code,
    )
    
    return await scrapinsta_http_exception_handler(request, http_exc)

# Funciones de autenticación y rate limiting extraídas a interface/auth/
# Importar desde módulos dedicados
from scrapinsta.interface.auth import (
    authenticate_client,
    check_scope,
    enforce_https,
    get_client_account,
    rate_limit,
)

# Re-exportar variables para compatibilidad con tests
from scrapinsta.interface.auth.authentication import (
    API_SHARED_SECRET,
    _CLIENTS,
    REQUIRE_HTTPS,
)

# Aliases para compatibilidad hacia atrás (si hay código que aún usa _auth_client, etc.)
_auth_client = authenticate_client
_check_scope = check_scope
_enforce_https = enforce_https
_rate_limit = rate_limit
_get_client_account = get_client_account


# =========================================================
# Configuración final de la app (si no se usó factory)
# =========================================================

# Si el app no tiene middlewares configurados, configurarlos ahora
# (esto solo ocurre si no se usó el factory)
if not hasattr(app.state, '_configured'):
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(SecurityMiddleware)
    _setup_app(app)
    app.state._configured = True

# Registrar routers
app.include_router(auth_router)
app.include_router(send_router)
app.include_router(external_router)
app.include_router(health_router)
