"""Router para endpoints externos (enqueue jobs, consultar estado)."""
from __future__ import annotations

from typing import List, Optional, Dict, Any
import os
import json
import re
from uuid import uuid4

from fastapi import APIRouter, Header, Path, Query, Request
from pydantic import BaseModel, Field

from scrapinsta.crosscutting.logging_config import get_logger, bind_request_context
from scrapinsta.crosscutting.exceptions import (
    BadRequestError,
    InternalServerError,
    JobNotFoundError,
    JobOwnershipError,
)
from scrapinsta.interface.auth import authenticate_client, check_scope, enforce_https, get_client_account, rate_limit
from scrapinsta.interface.dependencies import get_dependencies

logger = get_logger("routers.external")

router = APIRouter(tags=["external"])

APP_ENV = os.getenv("APP_ENV", "development").lower()
MAX_FOLLOWINGS_LIMIT = int(os.getenv("MAX_FOLLOWINGS_LIMIT", "100"))
MAX_ANALYZE_USERNAMES = int(os.getenv("MAX_ANALYZE_USERNAMES", "200" if APP_ENV == "production" else "500"))
MAX_ANALYZE_BATCH_SIZE = int(os.getenv("MAX_ANALYZE_BATCH_SIZE", "200"))
MAX_USERNAME_LENGTH = int(os.getenv("MAX_USERNAME_LENGTH", "64"))
MAX_EXTRA_BYTES = int(os.getenv("MAX_EXTRA_BYTES", "20000"))
MAX_JOB_ID_LENGTH = int(os.getenv("MAX_JOB_ID_LENGTH", "64"))
REQUIRE_JOB_ID_PREFIX = os.getenv(
    "REQUIRE_JOB_ID_PREFIX",
    "true" if APP_ENV == "production" else "false",
).lower() in ("1", "true", "yes")
JOB_ID_REGEX = r"^job:[a-f0-9]{32}$" if REQUIRE_JOB_ID_PREFIX else r"^.+$"
USERNAME_REGEX = os.getenv("USERNAME_REGEX", r"^[a-zA-Z0-9._]{2,30}$")


def _get_deps_from_request(request: Request):
    """Obtiene dependencias desde request.app.state o usa get_dependencies()."""
    if hasattr(request.app.state, 'dependencies'):
        return request.app.state.dependencies
    return get_dependencies()


class EnqueueFollowingsRequest(BaseModel):
    target_username: str
    limit: int = Field(default=10, ge=1, le=100)


class EnqueueResponse(BaseModel):
    job_id: str


class EnqueueAnalyzeRequest(BaseModel):
    usernames: List[str] = Field(default_factory=list)
    batch_size: int = Field(default=25, ge=1, le=200)
    priority: int = Field(default=5, ge=1, le=10)
    extra: Optional[Dict[str, Any]] = None


class EnqueueAnalyzeResponse(BaseModel):
    job_id: str
    total_items: int


class JobSummaryResponse(BaseModel):
    queued: int
    sent: int
    ok: int
    error: int


class JobListItem(BaseModel):
    id: str
    kind: str
    status: str
    created_at: str


class JobsListResponse(BaseModel):
    jobs: List[JobListItem]


class FollowingsRecipientsResponse(BaseModel):
    """Usernames de followings de un job fetch_followings para usar como destinatarios de DM."""
    job_id: str
    target_username: str
    usernames: List[str]
    total: int
    already_sent_count: int
    pending_count: int


# =====================================================
# Constantes para Send Messages
# =====================================================
MAX_SEND_USERNAMES = int(os.getenv("MAX_SEND_USERNAMES", "50"))
MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "1000"))
MIN_MESSAGE_LENGTH = int(os.getenv("MIN_MESSAGE_LENGTH", "10"))
MAX_CLIENT_MESSAGES_PER_DAY = int(os.getenv("MAX_CLIENT_MESSAGES_PER_DAY", "100"))
MAX_CLIENT_MESSAGES_PER_HOUR = int(os.getenv("MAX_CLIENT_MESSAGES_PER_HOUR", "20"))


