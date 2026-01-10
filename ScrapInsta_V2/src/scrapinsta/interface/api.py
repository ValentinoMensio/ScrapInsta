from __future__ import annotations

import os
from typing import List, Optional, Dict, Any
from uuid import uuid4
import time

from fastapi import FastAPI, Header, HTTPException, Path, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import json
from pydantic import BaseModel, Field

from scrapinsta.config.settings import Settings
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL
from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL
from scrapinsta.infrastructure.auth.jwt_auth import create_access_token, verify_token, get_client_id_from_token
from scrapinsta.infrastructure.redis import RedisClient, DistributedRateLimiter, get_redis_client
from passlib.context import CryptContext
from scrapinsta.crosscutting.logging_config import (
    configure_structured_logging,
    get_logger,
    bind_request_context,
    clear_request_context,
)
from scrapinsta.crosscutting.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    rate_limit_hits_total,
    get_metrics,
    get_metrics_content_type,
    get_metrics_json,
    get_metrics_summary,
)
from scrapinsta.crosscutting.exceptions import (
    ScrapInstaHTTPError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    InternalServerError,
    BadRequestError,
    ClientNotFoundError,
    JobNotFoundError,
    InvalidScopeError,
    JobOwnershipError,
)

configure_structured_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
)
logger = get_logger("api")

app = FastAPI(title="ScrapInsta Send API", version="0.1.0")

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


app.add_middleware(ObservabilityMiddleware)

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


app.add_middleware(SecurityMiddleware)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in CORS_ORIGINS if origin.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
        max_age=3600,
    )
    logger.info("cors_enabled", origins=CORS_ORIGINS)
