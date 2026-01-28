from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_MESSAGE_LENGTH = int(os.getenv("MIN_MESSAGE_LENGTH", "3"))
MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "1000"))
MAX_MESSAGE_RETRIES = int(os.getenv("MAX_MESSAGE_RETRIES", "10"))
MAX_TARGET_USERNAME_LENGTH = int(os.getenv("MAX_TARGET_USERNAME_LENGTH", "30"))
USERNAME_REGEX = os.getenv("USERNAME_REGEX", r"^[a-zA-Z0-9._]{2,30}$")


class MessageRequest(BaseModel):
    """Pedido de envío de mensaje (entrada del use case)."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    target_username: str = Field(..., min_length=2, max_length=MAX_TARGET_USERNAME_LENGTH)
    message_text: Optional[str] = None
    template_id: Optional[str] = None
    dry_run: bool = False
    max_retries: int = 3
    
    @field_validator("target_username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validar formato de username de Instagram."""
        if not re.match(USERNAME_REGEX, v):
            raise ValueError("Username inválido para Instagram (solo a-z, 0-9, ., _)")
        if len(v) > MAX_TARGET_USERNAME_LENGTH:
            raise ValueError("Username excede el máximo permitido")
        return v.lower()
    
    @field_validator("message_text")
    @classmethod
    def validate_message_text(cls, v: Optional[str]) -> Optional[str]:
        """Validar que message_text no esté vacío si se proporciona."""
        if v is not None:
            v_stripped = v.strip()
            if len(v_stripped) < MIN_MESSAGE_LENGTH:
                raise ValueError(f"message_text muy corto (mínimo {MIN_MESSAGE_LENGTH} caracteres)")
            if len(v_stripped) > MAX_MESSAGE_LENGTH:
                raise ValueError(f"message_text muy largo (máximo {MAX_MESSAGE_LENGTH} caracteres)")
            return v_stripped
        return v
    
    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validar que max_retries sea razonable."""
        if v < 0 or v > MAX_MESSAGE_RETRIES:
            raise ValueError(f"max_retries debe estar entre 0 y {MAX_MESSAGE_RETRIES}")
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
    generated_text: Optional[str] = None
    target_username: Optional[str] = None
    
    @field_validator("attempts")
    @classmethod
    def validate_attempts(cls, v: int) -> int:
        """Validar que attempts sea >= 0."""
        if v < 0:
            raise ValueError("attempts debe ser >= 0")
        return v