class EnqueueSendRequest(BaseModel):
    """Request para crear un job de envío de mensajes."""
    usernames: List[str] = Field(..., min_length=1, description="Lista de usernames destino")
    message_template: str = Field(..., min_length=MIN_MESSAGE_LENGTH, max_length=MAX_MESSAGE_LENGTH, description="Mensaje a enviar")
    source_job_id: Optional[str] = Field(None, description="Job ID origen (fetch/analyze) para trazabilidad")
    dry_run: bool = Field(default=True, description="Si es True, no envía realmente (para testing)")


class EnqueueSendResponse(BaseModel):
    job_id: str
    total_items: int
    daily_remaining: int
    hourly_remaining: int


class AnalyzedProfileItem(BaseModel):
    username: str
    followers: Optional[int] = None
    following: Optional[int] = None
    posts: Optional[int] = None
    verified: Optional[bool] = None
    private: Optional[bool] = None
    bio: Optional[str] = None
    success_score: Optional[float] = None


class AnalyzedProfilesResponse(BaseModel):
    job_id: str
    profiles: List[AnalyzedProfileItem]
    total: int


@router.post("/ext/followings/enqueue", response_model=EnqueueResponse)
def enqueue_followings(
    body: EnqueueFollowingsRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_account: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Crea un Job 'fetch_followings' para extraer followings de body.target_username
    con límite body.limit. La cuenta cliente viene en X-Account y se usará para
    enrutar la task a ese worker y luego deduplicar envíos en ledger.
    """
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    check_scope(client, "fetch")
    rate_limit(client, request)

    client_account = get_client_account(x_account)  # valida y normaliza

    deps = _get_deps_from_request(request)
    job_store = deps.job_store

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
    if len(target) > MAX_USERNAME_LENGTH:
        raise BadRequestError(
            "target_username excede el máximo permitido",
            details={"max": MAX_USERNAME_LENGTH},
        )
    if not re.match(USERNAME_REGEX, target):
        raise BadRequestError("target_username inválido")
    if body.limit > MAX_FOLLOWINGS_LIMIT:
        raise BadRequestError(
            "limit excede el máximo permitido",
            details={"limit": body.limit, "max": MAX_FOLLOWINGS_LIMIT},
        )

    job_id = f"job:{uuid4().hex}"

    client_id = client.get("id")
    try:
        job_store.create_job(
            job_id=job_id,
            kind="fetch_followings",
            priority=5,
            batch_size=1,
            # Arquitectura: la API crea el Job; las Tasks las crea el dispatcher/router.
            # Guardamos el seed y config en extra_json para que el dispatcher pueda reconstruir el flujo.
            extra={
                "limit": body.limit,
                "source": "ext",
                "client_account": client_account,
                "target_username": target,
                "client_id": client_id,  # Guardar client_id en extra para fallback en dispatcher
            },
            total_items=1,
            client_id=client_id,
        )
    except Exception as e:
        raise InternalServerError(f"create_job failed: {e}", error_code="DATABASE_ERROR", cause=e)

    return EnqueueResponse(job_id=job_id)


@router.post("/ext/analyze/enqueue", response_model=EnqueueAnalyzeResponse)
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
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    check_scope(client, "analyze")
    rate_limit(client, request)

    deps = _get_deps_from_request(request)
    job_store = deps.job_store

    usernames = [str(u).strip().lower() for u in (body.usernames or []) if str(u).strip()]
    if not usernames:
        raise BadRequestError("usernames vacío")
    too_long = [u for u in usernames if len(u) > MAX_USERNAME_LENGTH]
    if too_long:
        raise BadRequestError(
            "usernames contiene valores demasiado largos",
            details={"max": MAX_USERNAME_LENGTH},
        )
    invalid = [u for u in usernames if not re.match(USERNAME_REGEX, u)]
    if invalid:
        raise BadRequestError("usernames contiene valores inválidos")
    if len(usernames) > MAX_ANALYZE_USERNAMES:
        raise BadRequestError(
            "usernames excede el máximo permitido",
            details={"count": len(usernames), "max": MAX_ANALYZE_USERNAMES},
        )
    if body.batch_size > MAX_ANALYZE_BATCH_SIZE:
        raise BadRequestError(
            "batch_size excede el máximo permitido",
            details={"batch_size": body.batch_size, "max": MAX_ANALYZE_BATCH_SIZE},
        )

    job_id = f"job:{uuid4().hex}"

    client_id = client.get("id")
    if body.extra:
        try:
            extra_size = len(json.dumps(body.extra, separators=(",", ":"), ensure_ascii=False))
        except Exception as e:
            raise BadRequestError("extra inválido", details={"error": str(e)})
        if extra_size > MAX_EXTRA_BYTES:
            raise BadRequestError(
                "extra excede el tamaño permitido",
                details={"bytes": extra_size, "max": MAX_EXTRA_BYTES},
            )
    try:
        job_store.create_job(
            job_id=job_id,
            kind="analyze_profile",
            priority=body.priority,
            batch_size=body.batch_size,
            # Arquitectura: API crea el Job; dispatcher/router crean las Tasks.
            # Guardamos los items en extra_json para reconstrucción idempotente tras reinicios.
            extra={**(body.extra or {}), "usernames": usernames},
            total_items=len(usernames),
            client_id=client_id,
        )
    except Exception as e:
        raise InternalServerError(f"create_job failed: {e}", error_code="DATABASE_ERROR", cause=e)

    return EnqueueAnalyzeResponse(job_id=job_id, total_items=len(usernames))


@router.post("/ext/send/enqueue", response_model=EnqueueSendResponse)
def enqueue_send_message(
    body: EnqueueSendRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_account: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Crea un Job 'send_message' para enviar DMs a los usernames especificados.
    
    Las tasks se crean en estado 'queued' y la extensión del cliente las
    obtiene via /api/send/pull y reporta resultados via /api/send/result.
    
    Multi-tenant: cada job está vinculado a un client_id y las tasks
    solo son visibles para ese cliente.
    
    Rate limiting:
    - Límite diario por cliente (configurable)
    - Límite por hora por cliente (configurable)
    """
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    check_scope(client, "send")
    rate_limit(client, request)
    
    client_account = get_client_account(x_account)  # La cuenta de IG del cliente
    client_id = client.get("id")
    
    deps = _get_deps_from_request(request)
    job_store = deps.job_store
    
    # Bind contexto
    bind_request_context(
        client_id=client_id,
        account=client_account,
    )
    
    # Validar usernames
    usernames = [str(u).strip().lower() for u in (body.usernames or []) if str(u).strip()]
    if not usernames:
        raise BadRequestError("usernames vacío")
    
    too_long = [u for u in usernames if len(u) > MAX_USERNAME_LENGTH]
    if too_long:
        raise BadRequestError(
            "usernames contiene valores demasiado largos",
            details={"max": MAX_USERNAME_LENGTH},
        )
    
    invalid = [u for u in usernames if not re.match(USERNAME_REGEX, u)]
    if invalid:
        raise BadRequestError(
            "usernames contiene valores inválidos",
            details={"invalid": invalid[:5]},  # Mostrar solo los primeros 5
        )
    
    if len(usernames) > MAX_SEND_USERNAMES:
        raise BadRequestError(
            "usernames excede el máximo permitido",
            details={"count": len(usernames), "max": MAX_SEND_USERNAMES},
        )
    
    # Validar mensaje
    message = (body.message_template or "").strip()
    if len(message) < MIN_MESSAGE_LENGTH:
        raise BadRequestError(
            "message_template muy corto",
            details={"min": MIN_MESSAGE_LENGTH, "actual": len(message)},
        )
    if len(message) > MAX_MESSAGE_LENGTH:
        raise BadRequestError(
            "message_template muy largo",
            details={"max": MAX_MESSAGE_LENGTH, "actual": len(message)},
        )
    
    # =====================================================
    # Rate Limiting por cliente (seguridad anti-abuso)
    # =====================================================
    limits = deps.client_repo.get_limits(client_id) or {}
    daily_limit = int(limits.get("messages_per_day", MAX_CLIENT_MESSAGES_PER_DAY))
    hourly_limit = int(limits.get("messages_per_hour", MAX_CLIENT_MESSAGES_PER_HOUR))
    
    # Contar mensajes enviados hoy
    sent_today = job_store.count_messages_sent_today(client_id) or 0
    # Contar tareas en vuelo (enviadas pero no confirmadas)
    inflight_today = job_store.count_tasks_sent_today(client_id) or 0
    # Contar tareas queued pendientes para este cliente
    queued_today = job_store.count_tasks_queued_today(client_id) or 0
    
    used_today = sent_today + inflight_today + queued_today
    daily_remaining = max(0, daily_limit - used_today)
    
    if daily_remaining <= 0:
        raise BadRequestError(
            "Límite diario de mensajes alcanzado",
            details={
                "limit": daily_limit,
                "sent_today": sent_today,
                "inflight": inflight_today,
                "queued": queued_today,
            },
        )
    
    # Contar mensajes de última hora
    sent_hour = job_store.count_messages_sent_last_hour(client_id) or 0
    inflight_hour = job_store.count_tasks_sent_last_hour(client_id) or 0
    queued_hour = job_store.count_tasks_queued_last_hour(client_id) or 0
    used_hour = sent_hour + inflight_hour + queued_hour
    hourly_remaining = max(0, hourly_limit - used_hour)
    
    if hourly_remaining <= 0:
        raise BadRequestError(
            "Límite por hora de mensajes alcanzado",
            details={
                "limit": hourly_limit,
                "sent_hour": sent_hour,
                "inflight": inflight_hour,
                "queued": queued_hour,
            },
        )
    
    # Limitar usernames a lo que queda disponible
    effective_usernames = usernames[:min(len(usernames), daily_remaining, hourly_remaining)]
    
    if len(effective_usernames) < len(usernames):
        logger.warning(
            "send_enqueue_truncated",
            client_id=client_id,
            requested=len(usernames),
            effective=len(effective_usernames),
            daily_remaining=daily_remaining,
            hourly_remaining=hourly_remaining,
        )
    
    # Filtrar usernames a los que ya se les envió (deduplicación)
    filtered_usernames = []
    for u in effective_usernames:
        try:
            if not job_store.was_message_sent(client_account, u):
                filtered_usernames.append(u)
        except Exception:
            filtered_usernames.append(u)  # En caso de error, incluir
    
    if not filtered_usernames:
        raise BadRequestError(
            "Todos los usernames ya recibieron mensaje de esta cuenta",
            details={"original_count": len(usernames)},
        )
    
    job_id = f"send:{uuid4().hex}"
    
    logger.info(
        "enqueue_send_requested",
        client_id=client_id,
        client_account=client_account,
        usernames_count=len(filtered_usernames),
        source_job_id=body.source_job_id,
        dry_run=body.dry_run,
    )
    
    try:
        job_store.create_job(
            job_id=job_id,
            kind="send_message",
            priority=5,
            batch_size=1,  # Una task a la vez para control de rate
            extra={
                "usernames": filtered_usernames,
                "message_template": message,
                "client_account": client_account,
                "source_job_id": body.source_job_id,
                "dry_run": body.dry_run,
                "client_id": client_id,
            },
            total_items=len(filtered_usernames),
            client_id=client_id,
        )
        # Crear una task por username para que el frontend pueda hacer pull vía /api/send/pull.
        # El envío lo hace la extensión desde la cuenta del cliente; los workers no participan.
        base_payload = {
            "message_template": message,
            "client_account": client_account,
            "source_job_id": body.source_job_id,
            "dry_run": body.dry_run,
        }
        for username in filtered_usernames:
            task_id = f"{job_id}:send_message:{username}"
            payload = {**base_payload, "target_username": username}
            job_store.add_task(
                job_id=job_id,
                task_id=task_id,
                correlation_id=job_id,
                account_id=client_account,
                username=username,
                payload=payload,
                client_id=client_id,
            )
    except Exception as e:
        raise InternalServerError(f"create_job failed: {e}", error_code="DATABASE_ERROR", cause=e)
    
    return EnqueueSendResponse(
        job_id=job_id,
        total_items=len(filtered_usernames),
        daily_remaining=daily_remaining - len(filtered_usernames),
        hourly_remaining=hourly_remaining - len(filtered_usernames),
    )


@router.get("/ext/analyze/{job_id}/profiles", response_model=AnalyzedProfilesResponse)
def get_analyzed_profiles(
    job_id: str = Path(..., min_length=1, max_length=MAX_JOB_ID_LENGTH),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Obtiene los perfiles analizados de un job de tipo analyze_profile.
    
    Útil para que el cliente vea los resultados y decida a quiénes enviar mensajes.
    Solo devuelve perfiles del job que pertenece al cliente autenticado.
    """
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    rate_limit(client, request)
    client_id = client.get("id")
    
    deps = _get_deps_from_request(request)
    job_store = deps.job_store
    profile_repo = deps.profile_repo
    
    # Verificar ownership del job
    job_client_id = job_store.get_job_client_id(job_id)
    if not job_client_id:
        # Intentar con prefijo analyze: si no lo tiene
        if not job_id.startswith("analyze:"):
            alt_job_id = f"analyze:{job_id}"
            job_client_id = job_store.get_job_client_id(alt_job_id)
            if job_client_id:
                job_id = alt_job_id
    
    if not job_client_id:
        raise JobNotFoundError(f"Job '{job_id}' no encontrado")
    
    if job_client_id != client_id:
        raise JobOwnershipError(
            f"El job '{job_id}' no pertenece al cliente '{client_id}'",
            details={"job_id": job_id, "client_id": client_id}
        )
    
    # Obtener los usernames analizados desde las tasks completadas
    try:
        usernames = job_store.get_completed_usernames(job_id)
    except Exception as e:
        raise InternalServerError(f"Error obteniendo usernames: {e}", error_code="DATABASE_ERROR", cause=e)
    
    if not usernames:
        return AnalyzedProfilesResponse(job_id=job_id, profiles=[], total=0)
    
    # Obtener datos de perfil para cada username
    profiles = []
    for username in usernames:
        try:
            profile_data = profile_repo.get_profile(username)
            if profile_data:
                profiles.append(AnalyzedProfileItem(
                    username=username,
                    followers=profile_data.get("followers"),
                    following=profile_data.get("following"),
                    posts=profile_data.get("posts"),
                    verified=profile_data.get("verified"),
                    private=profile_data.get("private"),
                    bio=profile_data.get("bio"),
                    success_score=profile_data.get("success_score"),
                ))
            else:
                # Si no hay datos, incluir solo el username
                profiles.append(AnalyzedProfileItem(username=username))
        except Exception:
            profiles.append(AnalyzedProfileItem(username=username))
    
    return AnalyzedProfilesResponse(
        job_id=job_id,
        profiles=profiles,
        total=len(profiles),
    )


@router.get("/jobs/{job_id}/summary", response_model=JobSummaryResponse)
def job_summary(
    job_id: str = Path(..., min_length=1, max_length=MAX_JOB_ID_LENGTH, pattern=JOB_ID_REGEX),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Obtiene un resumen del estado de un job.
    """
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    rate_limit(client, request)
    client_id = client.get("id")
    
    deps = _get_deps_from_request(request)
    job_store = deps.job_store
    
    job_client_id = job_store.get_job_client_id(job_id)
    if not job_client_id:
        raise JobNotFoundError(f"Job '{job_id}' no encontrado")
    if job_client_id != client_id:
        raise JobOwnershipError(
            f"El job '{job_id}' no pertenece al cliente '{client_id}'",
            details={"job_id": job_id, "client_id": client_id, "job_client_id": job_client_id}
        )
    
    try:
        s = job_store.job_summary(job_id, client_id=client_id)
        safe = {
            "queued": int(s.get("queued") or 0),
            "sent":   int(s.get("sent")   or 0),
            "ok":     int(s.get("ok")     or 0),
            "error":  int(s.get("error")  or 0),
        }
        return JobSummaryResponse(**safe)
    except Exception as e:
        raise InternalServerError(f"job_summary failed: {e}", error_code="DATABASE_ERROR", cause=e)


@router.get("/ext/jobs", response_model=JobsListResponse)
def list_jobs(
    limit: int = Query(5, ge=1, le=20),
    kind: Optional[str] = Query(None, description="Filtrar por tipo: fetch_followings, analyze_profile, send_message"),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """Lista los últimos jobs del cliente, más recientes primero."""
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    rate_limit(client, request)
    client_id = client.get("id")
    deps = _get_deps_from_request(request)
    job_store = deps.job_store
    rows = job_store.list_jobs_by_client(client_id, limit=limit, kind=kind)
    return JobsListResponse(jobs=[JobListItem(**r) for r in rows])


@router.get("/ext/jobs/{job_id}/followings-recipients", response_model=FollowingsRecipientsResponse)
def get_followings_recipients(
    job_id: str = Path(..., min_length=1, max_length=MAX_JOB_ID_LENGTH),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_account: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Para un job fetch_followings, devuelve los usernames extraídos (followings del target).
    Incluye cuántos ya recibieron mensaje de esta cuenta para mostrar pendientes.
    """
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    rate_limit(client, request)
    client_id = client.get("id")
    client_account = get_client_account(x_account)
    deps = _get_deps_from_request(request)
    job_store = deps.job_store

    job_client_id = job_store.get_job_client_id(job_id)
    if not job_client_id:
        raise JobNotFoundError(f"Job '{job_id}' no encontrado")
    if job_client_id != client_id:
        raise JobOwnershipError(
            f"El job '{job_id}' no pertenece al cliente",
            details={"job_id": job_id, "client_id": client_id},
        )

    meta = job_store.get_job_metadata(job_id)
    if (meta.get("kind") or "") != "fetch_followings":
        raise BadRequestError(
            "El job no es de tipo fetch_followings",
            details={"job_id": job_id, "kind": meta.get("kind")},
        )

    extra = meta.get("extra") or {}
    target_username = (extra.get("target_username") or "").strip().lower()
    if not target_username:
        raise BadRequestError("El job no tiene target_username en extra", details={"job_id": job_id})

    usernames = job_store.get_followings_for_owner(target_username, limit=500)
    already_sent = 0
    for u in usernames:
        try:
            if job_store.was_message_sent(client_account, u):
                already_sent += 1
        except Exception:
            pass
    pending_count = len(usernames) - already_sent
    return FollowingsRecipientsResponse(
        job_id=job_id,
        target_username=target_username,
        usernames=usernames,
        total=len(usernames),
        already_sent_count=already_sent,
        pending_count=pending_count,
    )


@router.get("/ext/jobs/{job_id}/analyze-recipients", response_model=FollowingsRecipientsResponse)
def get_analyze_recipients(
    job_id: str = Path(..., min_length=1, max_length=MAX_JOB_ID_LENGTH),
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_account: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    request: Request = None,
):
    """
    Para un job analyze_profile, devuelve los usernames analizados (completados).
    Incluye cuántos ya recibieron mensaje de esta cuenta para mostrar pendientes.
    Permite enviar DMs a ese usuario o grupo tras un análisis.
    """
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    rate_limit(client, request)
    client_id = client.get("id")
    client_account = get_client_account(x_account)
    deps = _get_deps_from_request(request)
    job_store = deps.job_store

    job_client_id = job_store.get_job_client_id(job_id)
    if not job_client_id:
        alt_job_id = f"analyze:{job_id}" if not job_id.startswith("analyze:") else None
        if alt_job_id:
            job_client_id = job_store.get_job_client_id(alt_job_id)
            if job_client_id:
                job_id = alt_job_id
    if not job_client_id:
        raise JobNotFoundError(f"Job '{job_id}' no encontrado")
    if job_client_id != client_id:
        raise JobOwnershipError(
            f"El job '{job_id}' no pertenece al cliente",
            details={"job_id": job_id, "client_id": client_id},
        )

    meta = job_store.get_job_metadata(job_id)
    if (meta.get("kind") or "") != "analyze_profile":
        raise BadRequestError(
            "El job no es de tipo analyze_profile",
            details={"job_id": job_id, "kind": meta.get("kind")},
        )

    try:
        usernames = job_store.get_completed_usernames(job_id)
    except Exception as e:
        raise InternalServerError(f"Error obteniendo usernames del job: {e}", error_code="DATABASE_ERROR", cause=e)

    already_sent = 0
    for u in usernames:
        try:
            if job_store.was_message_sent(client_account, u):
                already_sent += 1
        except Exception:
            pass
    pending_count = len(usernames) - already_sent
    return FollowingsRecipientsResponse(
        job_id=job_id,
        target_username="",
        usernames=usernames,
        total=len(usernames),
        already_sent_count=already_sent,
        pending_count=pending_count,
    )

