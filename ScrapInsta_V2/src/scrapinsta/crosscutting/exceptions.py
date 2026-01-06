"""Excepciones HTTP centralizadas para la API."""
from __future__ import annotations

from typing import Optional, Dict, Any


class ScrapInstaHTTPError(Exception):
    """
    Excepción base para todos los errores HTTP de la API.
    
    Atributos:
        status_code: Código de estado HTTP
        error_code: Código de error único para el cliente
        message: Mensaje de error legible
        details: Información adicional opcional
    """
    
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    
    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.error_code
        self.details = details or {}
        self.cause = cause
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la excepción a un diccionario para la respuesta HTTP."""
        result = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


# Errores 4xx - Cliente

class ClientError(ScrapInstaHTTPError):
    """Base para errores del cliente (4xx)."""
    status_code = 400
    error_code = "CLIENT_ERROR"


class BadRequestError(ClientError):
    """Solicitud mal formada o inválida."""
    status_code = 400
    error_code = "BAD_REQUEST"


class UnauthorizedError(ClientError):
    """Falta autenticación o credenciales inválidas."""
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(ClientError):
    """Cliente autenticado pero sin permisos suficientes."""
    status_code = 403
    error_code = "FORBIDDEN"


class NotFoundError(ClientError):
    """Recurso no encontrado."""
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(ClientError):
    """Conflicto con el estado actual del recurso."""
    status_code = 409
    error_code = "CONFLICT"


class RateLimitError(ClientError):
    """Límite de tasa excedido."""
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


# Errores 5xx - Servidor

class ServerError(ScrapInstaHTTPError):
    """Base para errores del servidor (5xx)."""
    status_code = 500
    error_code = "SERVER_ERROR"


class InternalServerError(ServerError):
    """Error interno del servidor."""
    status_code = 500
    error_code = "INTERNAL_ERROR"


class ServiceUnavailableError(ServerError):
    """Servicio temporalmente no disponible."""
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"


# Errores específicos de dominio

class ClientNotFoundError(NotFoundError):
    """Cliente no encontrado."""
    error_code = "CLIENT_NOT_FOUND"


class JobNotFoundError(NotFoundError):
    """Job no encontrado."""
    error_code = "JOB_NOT_FOUND"


class TaskNotFoundError(NotFoundError):
    """Tarea no encontrada."""
    error_code = "TASK_NOT_FOUND"


class InvalidScopeError(ForbiddenError):
    """Scope insuficiente para la operación."""
    error_code = "INSUFFICIENT_SCOPE"


class JobOwnershipError(ForbiddenError):
    """El job no pertenece al cliente autenticado."""
    error_code = "JOB_OWNERSHIP_ERROR"


class DatabaseError(InternalServerError):
    """Error en la base de datos."""
    error_code = "DATABASE_ERROR"


class ConfigurationError(InternalServerError):
    """Error de configuración del sistema."""
    error_code = "CONFIGURATION_ERROR"

