"""Router para operaciones de envío de mensajes."""
from __future__ import annotations

from typing import List, Optional, Dict, Any
import os
import re
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field, field_validator

from scrapinsta.crosscutting.logging_config import get_logger, bind_request_context
from scrapinsta.crosscutting.exceptions import BadRequestError, InternalServerError, RateLimitError
from scrapinsta.interface.auth import authenticate_client, check_scope, enforce_https, get_client_account, rate_limit
from scrapinsta.interface.dependencies import get_dependencies

logger = get_logger("routers.send")

router = APIRouter(prefix="/api/send", tags=["send"])

APP_ENV = os.getenv("APP_ENV", "development").lower()
MAX_PULL_LIMIT = int(os.getenv("MAX_PULL_LIMIT", "100"))
MAX_USERNAME_LENGTH = int(os.getenv("MAX_USERNAME_LENGTH", "64"))
MAX_ERROR_LENGTH = int(os.getenv("MAX_ERROR_LENGTH", "2000"))
MAX_JOB_ID_LENGTH = int(os.getenv("MAX_JOB_ID_LENGTH", "64"))
MAX_TASK_ID_LENGTH = int(os.getenv("MAX_TASK_ID_LENGTH", "160"))
MAX_CLIENT_MESSAGES_PER_DAY = int(os.getenv("MAX_CLIENT_MESSAGES_PER_DAY", "100"))


def _safe_int(value, default: int) -> int:
    if value is None:
        return default
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        return int(value)
    except Exception:
        return default
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
    job_id: str = Field(..., min_length=1, max_length=MAX_JOB_ID_LENGTH, pattern=JOB_ID_REGEX)
    task_id: str = Field(..., min_length=1, max_length=MAX_TASK_ID_LENGTH)
    ok: bool
    error: Optional[str] = None
    # Para registrar el ledger cuando ok=true (evita SELECT extra)
    dest_username: Optional[str] = None

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str, info):
        job_id = info.data.get("job_id")
        if REQUIRE_JOB_ID_PREFIX and job_id and not v.startswith(f"{job_id}:"):
            raise ValueError("task_id debe comenzar con job_id")
        return v


@router.post("/pull", response_model=PullResponse)
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
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    check_scope(client, "send")
    rate_limit(client, request)
    account = get_client_account(x_account)
    
    deps = _get_deps_from_request(request)
    
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
    if body.limit > MAX_PULL_LIMIT:
        raise BadRequestError(
            "limit excede el máximo permitido",
            details={"limit": body.limit, "max": MAX_PULL_LIMIT},
        )

    client_id = client.get("id")
    limits = deps.client_repo.get_limits(client_id) or {}
    daily_limit = _safe_int(limits.get("messages_per_day", MAX_CLIENT_MESSAGES_PER_DAY), MAX_CLIENT_MESSAGES_PER_DAY)
    if daily_limit > 0:
        sent_ok_today = _safe_int(deps.job_store.count_messages_sent_today(client_id), 0)
        sent_inflight_today = _safe_int(deps.job_store.count_tasks_sent_today(client_id), 0)
        used_today = sent_ok_today + sent_inflight_today
        remaining = daily_limit - used_today
        if remaining <= 0:
            raise RateLimitError(
                "Límite diario de mensajes alcanzado",
                details={
                    "client_id": client_id,
                    "limit": daily_limit,
                    "sent_ok_today": sent_ok_today,
                    "sent_inflight_today": sent_inflight_today,
                },
            )
        effective_limit = min(body.limit, remaining)
    else:
        effective_limit = body.limit
    rows = deps.job_store.lease_tasks(account_id=account, limit=effective_limit, client_id=client_id)

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


@router.post("/result")
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
    enforce_https(request)
    client = authenticate_client(x_api_key, authorization, x_client_id)
    check_scope(client, "send")
    rate_limit(client, request)
    account = get_client_account(x_account)
    client_id = client.get("id")

    deps = _get_deps_from_request(request)
    job_store = deps.job_store

    # Marcar estado de la task
    try:
        if body.error and len(body.error) > MAX_ERROR_LENGTH:
            raise BadRequestError(
                "error excede el tamaño permitido",
                details={"max": MAX_ERROR_LENGTH},
            )
        if body.dest_username and len(body.dest_username.strip()) > MAX_USERNAME_LENGTH:
            raise BadRequestError(
                "dest_username excede el máximo permitido",
                details={"max": MAX_USERNAME_LENGTH},
            )
        if body.dest_username and not re.match(USERNAME_REGEX, body.dest_username.strip().lower()):
            raise BadRequestError("dest_username inválido")
        if body.ok:
            job_store.mark_task_ok(body.job_id, body.task_id, result=None)
        else:
            job_store.mark_task_error(body.job_id, body.task_id, error=body.error or "error")
    except Exception as e:
        raise InternalServerError(
            f"Error al actualizar estado de tarea: {str(e)}",
            error_code="DATABASE_ERROR",
            cause=e,
        )

    # Registrar mensaje enviado (no crítico, pero loguear errores)
    if body.ok and (body.dest_username and body.dest_username.strip()):
        try:
            job_store.register_message_sent(
                account,
                body.dest_username.strip(),
                body.job_id,
                body.task_id,
                client_id=client_id
            )
        except Exception as e:
            logger.warning(
                "message_sent_registration_failed",
                job_id=body.job_id,
                task_id=body.task_id,
                account=account,
                dest_username=body.dest_username,
                error=str(e),
                message="No crítico, pero debería investigarse"
            )

    # Marcar job como done si todas las tareas terminaron (crítico)
    try:
        if job_store.all_tasks_finished(body.job_id):
            job_store.mark_job_done(body.job_id)
            logger.debug(
                "job_marked_done",
                job_id=body.job_id,
                message="Job completado exitosamente"
            )
    except Exception as e:
        logger.error(
            "job_completion_check_failed",
            job_id=body.job_id,
            error=str(e),
            message="Error crítico: job puede quedar en estado inconsistente"
        )
        # No re-lanzamos para no afectar la respuesta del endpoint,
        # pero el error queda registrado para monitoreo

    return {"status": "ok"}

