"""Mapeo de excepciones de dominio a excepciones HTTP usando Registry Pattern."""
from __future__ import annotations

from typing import Callable, Dict, Type, Any, Optional
from functools import wraps

from scrapinsta.crosscutting.exceptions import (
    ScrapInstaHTTPError,
    UnauthorizedError,
    RateLimitError,
    InternalServerError,
    BadRequestError,
)


class ExceptionMapper:
    """
    Registry para mapear excepciones de dominio a excepciones HTTP.
    
    Usa el patrón Registry para centralizar el mapeo de excepciones,
    facilitando el mantenimiento y la extensibilidad.
    """
    
    def __init__(self) -> None:
        """Inicializa el mapper con el registry vacío."""
        self._registry: Dict[Type[Exception], Callable[[Exception], ScrapInstaHTTPError]] = {}
        self._default_mapper: Optional[Callable[[Exception], ScrapInstaHTTPError]] = None
    
    def register(
        self,
        exception_type: Type[Exception],
        mapper: Callable[[Exception], ScrapInstaHTTPError],
    ) -> None:
        """
        Registra un mapper para un tipo de excepción.
        
        Args:
            exception_type: Tipo de excepción a mapear
            mapper: Función que convierte la excepción a ScrapInstaHTTPError
        """
        self._registry[exception_type] = mapper
    
    def register_default(
        self,
        mapper: Callable[[Exception], ScrapInstaHTTPError],
    ) -> None:
        """
        Registra un mapper por defecto para excepciones no registradas.
        
        Args:
            mapper: Función que convierte excepciones no registradas a ScrapInstaHTTPError
        """
        self._default_mapper = mapper
    
    def map(self, exc: Exception) -> ScrapInstaHTTPError:
        """
        Mapea una excepción a una excepción HTTP.
        
        Busca en el registry el mapper más específico (usando isinstance)
        y lo aplica. Si no encuentra ninguno, usa el mapper por defecto.
        
        Args:
            exc: Excepción a mapear
            
        Returns:
            Excepción HTTP mapeada
        """
        # Buscar el mapper más específico (el tipo más cercano en la jerarquía)
        for exc_type, mapper in self._registry.items():
            if isinstance(exc, exc_type):
                return mapper(exc)
        
        # Si no hay mapper específico, usar el por defecto
        if self._default_mapper:
            return self._default_mapper(exc)
        
        # Fallback: error interno genérico
        return InternalServerError(
            "Error interno del servidor",
            cause=exc,
        )


# Instancia global del mapper (singleton)
_default_mapper = ExceptionMapper()


def get_exception_mapper() -> ExceptionMapper:
    """Obtiene la instancia global del exception mapper."""
    return _default_mapper


def _create_default_mapper() -> ExceptionMapper:
    """
    Crea y configura el mapper por defecto con todos los mapeos estándar.
    
    Returns:
        ExceptionMapper configurado
    """
    mapper = ExceptionMapper()
    
    # Importar tipos de excepciones de dominio
    from scrapinsta.domain.ports.browser_port import (
        BrowserPortError,
        BrowserAuthError,
        BrowserConnectionError,
        BrowserRateLimitError,
    )
    from scrapinsta.domain.ports.profile_repo import (
        ProfileRepoError,
        ProfileValidationError,
        ProfilePersistenceError,
    )
    from scrapinsta.domain.ports.followings_repo import (
        FollowingsRepoError,
        FollowingsValidationError,
        FollowingsPersistenceError,
    )
    
    # Mapear BrowserAuthError -> UnauthorizedError
    def map_browser_auth(exc: BrowserAuthError) -> UnauthorizedError:
        return UnauthorizedError(
            f"Error de autenticación: {str(exc)}",
            details={"username": exc.username} if exc.username else {},
        )
    mapper.register(BrowserAuthError, map_browser_auth)
    
    # Mapear BrowserRateLimitError -> RateLimitError
    def map_browser_rate_limit(exc: BrowserRateLimitError) -> RateLimitError:
        return RateLimitError(
            f"Límite de tasa excedido: {str(exc)}",
            details={"username": exc.username} if exc.username else {},
        )
    mapper.register(BrowserRateLimitError, map_browser_rate_limit)
    
    # Mapear BrowserConnectionError y BrowserPortError -> InternalServerError
    def map_browser_error(exc: Exception) -> InternalServerError:
        details = {}
        if hasattr(exc, "code"):
            details["code"] = exc.code
        if hasattr(exc, "username"):
            details["username"] = exc.username
        return InternalServerError(
            f"Error del navegador: {str(exc)}",
            details=details,
            cause=exc,
        )
    mapper.register(BrowserConnectionError, map_browser_error)
    mapper.register(BrowserPortError, map_browser_error)
    
    # Mapear ProfileValidationError y FollowingsValidationError -> BadRequestError
    def map_validation_error(exc: Exception) -> BadRequestError:
        return BadRequestError(
            f"Error de validación: {str(exc)}",
            cause=exc,
        )
    mapper.register(ProfileValidationError, map_validation_error)
    mapper.register(FollowingsValidationError, map_validation_error)
    
    # Mapear ProfilePersistenceError y FollowingsPersistenceError -> InternalServerError
    def map_persistence_error(exc: Exception) -> InternalServerError:
        return InternalServerError(
            f"Error de persistencia: {str(exc)}",
            error_code="DATABASE_ERROR",
            cause=exc,
        )
    mapper.register(ProfilePersistenceError, map_persistence_error)
    mapper.register(FollowingsPersistenceError, map_persistence_error)
    
    # Mapear ProfileRepoError y FollowingsRepoError -> InternalServerError
    def map_repo_error(exc: Exception) -> InternalServerError:
        return InternalServerError(
            f"Error del repositorio: {str(exc)}",
            cause=exc,
        )
    mapper.register(ProfileRepoError, map_repo_error)
    mapper.register(FollowingsRepoError, map_repo_error)
    
    # Mapper por defecto para excepciones no registradas
    def map_default(exc: Exception) -> InternalServerError:
        return InternalServerError(
            "Error interno del servidor",
            cause=exc,
        )
    mapper.register_default(map_default)
    
    return mapper


# Inicializar el mapper por defecto
_default_mapper = _create_default_mapper()

