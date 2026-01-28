"""Funciones de autenticación y autorización."""
from __future__ import annotations

import os
import json
import re
from typing import Dict, Any, Optional

from fastapi import Request, Header

from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.crosscutting.exceptions import (
    UnauthorizedError,
    ForbiddenError,
    BadRequestError,
    ClientNotFoundError,
    InternalServerError,
    InvalidScopeError,
)
from scrapinsta.infrastructure.auth.jwt_auth import verify_token
from scrapinsta.interface.dependencies import get_dependencies

logger = get_logger("auth.authentication")

# Cargar API_SHARED_SECRET desde gestor de secretos si está configurado
API_SHARED_SECRET = os.getenv("API_SHARED_SECRET")
try:
    from scrapinsta.crosscutting.secrets import get_secret
    secret = get_secret("api_shared_secret")
    if secret:
        API_SHARED_SECRET = secret
except Exception:
    # Si el gestor de secretos no está disponible, usar variable de entorno
    pass

# Clientes con scopes y rate limit (opcional, JSON en env API_CLIENTS_JSON)
_CLIENTS: Dict[str, Dict[str, Any]] = {}
try:
    raw = os.getenv("API_CLIENTS_JSON")
    if raw:
        _CLIENTS = json.loads(raw)
except Exception:
    _CLIENTS = {}

APP_ENV = os.getenv("APP_ENV", "development").lower()
REQUIRE_HTTPS = os.getenv(
    "REQUIRE_HTTPS",
    "true" if APP_ENV == "production" else "false",
).lower() in ("1", "true", "yes")
REQUIRE_ACCOUNT_IN_CONFIG = os.getenv(
    "REQUIRE_ACCOUNT_IN_CONFIG",
    "true" if APP_ENV == "production" else "false",
).lower() in ("1", "true", "yes")
MAX_USERNAME_LENGTH = int(os.getenv("MAX_USERNAME_LENGTH", "64"))
USERNAME_REGEX = os.getenv("USERNAME_REGEX", r"^[a-zA-Z0-9._]{2,30}$")
ACCOUNT_REGEX = os.getenv("ACCOUNT_REGEX", r"^[a-zA-Z0-9._-]{2,30}$")


def _normalize(s: Optional[str]) -> Optional[str]:
    """Normaliza strings: trim + lower."""
    if not s:
        return None
    v = str(s).strip().lower()
    return v or None


def authenticate_client(
    x_api_key: Optional[str] = None,
    authorization: Optional[str] = None,
    x_client_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Autentica un cliente usando JWT, API key estática o API clients JSON.
    
    Args:
        x_api_key: API key del header X-Api-Key
        authorization: Header Authorization (Bearer token)
        x_client_id: ID del cliente del header X-Client-Id
        
    Returns:
        Dict con id, scopes y rate del cliente
        
    Raises:
        UnauthorizedError: Si las credenciales son inválidas
        ForbiddenError: Si el cliente no está activo
    """
    deps = get_dependencies()
    client_repo = deps.client_repo
    
    # Intentar autenticación JWT primero
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = verify_token(token)
        if payload:
            client_id = payload.get("client_id")
            if client_id:
                client = client_repo.get_by_id(client_id)
                if not client:
                    raise ClientNotFoundError(f"Cliente '{client_id}' no encontrado")
                if client.get("status") != "active":
                    raise ForbiddenError(f"Cliente '{client_id}' no está activo")
                limits = client_repo.get_limits(client_id) or {}
                return {
                    "id": client_id,
                    "scopes": payload.get("scopes", ["fetch", "analyze", "send"]),
                    "rate": limits.get("requests_per_minute", 60)
                }
        raise UnauthorizedError("Token inválido o expirado")

    # Autenticación con API key
    provided: Optional[str] = None
    if x_api_key and x_api_key.strip():
        provided = x_api_key.strip()

    # API clients JSON (configuración avanzada)
    if _CLIENTS:
        cid = (x_client_id or "").strip()
        if not cid or cid not in _CLIENTS:
            raise UnauthorizedError("Cliente inválido")
        entry = _CLIENTS[cid]
        if not provided or provided != entry.get("key"):
            raise UnauthorizedError("API key inválida")
        return {
            "id": cid,
            "scopes": entry.get("scopes") or [],
            "rate": (entry.get("rate") or {}).get("rpm", 60)
        }

    # API key compartida (modo simple)
    if not API_SHARED_SECRET:
        raise InternalServerError(
            "API no configurada (falta API_SHARED_SECRET)",
            error_code="CONFIGURATION_ERROR"
        )
    if not provided or provided != API_SHARED_SECRET:
        raise UnauthorizedError("API key inválida")
    return {"id": "default", "scopes": ["fetch", "analyze", "send"], "rate": 60}


def check_scope(client: Dict[str, Any], scope: str) -> None:
    """
    Verifica que el cliente tenga el scope requerido.
    
    Args:
        client: Dict del cliente (de authenticate_client)
        scope: Scope requerido
        
    Raises:
        InvalidScopeError: Si el cliente no tiene el scope
    """
    scopes = client.get("scopes") or []
    if scope not in scopes:
        raise InvalidScopeError(
            f"Scope '{scope}' requerido pero no disponible",
            details={"required_scope": scope, "available_scopes": scopes}
        )


def enforce_https(req: Request) -> None:
    """
    Valida que la request venga por HTTPS. Soporta proxies reversos (X-Forwarded-Proto).
    
    Args:
        req: Request de FastAPI
        
    Raises:
        BadRequestError: Si REQUIRE_HTTPS está activo y la request no es HTTPS
    """
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


def get_client_account(x_account: Optional[str] = None) -> str:
    """
    Obtiene y valida el account del cliente desde el header X-Account.
    
    Args:
        x_account: Valor del header X-Account
        
    Returns:
        Account normalizado
        
    Raises:
        BadRequestError: Si falta X-Account
    """
    acc = _normalize(x_account)
    if not acc:
        raise BadRequestError("Falta X-Account")
    if len(acc) > MAX_USERNAME_LENGTH:
        raise BadRequestError(
            "X-Account excede el máximo permitido",
            details={"max": MAX_USERNAME_LENGTH},
        )
    if not re.match(ACCOUNT_REGEX, acc):
        raise BadRequestError("X-Account inválido")
    if REQUIRE_ACCOUNT_IN_CONFIG:
        deps = get_dependencies()
        allowed = deps.settings.get_accounts_usernames()
        if not allowed:
            logger.error(
                "accounts_not_configured",
                message="No hay cuentas configuradas en Settings",
            )
            raise InternalServerError(
                "No hay cuentas configuradas para validar X-Account",
                error_code="CONFIGURATION_ERROR",
            )
        if acc not in allowed:
            raise ForbiddenError(
                "Cuenta no autorizada",
                details={"account": acc},
            )
    return acc

