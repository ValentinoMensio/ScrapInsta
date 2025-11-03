from __future__ import annotations

from typing import Protocol, runtime_checkable, Iterable, Optional
from scrapinsta.domain.models.profile_models import Username, Following

# =========================
# Excepciones de dominio
# =========================

class FollowingsRepoError(Exception):
    """
    Base para errores en la persistencia de followings.

    Atributos:
        retryable (bool): indica si el error es potencialmente transitorio y
            un retry/backoff podría resolverlo (p.ej., locks, desconexión).
        cause (BaseException | None): excepción original de infraestructura
            para trazabilidad; no debe filtrarse fuera del dominio.
    """
    retryable: bool = False

    def __init__(self, message: str = "", *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.cause = cause


class FollowingsValidationError(FollowingsRepoError):
    """
    Error validando datos antes de guardar (owner vacío, lista vacía, datos inválidos).
    No es retryable: corregir la entrada y reintentar.
    """
    retryable = False


class FollowingsPersistenceError(FollowingsRepoError):
    """
    Error ejecutando la consulta o al insertar en la base de datos
    (deadlocks, timeouts, conexión perdida, tabla bloqueada, etc.).

    Suele ser retryable: la política de reintentos/backoff debe aplicarse desde
    crosscutting (p.ej., decoradores o el orquestador de casos de uso).
    """
    retryable = True


# =========================
# Puerto: FollowingsRepo
# =========================

@runtime_checkable
class FollowingsRepo(Protocol):
    """
    Abstracción del repositorio de followings.

    Debe persistir de forma idempotente relaciones (owner -> target).
    Las entradas llegan tipadas con VO/entidades de dominio.
    """

    def save_for_owner(self, owner: Username, followings: Iterable[Following]) -> int:
        """
        Inserta followings nuevos para 'owner' (idempotente).

        Requisitos:
        - owner/targets ya validados (VO Username) y relaciones válidas (Following).
        - Ignorar duplicados existentes en la base.
        - Retornar cuántos followings fueron realmente nuevos.
        - Mapear errores a FollowingsValidationError o FollowingsPersistenceError.
        """
        ...

    def get_for_owner(self, owner: Username, limit: int | None = None) -> list[Following]:
        """
        Devuelve relaciones persistidas para 'owner'. Si 'limit' > 0, recorta el resultado.
        """
        ...

