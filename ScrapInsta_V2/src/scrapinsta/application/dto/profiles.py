from __future__ import annotations

from typing import Optional, List
import os
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

from scrapinsta.domain.models.profile_models import (
    PrivacyStatus,
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)


APP_ENV = os.getenv("APP_ENV", "development").lower()
MAX_USERNAME_LENGTH = int(os.getenv("MAX_USERNAME_LENGTH", "64"))
MAX_ANALYZE_MAX_REELS = int(os.getenv("MAX_ANALYZE_MAX_REELS", "12"))
MAX_ANALYZE_MAX_POSTS = int(os.getenv("MAX_ANALYZE_MAX_POSTS", "30"))


class AnalyzeProfileRequest(BaseModel):
    """
    DTO de entrada para analyze_profile.
    """
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    username: str = Field(..., min_length=2, max_length=MAX_USERNAME_LENGTH)
    fetch_reels: bool = True
    fetch_posts: bool = False
    max_reels: int = Field(default=5, ge=1)
    max_posts: int = Field(default=30, ge=1)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("@"):
            v = v[1:]
        if not re.match(r'^[a-zA-Z0-9._]{2,30}$', v):
            raise ValueError("Username inválido para Instagram (solo a-z, 0-9, ., _)")
        if len(v) > MAX_USERNAME_LENGTH:
            raise ValueError("username excede el máximo permitido")
        return v.lower()

    @field_validator("max_reels")
    @classmethod
    def validate_max_reels(cls, v: int) -> int:
        if v > MAX_ANALYZE_MAX_REELS:
            raise ValueError("max_reels excede el máximo permitido")
        return v

    @field_validator("max_posts")
    @classmethod
    def validate_max_posts(cls, v: int) -> int:
        if v > MAX_ANALYZE_MAX_POSTS:
            raise ValueError("max_posts excede el máximo permitido")
        return v


class AnalyzeProfileResponse(BaseModel):
    """
    DTO de salida del caso de uso analyze_profile.
    Reutiliza modelos de dominio sin redefinirlos.
    """
    model_config = ConfigDict(frozen=True)

    snapshot: Optional[ProfileSnapshot] = None
    basic_stats: Optional[BasicStats] = None
    recent_reels: Optional[List[ReelMetrics]] = None
    recent_posts: Optional[List[PostMetrics]] = None
    skipped_recent: bool = False  # True si se saltó por análisis reciente


__all__ = [
    "PrivacyStatus",
    "ProfileSnapshot",
    "ReelMetrics",
    "PostMetrics",
    "BasicStats",
    "AnalyzeProfileRequest",
    "AnalyzeProfileResponse",
]
