"""
Manejadores específicos de excepciones para ScrapInsta4
"""
import logging
import traceback
from typing import Optional, Dict, Any, Callable, Type
from functools import wraps
import mysql.connector
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    ElementNotInteractableException, StaleElementReferenceException
)
from pydantic import ValidationError as PydanticValidationError

from exceptions.database_exceptions import (
    DatabaseConnectionError, DatabaseQueryError, DatabaseTransactionError,
    DatabasePoolError, DatabaseValidationError
)
from exceptions.selenium_exceptions import (
    SeleniumDriverError, SeleniumTimeoutError, SeleniumElementNotFoundError,
    SeleniumNavigationError, SeleniumSessionError
)
from exceptions.validation_exceptions import (
    ValidationError, ProfileValidationError, TaskValidationError,
    FollowingValidationError, ConfigurationValidationError
)
from exceptions.business_exceptions import (
    ProfileNotFoundError, ProfilePrivateError, ProfileBlockedError,
    InstagramRateLimitError, InstagramLoginError, TaskProcessingError, WorkerError
)
from exceptions.network_exceptions import (
    NetworkConnectionError, NetworkTimeoutError, ProxyError, InstagramAPIError
)

logger = logging.getLogger(__name__)


def handle_database_exceptions(func: Callable) -> Callable:
    """
    Decorator para manejar excepciones de base de datos
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except mysql.connector.Error as e:
            error_code = e.errno
            error_msg = e.msg
            
            if error_code == 2003:  # Can't connect to MySQL server
                raise DatabaseConnectionError(
                    f"No se puede conectar al servidor MySQL: {error_msg}",
                    error_code=str(error_code)
                )
            elif error_code == 1045:  # Access denied
                raise DatabaseConnectionError(
                    f"Acceso denegado a la base de datos: {error_msg}",
                    error_code=str(error_code)
                )
            elif error_code == 1049:  # Unknown database
                raise DatabaseConnectionError(
                    f"Base de datos desconocida: {error_msg}",
                    error_code=str(error_code)
                )
            elif error_code == 1062:  # Duplicate entry
                raise DatabaseValidationError(
                    f"Entrada duplicada: {error_msg}",
                    error_code=str(error_code)
                )
            elif error_code == 1146:  # Table doesn't exist
                raise DatabaseQueryError(
                    f"Tabla no existe: {error_msg}",
                    error_code=str(error_code)
                )
            elif error_code == 1054:  # Unknown column
                raise DatabaseQueryError(
                    f"Columna desconocida: {error_msg}",
                    error_code=str(error_code)
                )
            else:
                raise DatabaseQueryError(
                    f"Error de base de datos: {error_msg}",
                    error_code=str(error_code)
                )
        except Exception as e:
            if isinstance(e, (DatabaseConnectionError, DatabaseQueryError, 
                            DatabaseTransactionError, DatabasePoolError, 
                            DatabaseValidationError)):
                raise
            else:
                raise DatabaseQueryError(f"Error inesperado en base de datos: {str(e)}")
    
    return wrapper


def handle_selenium_exceptions(func: Callable) -> Callable:
    """
    Decorator para manejar excepciones de Selenium
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TimeoutException as e:
            raise SeleniumTimeoutError(
                f"Timeout en operación de Selenium: {str(e)}",
                timeout=getattr(e, 'timeout', None),
                operation=func.__name__
            )
        except NoSuchElementException as e:
            raise SeleniumElementNotFoundError(
                f"Elemento no encontrado: {str(e)}",
                selector=getattr(e, 'selector', None),
                selector_type=getattr(e, 'selector_type', None)
            )
        except ElementNotInteractableException as e:
            raise SeleniumElementNotFoundError(
                f"Elemento no interactuable: {str(e)}",
                selector=getattr(e, 'selector', None),
                selector_type=getattr(e, 'selector_type', None)
            )
        except StaleElementReferenceException as e:
            raise SeleniumElementNotFoundError(
                f"Referencia de elemento obsoleta: {str(e)}",
                selector=getattr(e, 'selector', None),
                selector_type=getattr(e, 'selector_type', None)
            )
        except WebDriverException as e:
            if "chrome" in str(e).lower() or "chromedriver" in str(e).lower():
                raise SeleniumDriverError(
                    f"Error del driver Chrome: {str(e)}",
                    driver_type="Chrome"
                )
            else:
                raise SeleniumDriverError(f"Error del driver: {str(e)}")
        except Exception as e:
            if isinstance(e, (SeleniumDriverError, SeleniumTimeoutError, 
                            SeleniumElementNotFoundError, SeleniumNavigationError, 
                            SeleniumSessionError)):
                raise
            else:
                raise SeleniumDriverError(f"Error inesperado en Selenium: {str(e)}")
    
    return wrapper


