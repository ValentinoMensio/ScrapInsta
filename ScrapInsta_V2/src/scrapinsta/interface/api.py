from __future__ import annotations

import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Header, HTTPException, Path, Request
import json
import time
from pydantic import BaseModel, Field

from scrapinsta.config.settings import Settings
import logging
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL


logger = logging.getLogger("api")

# =========================================================
# App
# =========================================================
app = FastAPI(title="ScrapInsta Send API", version="0.1.0")

# Singletons simples (sin DI compleja)
_settings = Settings()
logging.getLogger("api").info("[api] DB_DSN=%s", _settings.db_dsn)
_job_store = JobStoreSQL(_settings.db_dsn)

# =========================================================
# Auth mínima para clientes (extensión)
# - X-Api-Key / Authorization: Bearer <API_SHARED_SECRET>
# - X-Account = cuenta local del cliente (cola a la que se leasea)
# =========================================================
API_SHARED_SECRET = os.getenv("API_SHARED_SECRET")

# Clientes con scopes y rate limit (opcional, JSON en env API_CLIENTS_JSON)
_CLIENTS: Dict[str, Dict[str, Any]] = {}
try:
    raw = os.getenv("API_CLIENTS_JSON")
    if raw:
        _CLIENTS = json.loads(raw)
except Exception:
    _CLIENTS = {}

REQUIRE_HTTPS = os.getenv("REQUIRE_HTTPS", "false").lower() in ("1","true","yes")

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
    """
    Autenticación de clientes con soporte de múltiples claves y scopes.
    Si API_CLIENTS_JSON no está definido, cae a API_SHARED_SECRET (modo único).
    """
    provided: Optional[str] = None
    if x_api_key and x_api_key.strip():
        provided = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()

    if _CLIENTS:
        cid = (x_client_id or "").strip()
        if not cid or cid not in _CLIENTS:
            raise HTTPException(status_code=401, detail="cliente inválido")
        entry = _CLIENTS[cid]
        if not provided or provided != entry.get("key"):
            raise HTTPException(status_code=401, detail="API key inválida")
        return {"id": cid, "scopes": entry.get("scopes") or [], "rate": (entry.get("rate") or {}).get("rpm", 60)}

    if not API_SHARED_SECRET:
        raise HTTPException(status_code=500, detail="API no configurada (falta API_SHARED_SECRET)")
    if not provided or provided != API_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="API key inválida")
    return {"id": "default", "scopes": ["fetch","analyze","send"], "rate": 60}


def _enforce_https(req: Request) -> None:
    if not REQUIRE_HTTPS:
        return
    proto = req.headers.get("x-forwarded-proto") or req.url.scheme
    if (proto or "").lower() != "https":
        raise HTTPException(status_code=400, detail="Se requiere HTTPS")


def _check_scope(client: Dict[str, Any], scope: str) -> None:
    scopes = client.get("scopes") or []
    if scope not in scopes:
        raise HTTPException(status_code=403, detail="scope insuficiente")


def _rate_limit(client: Dict[str, Any], req: Request) -> None:
    rpm = int(client.get("rate") or 60)
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "-").split(",")[0].strip()
    if not _rate.allow(f"client:{client['id']}", rpm):
        raise HTTPException(status_code=429, detail="rate limit (cliente)")
    if not _rate.allow(f"ip:{ip}", max(60, rpm)):
        raise HTTPException(status_code=429, detail="rate limit (ip)")


def _get_client_account(x_account: Optional[str]) -> str:
    acc = _normalize(x_account)
    if not acc:
        raise HTTPException(status_code=400, detail="Falta X-Account")
    return acc


# =========================================================
# Schemas
# =========================================================
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


# =========================================================
# Endpoints
# =========================================================
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
    
    logger.info(f"[api] pull_tasks account={account} limit={body.limit}")

    try:
        rows = _job_store.lease_tasks(account_id=account, limit=body.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"lease_tasks failed: {e}")

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

    # Marcar estado de la task
    try:
        if body.ok:
            _job_store.mark_task_ok(body.job_id, body.task_id, result=None)
        else:
            _job_store.mark_task_error(body.job_id, body.task_id, error=body.error or "error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"mark_task_* failed: {e}")

    # Ledger: registrar envío exitoso por (cuenta cliente, destino)
    if body.ok and (body.dest_username and body.dest_username.strip()):
        try:
            _job_store.register_message_sent(account, body.dest_username.strip(), body.job_id, body.task_id)
        except Exception:
            # No romper si falla el ledger; el envío ya se marcó ok
            pass

    # Cerrar job si ya no quedan pendientes/sent
    try:
        if _job_store.all_tasks_finished(body.job_id):
            _job_store.mark_job_done(body.job_id)
    except Exception:
        pass

    return {"status": "ok"}


@app.get("/health")
def health():
    """Ping simple a la DB reutilizando el store."""
    try:
        _job_store.pending_jobs()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

from uuid import uuid4

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

    logger.info(f"[api] enqueue_followings target={body.target_username} limit={body.limit} client_account={client_account}")

    target = (body.target_username or "").strip().lower()
    if not target:
        raise HTTPException(status_code=400, detail="target_username vacío")

    job_id = f"job:{uuid4().hex}"

    try:
        _job_store.create_job(
            job_id=job_id,
            kind="fetch_followings",
            priority=5,
            batch_size=1,
            extra={"limit": body.limit, "source": "ext", "client_account": client_account},
            total_items=1,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"create_job failed: {e}")

    try:
        seed_task_id = f"{job_id}:fetch_followings:{target}"
        _job_store.add_task(
            job_id=job_id,
            task_id=seed_task_id,
            correlation_id=job_id,
            account_id=None,
            username=target,
            payload={"username": target, "limit": body.limit, "client_account": client_account},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"add_task failed: {e}")

    return EnqueueResponse(job_id=job_id)


# =========================================================
# Endpoint: job summary
# =========================================================
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
    try:
        s = _job_store.job_summary(job_id)
        safe = {
            "queued": int(s.get("queued") or 0),
            "sent":   int(s.get("sent")   or 0),
            "ok":     int(s.get("ok")     or 0),
            "error":  int(s.get("error")  or 0),
        }
        return JobSummaryResponse(**safe)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"job_summary failed: {e}")



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
        raise HTTPException(status_code=400, detail="usernames vacío")

    job_id = f"job:{uuid4().hex}"

    try:
        _job_store.create_job(
            job_id=job_id,
            kind="analyze_profile",
            priority=body.priority,
            batch_size=body.batch_size,
            extra=body.extra or {},
            total_items=len(usernames),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"create_job failed: {e}")

    # Creamos las tasks 'queued' (Router las enviará a los bots y marcará 'sent')
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
            )
        except Exception:
            pass

    return EnqueueAnalyzeResponse(job_id=job_id, total_items=len(usernames))
