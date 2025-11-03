from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Sequence, Tuple
import re

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, NonNegativeInt, field_validator, model_validator


class PrivacyStatus(str, Enum):
    public = "public"
    private = "private"
    unknown = "unknown"


class ReelMetrics(BaseModel):
    """
    Métricas por reel. 'code' es el shortcode (https://instagram.com/reel/<code>/).
    Mantener liviano: datos que el dominio/IA necesita, no HTML/elementos.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    code: str = Field(..., min_length=3, max_length=32)
    views: NonNegativeInt = 0
    likes: NonNegativeInt = 0
    comments: NonNegativeInt = 0
    published_at: Optional[datetime] = None
    url: Optional[HttpUrl] = None


class BasicStats(BaseModel):
    """
    Agregados/derivados usados por evaluación o IA.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    avg_views_last_n: Optional[float] = None
    avg_likes_last_n: Optional[float] = None
    avg_comments_last_n: Optional[float] = None
    engagement_score: Optional[float] = None
    success_score: Optional[float] = None


# =========================
# Username (VO con invariantes)
# =========================

class Username(BaseModel):
    """
    Value Object: Username de Instagram con validación completa.
    - Solo letras, números, '.' o '_'
    - 1–30 caracteres
    - No puede comenzar ni terminar con '.'
    - No puede tener '..'
    - Case-insensitive (almacenado en lowercase)
    """

    value: str = Field(..., min_length=1, max_length=30)
    model_config = ConfigDict(frozen=True)

    @field_validator("value")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip().lstrip("@").lower()

        # Longitud
        if not (1 <= len(v) <= 30):
            raise ValueError("El nombre de usuario debe tener entre 1 y 30 caracteres.")

        # Solo caracteres válidos
        if not re.fullmatch(r"[a-z0-9._]+", v):
            raise ValueError("El nombre de usuario solo puede contener letras, números, '.' o '_'.")

        # No empezar/terminar con punto
        if v.startswith(".") or v.endswith("."):
            raise ValueError("El nombre de usuario no puede empezar ni terminar con punto.")

        # No contener dos puntos consecutivos
        if ".." in v:
            raise ValueError("El nombre de usuario no puede contener '..' consecutivos.")

        return v


# =========================
# Profile (entidad simple)
# =========================

class Profile(BaseModel):
    """
    Entidad de dominio para el perfil con Value Objects.
    Usa Username como VO y PrivacyStatus como enum.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    username: Username
    privacy: PrivacyStatus = PrivacyStatus.unknown
    bio: Optional[str] = None
    picture_url: Optional[HttpUrl] = None
    last_seen: Optional[datetime] = None
    stats: Optional[BasicStats] = None

    def can_receive_dm(self) -> bool:
        return self.privacy is PrivacyStatus.public


class ProfileSnapshot(BaseModel):
    """
    DTO de snapshots para scraping y persistencia.
    Representa el estado completo de un perfil para ser guardado en DB.
    Usa strings en lugar de Value Objects para simplicidad de serialización.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    username: str = Field(..., min_length=1)
    bio: str = ""
    followers: Optional[int] = Field(None, ge=0)
    followings: Optional[int] = Field(None, ge=0)
    posts: Optional[int] = Field(None, ge=0)
    is_verified: bool = False
    privacy: str = "unknown"  # 'public', 'private', 'unknown'
    rubro: Optional[str] = None  # Categoría/profesión detectada (ej: "profesional", "coach", "marca")

    def can_receive_dm(self) -> bool:
        """Indica si el perfil puede recibir mensajes directos."""
        return self.privacy == "public"


class PostMetrics(BaseModel):
    """
    Métricas por post/potografía estática.
    Similar a ReelMetrics pero para posts regulares.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    code: str = Field(..., min_length=3, max_length=32)  # shortcode
    likes: NonNegativeInt = 0
    comments: NonNegativeInt = 0
    published_at: Optional[datetime] = None
    url: Optional[HttpUrl] = None


# =========================
# Followings (relación) + helpers
# =========================

class Following(BaseModel):
    """
    Relación 'owner -> target' con invariantes de dominio.
    - owner != target
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    owner: Username
    target: Username

    @model_validator(mode="after")
    def _check_distinct(self) -> "Following":
        if self.owner.value == self.target.value:
            raise ValueError("El owner y el target no pueden ser el mismo usuario.")
        return self


def normalize_usernames(items: Iterable[str]) -> list[Username]:
    """
    Convierte una lista de str a Username aplicando invariantes (lower/regex/longitud).
    Levanta ValueError si alguno es inválido.
    """
    return [Username(value=s) for s in items]


def unique_followings(items: Iterable[Following]) -> list[Following]:
    """
    Dedup por par (owner,target) preservando orden de primera aparición.
    """
    seen: set[Tuple[str, str]] = set()
    out: list[Following] = []
    for f in items:
        key = (f.owner.value, f.target.value)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def clip_followings(items: Sequence[Following], max_items: int | None) -> list[Following]:
    """
    Recorta a max_items si corresponde (None/<=0 => no recorta).
    """
    if max_items is None or max_items <= 0:
        return list(items)
    return list(items[:max_items])