else:
    logger.info("cors_disabled", message="CORS deshabilitado (ningún origen permitido)")

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
    """
    # Mapear excepciones de dominio a excepciones HTTP
    from scrapinsta.domain.ports.browser_port import (
        BrowserPortError,
        BrowserAuthError,
        BrowserConnectionError,
        BrowserRateLimitError,
    )
    from scrapinsta.domain.ports.profile_repo import (
        ProfileRepoError,
        ProfileValidationError,
        ProfilePersistenceError,
    )
    from scrapinsta.domain.ports.followings_repo import (
        FollowingsRepoError,
        FollowingsValidationError,
        FollowingsPersistenceError,
    )
    
    if isinstance(exc, BrowserAuthError):
        http_exc = UnauthorizedError(
            f"Error de autenticación: {str(exc)}",
            details={"username": exc.username} if exc.username else {},
        )
    elif isinstance(exc, BrowserRateLimitError):
        http_exc = RateLimitError(
            f"Límite de tasa excedido: {str(exc)}",
            details={"username": exc.username} if exc.username else {},
        )
    elif isinstance(exc, (BrowserConnectionError, BrowserPortError)):
        http_exc = InternalServerError(
            f"Error del navegador: {str(exc)}",
            details={"code": exc.code, "username": exc.username} if hasattr(exc, "code") else {},
            cause=exc,
        )
    elif isinstance(exc, (ProfileValidationError, FollowingsValidationError)):
        http_exc = BadRequestError(
            f"Error de validación: {str(exc)}",
            cause=exc,
        )
    elif isinstance(exc, (ProfilePersistenceError, FollowingsPersistenceError)):
        http_exc = InternalServerError(
            f"Error de persistencia: {str(exc)}",
            error_code="DATABASE_ERROR",
            cause=exc,
        )
    elif isinstance(exc, (ProfileRepoError, FollowingsRepoError)):
        http_exc = InternalServerError(
            f"Error del repositorio: {str(exc)}",
            cause=exc,
        )
    else:
        http_exc = InternalServerError(
            "Error interno del servidor",
            cause=exc,
        )
    logger.exception(
        "unhandled_exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
        method=request.method,
        http_error_code=http_exc.error_code,
    )
    
    return await scrapinsta_http_exception_handler(request, http_exc)

API_SHARED_SECRET = os.getenv("API_SHARED_SECRET")

# Clientes con scopes y rate limit (opcional, JSON en env API_CLIENTS_JSON)
_CLIENTS: Dict[str, Dict[str, Any]] = {}
try:
    raw = os.getenv("API_CLIENTS_JSON")
    if raw:
        _CLIENTS = json.loads(raw)
except Exception:
    _CLIENTS = {}

REQUIRE_HTTPS = os.getenv("REQUIRE_HTTPS", "false").lower() in ("1", "true", "yes")

class _RateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, float]] = {}

    def allow(self, key: str, rpm: int) -> bool:
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

_rate = _RateLimiter()


def _normalize(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    v = str(s).strip().lower()
    return v or None


def _auth_client(x_api_key: Optional[str], authorization: Optional[str], x_client_id: Optional[str]) -> Dict[str, Any]:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = verify_token(token)
        if payload:
            client_id = payload.get("client_id")
            if client_id:
                client = _client_repo.get_by_id(client_id)
                if not client:
                    raise ClientNotFoundError(f"Cliente '{client_id}' no encontrado")
                if client.get("status") != "active":
                    raise ForbiddenError(f"Cliente '{client_id}' no está activo")
                limits = _client_repo.get_limits(client_id) or {}
                return {
                    "id": client_id,
                    "scopes": payload.get("scopes", ["fetch", "analyze", "send"]),
                    "rate": limits.get("requests_per_minute", 60)
                }
        raise UnauthorizedError("Token inválido o expirado")

    provided: Optional[str] = None
    if x_api_key and x_api_key.strip():
        provided = x_api_key.strip()

    if _CLIENTS:
        cid = (x_client_id or "").strip()
        if not cid or cid not in _CLIENTS:
            raise UnauthorizedError("Cliente inválido")
        entry = _CLIENTS[cid]
        if not provided or provided != entry.get("key"):
            raise UnauthorizedError("API key inválida")
        return {"id": cid, "scopes": entry.get("scopes") or [], "rate": (entry.get("rate") or {}).get("rpm", 60)}

    if not API_SHARED_SECRET:
        raise InternalServerError(
            "API no configurada (falta API_SHARED_SECRET)",
            error_code="CONFIGURATION_ERROR"
        )
    if not provided or provided != API_SHARED_SECRET:
        raise UnauthorizedError("API key inválida")
    return {"id": "default", "scopes": ["fetch","analyze","send"], "rate": 60}


def _enforce_https(req: Request) -> None:
    """Valida que la request venga por HTTPS. Soporta proxies reversos (X-Forwarded-Proto)."""
    if not REQUIRE_HTTPS:
        return
    
    proto = req.headers.get("x-forwarded-proto") or req.url.scheme
    
    if (proto or "").lower() != "https":
        logger.warning(
            "https_required_violation",
            method=req.method,
            path=req.url.path,
            scheme=proto,
            forwarded_proto=req.headers.get("x-forwarded-proto"),
            client_host=req.client.host if req.client else None,
        )
        raise BadRequestError(
            "Se requiere HTTPS para esta operación",
            details={"scheme": proto, "required": "https"}
        )


def _check_scope(client: Dict[str, Any], scope: str) -> None:
    scopes = client.get("scopes") or []
    if scope not in scopes:
        raise InvalidScopeError(
            f"Scope '{scope}' requerido pero no disponible",
            details={"required_scope": scope, "available_scopes": scopes}
        )


def _rate_limit(client: Dict[str, Any], req: Request) -> None:
    rpm = int(client.get("rate") or 60)
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "-").split(",")[0].strip()
    endpoint = req.url.path
    
    # Intentar usar rate limiting distribuido (Redis)
    if _distributed_rate_limiter.enabled:
        # Rate limit por cliente
        allowed, retry_after = _distributed_rate_limiter.allow(f"client:{client['id']}", rpm)
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
        allowed, retry_after = _distributed_rate_limiter.allow(f"ip:{ip}", ip_rpm)
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
        if not _rate.allow(f"client:{client['id']}", rpm):
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
        if not _rate.allow(f"ip:{ip}", max(60, rpm)):
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


def _get_client_account(x_account: Optional[str]) -> str:
    acc = _normalize(x_account)
    if not acc:
        raise BadRequestError("Falta X-Account")
    return acc


# =========================================================
# Schemas

class LoginRequest(BaseModel):
    api_key: str = Field(..., description="API key del cliente")

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    client_id: str


class PullRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100, description="Máximo de tareas a tomar")


class PulledTask(BaseModel):
    job_id: str
    task_id: str
    dest_username: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class PullResponse(BaseModel):
    items: List[PulledTask]


class ResultRequest(BaseModel):
    job_id: str
    task_id: str
    ok: bool
    error: Optional[str] = None
    # Para registrar el ledger cuando ok=true (evita SELECT extra)
    dest_username: Optional[str] = None


class JobSummaryResponse(BaseModel):
    queued: int
    sent: int
    ok: int
    error: int


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    client = _client_repo.get_by_api_key(body.api_key)
    if not client:
        raise UnauthorizedError("API key inválida")
    
    if client.get("status") != "active":
        raise ForbiddenError("Cliente suspendido o eliminado")
    
    access_token = create_access_token({
        "client_id": client["id"],
        "scopes": ["fetch", "analyze", "send"]
    })
    
    return LoginResponse(
        access_token=access_token,
        client_id=client["id"]
    )

@app.post("/api/send/pull", response_model=PullResponse)
def pull_tasks(
    body: PullRequest,
    x_account: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Lease de tareas 'queued' para esta cuenta cliente. Las pasa a 'sent' y devuelve payload.
    Pensado para 'send_message'. Idempotente con SKIP LOCKED (MySQL 8+).
    """
    _enforce_https(request)
    client = _auth_client(x_api_key, authorization, x_client_id)
    _check_scope(client, "send")
    _rate_limit(client, request)
    account = _get_client_account(x_account)
    
    # Bind contexto adicional
    bind_request_context(
        client_id=client.get("id"),
        account=account,
    )
    
    logger.info(
        "pull_tasks_requested",
        account=account,
        limit=body.limit,
    )

    client_id = client.get("id")
    rows = _job_store.lease_tasks(account_id=account, limit=body.limit, client_id=client_id)

    items: List[PulledTask] = []
    for r in rows:
        items.append(
            PulledTask(
                job_id=r["job_id"],
                task_id=r["task_id"],
                dest_username=r.get("username"),
                payload=r.get("payload"),
            )
        )
    return PullResponse(items=items)


