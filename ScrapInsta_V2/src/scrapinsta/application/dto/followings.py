from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field, constr, field_validator, model_validator
from pydantic.config import ConfigDict


class FetchFollowingsRequest(BaseModel):
    """
    DTO de entrada para el caso de uso FetchFollowings.
    """
    username: constr(strip_whitespace=True, min_length=1, max_length=50) = Field(
        ..., description="Nombre de usuario del perfil origen"
    )
    # Campo normalizado de entrada
    max_followings: int = Field(
        100,
        ge=1,
        le=1000,
        description="Cantidad máxima de followings a obtener",
    )

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    @field_validator("username")
    @classmethod
    def validar_username(cls, v: str) -> str:
        # Sin espacios internos y solo chars típicos de IG (letras, números, punto, guión bajo)
        if " " in v:
            raise ValueError("El nombre de usuario no debe contener espacios.")
        if not all(ch.isalnum() or ch in "._" for ch in v):
            raise ValueError("El nombre de usuario contiene caracteres inválidos.")
        return v


class FetchFollowingsResponse(BaseModel):
    """
    DTO de salida del caso de uso FetchFollowings.
    """
    owner: str = Field(..., description="Usuario origen de los followings")
    followings: List[str] = Field(..., description="Usernames recolectados")
    new_saved: int = Field(..., ge=0, description="Nuevos followings insertados")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="selenium", description="Origen del scraping")

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _normalize_limit_field(cls, data):
        """
        Acepta tanto 'limit' como 'max_followings' en el payload y los normaliza a 'max_followings'.
        Si vienen ambos, prioriza 'max_followings'.
        """
        if isinstance(data, dict):
            if "max_followings" not in data and "limit" in data:
                try:
                    data["max_followings"] = int(data.get("limit"))
                except Exception:
                    pass
        return data

    @field_validator("owner")
    @classmethod
    def normalizar_owner(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("followings", mode="before")
    @classmethod
    def normalizar_followings(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            return v
        out: List[str] = []
        for item in v:
            if isinstance(item, str):
                s = item.strip().lower()
                if s:
                    out.append(s)
        return out