def handle_validation_exceptions(func: Callable) -> Callable:
    """
    Decorator para manejar excepciones de validación
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PydanticValidationError as e:
            raise ValidationError(
                f"Error de validación de datos: {str(e)}",
                pydantic_error=e
            )
        except Exception as e:
            if isinstance(e, (ValidationError, ProfileValidationError, 
                            TaskValidationError, FollowingValidationError, 
                            ConfigurationValidationError)):
                raise
            else:
                raise ValidationError(f"Error inesperado en validación: {str(e)}")
    
    return wrapper


def handle_business_exceptions(func: Callable) -> Callable:
    """
    Decorator para manejar excepciones de lógica de negocio
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, (ProfileNotFoundError, ProfilePrivateError, 
                            ProfileBlockedError, InstagramRateLimitError, 
                            InstagramLoginError, TaskProcessingError, WorkerError)):
                raise
            else:
                # Analizar el contexto para determinar el tipo de excepción
                error_msg = str(e).lower()
                if "private" in error_msg or "privada" in error_msg:
                    raise ProfilePrivateError(f"Perfil privado: {str(e)}")
                elif "blocked" in error_msg or "bloqueado" in error_msg:
                    raise ProfileBlockedError(f"Perfil bloqueado: {str(e)}")
                elif "rate limit" in error_msg or "límite" in error_msg:
                    raise InstagramRateLimitError(f"Límite de rate excedido: {str(e)}")
                elif "login" in error_msg or "sesión" in error_msg:
                    raise InstagramLoginError(f"Error de login: {str(e)}")
                elif "not found" in error_msg or "no encontrado" in error_msg:
                    raise ProfileNotFoundError(f"Perfil no encontrado: {str(e)}")
                else:
                    raise TaskProcessingError(f"Error en procesamiento: {str(e)}")
    
    return wrapper


def handle_network_exceptions(func: Callable) -> Callable:
    """
    Decorator para manejar excepciones de red
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, (NetworkConnectionError, NetworkTimeoutError, 
                            ProxyError, InstagramAPIError)):
                raise
            else:
                error_msg = str(e).lower()
                if "timeout" in error_msg:
                    raise NetworkTimeoutError(f"Timeout de red: {str(e)}")
                elif "connection" in error_msg or "conexión" in error_msg:
                    raise NetworkConnectionError(f"Error de conexión: {str(e)}")
                elif "proxy" in error_msg:
                    raise ProxyError(f"Error de proxy: {str(e)}")
                else:
                    raise NetworkConnectionError(f"Error de red: {str(e)}")
    
    return wrapper


def log_exception_details(exception: Exception, context: Optional[Dict[str, Any]] = None):
    """
    Registra detalles específicos de una excepción
    """
    context = context or {}
    
    # Log del error principal
    logger.error(f"Excepción capturada: {type(exception).__name__}: {str(exception)}")
    
    # Log del contexto adicional
    if context:
        logger.error(f"Contexto: {context}")
    
    # Log de atributos específicos de la excepción
    if hasattr(exception, 'context') and exception.context:
        logger.error(f"Contexto de excepción: {exception.context}")
    
    # Log del stack trace
    logger.debug(f"Stack trace: {traceback.format_exc()}")


def create_exception_response(exception: Exception, 
                            default_message: str = "Error interno del servidor") -> Dict[str, Any]:
    """
    Crea una respuesta estructurada para una excepción
    """
    response = {
        "error": True,
        "message": str(exception),
        "type": type(exception).__name__,
        "timestamp": None  # Se puede añadir timestamp si es necesario
    }
    
    # Añadir información específica según el tipo de excepción
    if hasattr(exception, 'error_code'):
        response["error_code"] = exception.error_code
    
    if hasattr(exception, 'context') and exception.context:
        response["context"] = exception.context
    
    # Añadir información de retry si aplica
    if isinstance(exception, InstagramRateLimitError):
        if hasattr(exception, 'retry_after'):
            response["retry_after"] = exception.retry_after
        response["retryable"] = True
    elif isinstance(exception, (NetworkTimeoutError, NetworkConnectionError)):
        response["retryable"] = True
    else:
        response["retryable"] = False
    
    return response


def safe_execute(func: Callable, *args, **kwargs) -> tuple[bool, Any, Optional[Exception]]:
    """
    Ejecuta una función de forma segura y retorna (success, result, exception)
    """
    try:
        result = func(*args, **kwargs)
        return True, result, None
    except Exception as e:
        log_exception_details(e)
        return False, None, e


def retry_on_exception(max_retries: int = 3, 
                      retryable_exceptions: tuple = (NetworkTimeoutError, NetworkConnectionError),
                      delay: float = 1.0):
    """
    Decorator para reintentar en caso de excepciones específicas
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if isinstance(e, retryable_exceptions) and attempt < max_retries:
                        logger.warning(f"Intento {attempt + 1} falló, reintentando en {delay}s: {str(e)}")
                        import time
                        time.sleep(delay * (attempt + 1))  # Backoff exponencial
                        continue
                    else:
                        break
            
            # Si llegamos aquí, todos los intentos fallaron
            raise last_exception
        
        return wrapper
    return decorator