@app.post("/api/send/result")
def post_result(
    body: ResultRequest,
    x_account: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Reporte de resultado de envío (ok/error).
    Si ok, registra ledger (client_username + dest_username) para dedupe por cuenta.
    """
    _enforce_https(request)
    client = _auth_client(x_api_key, authorization, x_client_id)
    _check_scope(client, "send")
    _rate_limit(client, request)
    account = _get_client_account(x_account)
    client_id = client.get("id")

    # Marcar estado de la task
    try:
        if body.ok:
            _job_store.mark_task_ok(body.job_id, body.task_id, result=None)
        else:
            _job_store.mark_task_error(body.job_id, body.task_id, error=body.error or "error")
    except Exception as e:
        raise InternalServerError(
            f"Error al actualizar estado de tarea: {str(e)}",
            error_code="DATABASE_ERROR",
            cause=e,
        )

    if body.ok and (body.dest_username and body.dest_username.strip()):
        try:
            _job_store.register_message_sent(
                account,
                body.dest_username.strip(),
                body.job_id,
                body.task_id,
                client_id=client_id
            )
        except Exception:
            pass

    try:
        if _job_store.all_tasks_finished(body.job_id):
            _job_store.mark_job_done(body.job_id)
    except Exception:
        pass

    return {"status": "ok"}


@app.get("/health")
def health():
    """
    Health check básico: verifica conectividad con BD.
    Usado para verificar que el servicio está vivo.
    """
    try:
        _job_store.pending_jobs()
        return {"ok": True, "status": "healthy"}
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {"ok": False, "status": "unhealthy", "error": str(e)}


@app.get("/ready")
def ready():
    """
    Readiness check: verifica que el servicio está listo para recibir tráfico.
    Verifica BD y dependencias críticas.
    """
    checks = {
        "database": False,
    }
    all_ok = True

    # Verificar BD
    try:
        _job_store.pending_jobs()
        checks["database"] = True
    except Exception as e:
        logger.error("readiness_check_failed", component="database", error=str(e))
        all_ok = False

    status_code = 200 if all_ok else 503
    return Response(
        content=json.dumps({
            "ok": all_ok,
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        }),
        status_code=status_code,
        media_type="application/json",
    )


@app.get("/live")
def live():
    """
    Liveness check: verifica que el proceso está vivo.
    Siempre retorna OK si el proceso está corriendo.
    """
    return {"ok": True, "status": "alive"}


@app.get("/metrics")
def metrics():
    """
    Endpoint de métricas Prometheus (formato Prometheus estándar).
    Expone todas las métricas del sistema en formato Prometheus para scraping.
    """
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type(),
    )


@app.get("/metrics/json")
def metrics_json():
    """
    Endpoint de métricas en formato JSON legible.
    Retorna todas las métricas organizadas por categoría en formato JSON.
    """
    return get_metrics_json()


@app.get("/metrics/summary")
def metrics_summary():
    """
    Endpoint de resumen de métricas.
    Retorna un resumen legible de las métricas más importantes:
    - Requests HTTP por endpoint y status
    - Latencia promedio por endpoint
    - Tareas procesadas por tipo
    - Jobs activos
    - Conexiones de BD
    - Rate limit hits
    - Workers activos
    """
    return get_metrics_summary()

class EnqueueFollowingsRequest(BaseModel):
    target_username: str
    limit: int = Field(default=10, ge=1, le=100)

class EnqueueResponse(BaseModel):
    job_id: str

@app.post("/ext/followings/enqueue", response_model=EnqueueResponse)
def enqueue_followings(
    body: EnqueueFollowingsRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_account: Optional[str] = Header(None),   # <-- ahora recibimos la cuenta del cliente
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Crea un Job 'fetch_followings' para extraer followings de body.target_username
    con límite body.limit. La cuenta cliente viene en X-Account y se usará para
    enrutar la task a ese worker y luego deduplicar envíos en ledger.
    """
    _enforce_https(request)
    client = _auth_client(x_api_key, authorization, x_client_id)
    _check_scope(client, "fetch")
    _rate_limit(client, request)

    client_account = _get_client_account(x_account)  # valida y normaliza

    # Bind contexto
    bind_request_context(
        client_id=client.get("id"),
        account=client_account,
    )

    logger.info(
        "enqueue_followings_requested",
        target_username=body.target_username,
        limit=body.limit,
        client_account=client_account,
    )

    target = (body.target_username or "").strip().lower()
    if not target:
        raise BadRequestError("target_username vacío")

    job_id = f"job:{uuid4().hex}"

    client_id = client.get("id")
    try:
        _job_store.create_job(
            job_id=job_id,
            kind="fetch_followings",
            priority=5,
            batch_size=1,
            extra={"limit": body.limit, "source": "ext", "client_account": client_account},
            total_items=1,
            client_id=client_id,
        )
    except Exception as e:
        raise InternalServerError(f"create_job failed: {e}", error_code="DATABASE_ERROR", cause=e)

    try:
        seed_task_id = f"{job_id}:fetch_followings:{target}"
        _job_store.add_task(
            job_id=job_id,
            task_id=seed_task_id,
            correlation_id=job_id,
            account_id=None,
            username=target,
            payload={"username": target, "limit": body.limit, "client_account": client_account},
            client_id=client_id,
        )
    except Exception as e:
        raise InternalServerError(f"add_task failed: {e}", error_code="DATABASE_ERROR", cause=e)

    return EnqueueResponse(job_id=job_id)


@app.get("/jobs/{job_id}/summary", response_model=JobSummaryResponse)
def job_summary(
    job_id: str = Path(..., min_length=1),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    _enforce_https(request)
    client = _auth_client(x_api_key, authorization, x_client_id)
    _rate_limit(client, request)
    client_id = client.get("id")
    
    job_client_id = _job_store.get_job_client_id(job_id)
    if not job_client_id:
        raise JobNotFoundError(f"Job '{job_id}' no encontrado")
    if job_client_id != client_id:
        raise JobOwnershipError(
            f"El job '{job_id}' no pertenece al cliente '{client_id}'",
            details={"job_id": job_id, "client_id": client_id, "job_client_id": job_client_id}
        )
    
    try:
        s = _job_store.job_summary(job_id, client_id=client_id)
        safe = {
            "queued": int(s.get("queued") or 0),
            "sent":   int(s.get("sent")   or 0),
            "ok":     int(s.get("ok")     or 0),
            "error":  int(s.get("error")  or 0),
        }
        return JobSummaryResponse(**safe)
    except Exception as e:
        raise InternalServerError(f"job_summary failed: {e}", error_code="DATABASE_ERROR", cause=e)



class EnqueueAnalyzeRequest(BaseModel):
    usernames: List[str] = Field(default_factory=list)
    batch_size: int = Field(default=25, ge=1, le=200)
    priority: int = Field(default=5, ge=1, le=10)
    extra: Optional[Dict[str, Any]] = None

class EnqueueAnalyzeResponse(BaseModel):
    job_id: str
    total_items: int

@app.post("/ext/analyze/enqueue", response_model=EnqueueAnalyzeResponse)
def enqueue_analyze_profile(
    body: EnqueueAnalyzeRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Crea un Job 'analyze_profile' para que lo ejecuten los workers del servidor.
    (Esto NO envía mensajes: solo analiza).
    """
    _enforce_https(request)
    client = _auth_client(x_api_key, authorization, x_client_id)
    _check_scope(client, "analyze")
    _rate_limit(client, request)

    usernames = [str(u).strip().lower() for u in (body.usernames or []) if str(u).strip()]
    if not usernames:
        raise BadRequestError("usernames vacío")

    job_id = f"job:{uuid4().hex}"

    client_id = client.get("id")
    try:
        _job_store.create_job(
            job_id=job_id,
            kind="analyze_profile",
            priority=body.priority,
            batch_size=body.batch_size,
            extra=body.extra or {},
            total_items=len(usernames),
            client_id=client_id,
        )
    except Exception as e:
        raise InternalServerError(f"create_job failed: {e}", error_code="DATABASE_ERROR", cause=e)

    for u in usernames:
        try:
            task_id = f"{job_id}:analyze_profile:{u}"
            _job_store.add_task(
                job_id=job_id,
                task_id=task_id,
                correlation_id=job_id,
                account_id=None,
                username=u,
                payload={"username": u, **(body.extra or {})},
                client_id=client_id,
            )
        except Exception:
            pass

    return EnqueueAnalyzeResponse(job_id=job_id, total_items=len(usernames))
