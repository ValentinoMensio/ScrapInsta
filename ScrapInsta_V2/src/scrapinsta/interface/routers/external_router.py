"""Router para endpoints externos (enqueue jobs, consultar estado)."""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Header, Path, Request
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

    job_id = f"job:{uuid4().hex}"

    client_id = client.get("id")
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


@router.get("/jobs/{job_id}/summary", response_model=JobSummaryResponse)
def job_summary(
    job_id: str = Path(..., min_length=1),
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

