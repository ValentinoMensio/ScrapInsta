from __future__ import annotations

from typing import Protocol, runtime_checkable, Optional, Sequence

from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    BasicStats,
    ReelMetrics,
    PostMetrics,
)


# =========================
# Excepciones de dominio
# =========================

class ProfileRepoError(Exception):
    """
    Base para errores en la persistencia de perfiles.
    
    Atributos:
        retryable (bool): indica si el error es potencialmente transitorio
        cause (BaseException | None): excepción original para trazabilidad
    """
    retryable: bool = False
    
    def __init__(self, message: str = "", *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.cause = cause


class ProfileValidationError(ProfileRepoError):
    """
    Error validando datos antes de guardar.
    No es retryable.
    """
    retryable = False


class ProfilePersistenceError(ProfileRepoError):
    """
    Error ejecutando la consulta o al insertar en la base de datos.
    Suele ser retryable.
    """
    retryable = True


# =========================
# Puerto: ProfileRepository
# =========================

@runtime_checkable
class ProfileRepository(Protocol):
    """
    Puerto de persistencia de perfiles.
    
    Define el contrato para almacenamiento de perfiles y sus análisis,
    agnóstico de la implementación de base de datos.
    """

    def get_profile_id(self, username: str) -> Optional[int]:
        """
        Devuelve el ID del perfil o None si no existe.
        """
        ...

    def get_last_analysis_date(self, username: str) -> Optional[str]:
        """
        Obtiene la fecha del último análisis para un usuario.
        Retorna None si no existe análisis previo.
        """
        ...

    def upsert_profile(self, snap: ProfileSnapshot) -> int:
        """
        Crea o actualiza un perfil y devuelve su ID.
        Implementaciones deben usar ON DUPLICATE KEY UPDATE (o equivalente).
        """
        ...

    def save_analysis_snapshot(
        self,
        profile_id: int,
        snapshot: ProfileSnapshot,
        basic: Optional[BasicStats],
        reels: Optional[Sequence[ReelMetrics]],
        posts: Optional[Sequence[PostMetrics]],
    ) -> int:
        """
        Guarda un registro del análisis de un perfil (audit trail) usando SOLO modelos de dominio.
        """
        ...
