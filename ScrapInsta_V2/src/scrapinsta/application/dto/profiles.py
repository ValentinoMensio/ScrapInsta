from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from scrapinsta.domain.models.profile_models import (
    PrivacyStatus,
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)


class AnalyzeProfileRequest(BaseModel):
    """
    DTO de entrada para analyze_profile.
    """
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    username: str
    fetch_reels: bool = True
    fetch_posts: bool = False
    max_reels: int = 5
    max_posts: int = 30


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
