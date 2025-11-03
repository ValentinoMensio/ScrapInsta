from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageRequest(BaseModel):
    """Pedido de envío de mensaje (entrada del use case)."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    target_username: str = Field(..., min_length=2, max_length=30)
    # Si viene message_text, se usa tal cual. Si no, el use case pedirá al composer (IA) que lo genere.
    message_text: Optional[str] = None
    template_id: Optional[str] = None  # opcional para plantillas del composer
    dry_run: bool = False
    max_retries: int = 3
    
    @field_validator("target_username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validar formato de username de Instagram."""
        # Instagram permite: a-z, A-Z, 0-9, punto (.), underscore (_)
        if not re.match(r'^[a-zA-Z0-9._]{2,30}$', v):
            raise ValueError("Username inválido para Instagram (solo a-z, 0-9, ., _)")
        return v.lower()  # normalizar a lowercase
    
    @field_validator("message_text")
    @classmethod
    def validate_message_text(cls, v: Optional[str]) -> Optional[str]:
        """Validar que message_text no esté vacío si se proporciona."""
        if v is not None:
            v_stripped = v.strip()
            if len(v_stripped) < 3:
                raise ValueError("message_text muy corto (mínimo 3 caracteres)")
            if len(v_stripped) > 1000:
                raise ValueError("message_text muy largo (máximo 1000 caracteres)")
            return v_stripped
        return v
    
    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validar que max_retries sea razonable."""
        if v < 0 or v > 10:
            raise ValueError("max_retries debe estar entre 0 y 10")
        return v


class MessageContext(BaseModel):
    """Contexto mínimo para componer el mensaje (lo trae el repo de perfiles)."""
    model_config = ConfigDict(frozen=True)

    username: str
    rubro: Optional[str] = None
    followers: Optional[int] = None
    posts: Optional[int] = None
    avg_views: Optional[float] = None
    engagement_score: Optional[float] = None
    success_score: Optional[float] = None


class MessageResult(BaseModel):
    """Resultado del envío."""
    model_config = ConfigDict(frozen=True)

    success: bool
    attempts: int
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    generated_text: Optional[str] = None  # Para dry_run y debugging
    target_username: Optional[str] = None  # Para trazabilidad
    
    @field_validator("attempts")
    @classmethod
    def validate_attempts(cls, v: int) -> int:
        """Validar que attempts sea >= 0."""
        if v < 0:
            raise ValueError("attempts debe ser >= 0")
        return v
