"""
Funciones helper para validación de datos
"""
import logging
from typing import Any, Dict, List, Optional, Type, Union
from pydantic import BaseModel, ValidationError
from schemas.profile_schemas import ProfileData, ProfileCreate, ProfileUpdate, ProfileAnalysisResult
from schemas.task_schemas import TaskData, AnalyzeTask, FetchFollowingsTask, SendMessageTask, TaskResult
from schemas.database_schemas import FollowingData, FollowingCreate, FollowingList

logger = logging.getLogger(__name__)


def validate_data(data: Dict[str, Any], schema_class: Type[BaseModel], context: str = "") -> Optional[BaseModel]:
    """
    Valida datos usando un esquema de Pydantic
    
    Args:
        data: Diccionario con los datos a validar
        schema_class: Clase del esquema de Pydantic
        context: Contexto para logging (opcional)
        
    Returns:
        Instancia validada del esquema o None si hay error
    """
    try:
        validated_data = schema_class(**data)
        logger.debug(f"Datos validados exitosamente para {context}")
        return validated_data
    except ValidationError as e:
        logger.error(f"Error de validación en {context}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado validando datos en {context}: {e}")
        return None


def validate_profile_data(profile_data: Dict[str, Any]) -> Optional[ProfileData]:
    """
    Valida datos de perfil de Instagram
    
    Args:
        profile_data: Diccionario con datos del perfil
        
    Returns:
        ProfileData validado o None si hay error
    """
    return validate_data(profile_data, ProfileData, "perfil de Instagram")


def validate_profile_create(profile_data: Dict[str, Any]) -> Optional[ProfileCreate]:
    """
    Valida datos para crear un perfil
    
    Args:
        profile_data: Diccionario con datos del perfil
        
    Returns:
        ProfileCreate validado o None si hay error
    """
    return validate_data(profile_data, ProfileCreate, "creación de perfil")


def validate_profile_update(profile_data: Dict[str, Any]) -> Optional[ProfileUpdate]:
    """
    Valida datos para actualizar un perfil
    
    Args:
        profile_data: Diccionario con datos del perfil
        
    Returns:
        ProfileUpdate validado o None si hay error
    """
    return validate_data(profile_data, ProfileUpdate, "actualización de perfil")


def validate_task_data(task_data: Dict[str, Any]) -> Optional[TaskData]:
    """
    Valida datos de tarea
    
    Args:
        task_data: Diccionario con datos de la tarea
        
    Returns:
        TaskData validado o None si hay error
    """
    return validate_data(task_data, TaskData, "tarea del sistema")


def validate_analyze_task(task_data: Dict[str, Any]) -> Optional[AnalyzeTask]:
    """
    Valida tarea de análisis
    
    Args:
        task_data: Diccionario con datos de la tarea
        
    Returns:
        AnalyzeTask validado o None si hay error
    """
    return validate_data(task_data, AnalyzeTask, "tarea de análisis")


def validate_fetch_followings_task(task_data: Dict[str, Any]) -> Optional[FetchFollowingsTask]:
    """
    Valida tarea de obtención de followings
    
    Args:
        task_data: Diccionario con datos de la tarea
        
    Returns:
        FetchFollowingsTask validado o None si hay error
    """
    return validate_data(task_data, FetchFollowingsTask, "tarea de followings")


def validate_send_message_task(task_data: Dict[str, Any]) -> Optional[SendMessageTask]:
    """
    Valida tarea de envío de mensaje
    
    Args:
        task_data: Diccionario con datos de la tarea
        
    Returns:
        SendMessageTask validado o None si hay error
    """
    return validate_data(task_data, SendMessageTask, "tarea de mensaje")


def validate_following_data(following_data: Dict[str, Any]) -> Optional[FollowingData]:
    """
    Valida datos de following
    
    Args:
        following_data: Diccionario con datos del following
        
    Returns:
        FollowingData validado o None si hay error
    """
    return validate_data(following_data, FollowingData, "following")


def validate_following_create(following_data: Dict[str, Any]) -> Optional[FollowingCreate]:
    """
    Valida datos para crear following
    
    Args:
        following_data: Diccionario con datos del following
        
    Returns:
        FollowingCreate validado o None si hay error
    """
    return validate_data(following_data, FollowingCreate, "creación de following")


