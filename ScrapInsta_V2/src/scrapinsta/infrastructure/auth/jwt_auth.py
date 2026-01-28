from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt

from scrapinsta.crosscutting.logging_config import get_logger

logger = get_logger("auth.jwt")

APP_ENV = os.getenv("APP_ENV", "development").lower()

# Cargar SECRET_KEY desde gestor de secretos si está configurado
_secret_key = os.getenv("JWT_SECRET_KEY") or os.getenv("API_SHARED_SECRET")
try:
    from scrapinsta.crosscutting.secrets import get_secret
    jwt_secret = get_secret("jwt_secret_key")
    if jwt_secret:
        _secret_key = jwt_secret
    else:
        # Fallback a api_shared_secret
        api_secret = get_secret("api_shared_secret")
        if api_secret:
            _secret_key = api_secret
except Exception:
    # Si el gestor de secretos no está disponible, usar variable de entorno
    pass

SECRET_KEY = _secret_key or "change-me-in-production"
ALGORITHM = "HS256"

# En producción, no permitir usar el secreto por defecto
if APP_ENV == "production" and SECRET_KEY == "change-me-in-production":
    raise RuntimeError("JWT_SECRET_KEY es requerido en producción")
elif SECRET_KEY == "change-me-in-production":
    logger.warning("jwt_secret_default_in_use", message="Usando secret por defecto en no-producción")
# Configurable via env (documentado en MEJORAS_PROFESIONALES.md)
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
except Exception:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_client_id_from_token(token: str) -> Optional[str]:
    payload = verify_token(token)
    if payload:
        return payload.get("client_id")
    return None