def validate_following_list(following_data: Dict[str, Any]) -> Optional[FollowingList]:
    """
    Valida lista de followings
    
    Args:
        following_data: Diccionario con datos de followings
        
    Returns:
        FollowingList validado o None si hay error
    """
    return validate_data(following_data, FollowingList, "lista de followings")


def validate_task_result(result_data: Dict[str, Any]) -> Optional[TaskResult]:
    """
    Valida resultado de tarea
    
    Args:
        result_data: Diccionario con datos del resultado
        
    Returns:
        TaskResult validado o None si hay error
    """
    return validate_data(result_data, TaskResult, "resultado de tarea")


def safe_validate_profile_data(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validación segura de datos de perfil con valores por defecto
    
    Args:
        profile_data: Diccionario con datos del perfil
        
    Returns:
        Diccionario con datos validados y valores por defecto
    """
    try:
        validated = validate_profile_data(profile_data)
        if validated:
            return validated.dict()
    except Exception as e:
        logger.warning(f"Error validando perfil, usando valores por defecto: {e}")
    
    # Valores por defecto seguros
    return {
        'username': profile_data.get('username', 'unknown'),
        'bio': profile_data.get('bio', ''),
        'followers': max(0, profile_data.get('followers', 0)),
        'following': max(0, profile_data.get('following', 0)),
        'posts': max(0, profile_data.get('posts', 0)),
        'avg_likes': max(0.0, profile_data.get('avg_likes', 0.0)),
        'avg_comments': max(0.0, profile_data.get('avg_comments', 0.0)),
        'avg_views': max(0.0, profile_data.get('avg_views', 0.0)),
        'is_private': bool(profile_data.get('is_private', False)),
        'is_verified': bool(profile_data.get('is_verified', False)),
        'engagement_score': max(0.0, min(1.0, profile_data.get('engagement_score', 0.0))),
        'success_score': max(0.0, min(1.0, profile_data.get('success_score', 0.0))),
        'rubro': profile_data.get('rubro', 'unknown')
    }


def validate_username(username: str) -> Optional[str]:
    """
    Valida y normaliza un username de Instagram
    
    Args:
        username: Username a validar
        
    Returns:
        Username validado y normalizado o None si es inválido
    """
    if not username or not isinstance(username, str):
        return None
    
    username = username.strip()
    if len(username) == 0 or len(username) > 30:
        return None
    
    # Validar caracteres permitidos en Instagram
    if not username.replace('_', '').replace('.', '').isalnum():
        return None
    
    return username.lower()


def validate_rubro(rubro: str) -> Optional[str]:
    """
    Valida y normaliza un rubro
    
    Args:
        rubro: Rubro a validar
        
    Returns:
        Rubro validado y normalizado o None si es inválido
    """
    if not rubro or not isinstance(rubro, str):
        return None
    
    rubro = rubro.strip()
    if len(rubro) == 0 or len(rubro) > 100:
        return None
    
    return rubro.title()


def validate_following_list_data(followings: List[str]) -> List[str]:
    """
    Valida y normaliza una lista de followings
    
    Args:
        followings: Lista de usernames
        
    Returns:
        Lista de usernames validados y normalizados
    """
    if not followings or not isinstance(followings, list):
        return []
    
    validated_followings = []
    for username in followings:
        validated_username = validate_username(username)
        if validated_username:
            validated_followings.append(validated_username)
    
    return validated_followings


def log_validation_error(error: ValidationError, context: str = ""):
    """
    Log detallado de errores de validación
    
    Args:
        error: Error de validación de Pydantic
        context: Contexto para el log
    """
    logger.error(f"Error de validación en {context}:")
    for err in error.errors():
        field = err.get('loc', ['unknown'])[-1]
        message = err.get('msg', 'Error desconocido')
        value = err.get('input', 'N/A')
        logger.error(f"  Campo '{field}': {message} (valor: {value})")


def create_validation_summary(validated_data: BaseModel, context: str = "") -> Dict[str, Any]:
    """
    Crea un resumen de datos validados
    
    Args:
        validated_data: Datos validados
        context: Contexto para el resumen
        
    Returns:
        Diccionario con resumen de validación
    """
    return {
        'context': context,
        'validated': True,
        'fields_count': len(validated_data.dict()),
        'data_type': type(validated_data).__name__,
        'timestamp': validated_data.dict().get('timestamp')
    }
