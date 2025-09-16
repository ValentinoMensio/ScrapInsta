from core.utils.parse import parse_number
import logging
from typing import Dict, Any, Optional, List
from .connection import get_db_connection_context
from utils.validation_helpers import (
    validate_following_list,
    validate_profile_create,
    safe_validate_profile_data,
    log_validation_error
)
from utils.exception_handlers import handle_database_exceptions, log_exception_details
from schemas.database_schemas import FollowingList
from schemas.profile_schemas import ProfileCreate
from pydantic import ValidationError
from exceptions.database_exceptions import (
    DatabaseQueryError, DatabaseTransactionError, DatabaseValidationError
)
from exceptions.validation_exceptions import FollowingValidationError, ProfileValidationError

logger = logging.getLogger(__name__)

def save_followings(username_origin: str, followings_list: List[str]) -> bool:
    """
    Guarda la lista de followings en la base de datos usando connection pooling
    
    Args:
        username_origin: Usuario del cual se obtuvieron los followings
        followings_list: Lista de usernames seguidos
        
    Returns:
        bool: True si se guardó exitosamente, False en caso contrario
    """
    if not followings_list:
        logger.warning(f"No hay followings para guardar de {username_origin}")
        return True
    
    # Validar datos de entrada
    try:
        following_data = FollowingList(
            username_origin=username_origin,
            followings=followings_list
        )
        validated_followings = following_data.followings
        logger.debug(f"Datos de followings validados: {len(validated_followings)} elementos")
    except ValidationError as e:
        log_validation_error(e, f"followings de {username_origin}")
        raise FollowingValidationError(
            f"Error validando followings de {username_origin}",
            username_origin=username_origin,
            pydantic_error=e
        )
    except Exception as e:
        error_msg = f"Error validando followings de {username_origin}: {e}"
        logger.error(error_msg)
        log_exception_details(e, {'username_origin': username_origin, 'followings_count': len(followings_list)})
        raise FollowingValidationError(
            f"Error inesperado validando followings: {str(e)}",
            username_origin=username_origin
        )
    
    try:
        with get_db_connection_context() as conn:
            cursor = conn.cursor()
            
            # Primero, verificar cuáles ya existen para evitar duplicados
            existing_query = "SELECT username_target FROM followings WHERE username_origin = %s"
            cursor.execute(existing_query, (username_origin,))
            existing_followings = {row[0] for row in cursor.fetchall()}
            
            # Filtrar solo los nuevos followings
            new_followings = [f for f in validated_followings if f not in existing_followings]
            
            if not new_followings:
                logger.info(f"Todos los followings de {username_origin} ya existen en la base de datos")
                return True
            
            # Insertar solo los nuevos
            query = "INSERT INTO followings (username_origin, username_target) VALUES (%s, %s)"
            values = [(username_origin, username_target) for username_target in new_followings]
            cursor.executemany(query, values)
            conn.commit()
            logger.info(f"Followings de {username_origin} guardados exitosamente: {len(new_followings)} nuevos registros (de {len(validated_followings)} total)")
            return True
    except Exception as e:
        error_msg = f"Error guardando followings de {username_origin}: {e}"
        logger.error(error_msg)
        log_exception_details(e, {
            'username_origin': username_origin,
            'followings_count': len(validated_followings),
            'query': query
        })
        
        # Convertir a excepción específica
        if "duplicate entry" in str(e).lower():
            # Los duplicados no son errores críticos, solo log y continuar
            logger.warning(f"Entrada duplicada detectada para {username_origin}: {str(e)}")
            return True  # Considerar como éxito ya que los datos ya existen
        else:
            raise DatabaseQueryError(
                f"Error ejecutando consulta de followings: {str(e)}",
                query=query,
                affected_rows=len(validated_followings)
            )
    finally:
        if 'cursor' in locals():
            cursor.close()

def save_profile_to_db(profile_data: Dict[str, Any]) -> Optional[int]:
    """
    Guarda los datos del perfil en la base de datos usando connection pooling
    
    Args:
        profile_data: Diccionario con los datos del perfil
        
    Returns:
        int: ID del perfil guardado o None si hubo error
    """
    # Filtrar solo los campos relevantes para la base de datos
    db_fields = {
        'username', 'bio', 'followers', 'following', 'posts', 
        'avg_likes', 'avg_comments', 'avg_views', 'is_private', 
        'is_verified', 'engagement_score', 'success_score', 'rubro'
    }
    filtered_data = {k: v for k, v in profile_data.items() if k in db_fields}
    
    # Validar datos de entrada
    try:
        validated_profile = validate_profile_create(filtered_data)
        if not validated_profile:
            logger.error(f"Datos de perfil inválidos para {filtered_data.get('username', 'unknown')}")
            return None
        
        validated_data = validated_profile.dict()
        logger.debug(f"Datos de perfil validados para {validated_data['username']}")
    except ValidationError as e:
        log_validation_error(e, f"perfil {filtered_data.get('username', 'unknown')}")
        return None
    except Exception as e:
        logger.error(f"Error validando perfil {filtered_data.get('username', 'unknown')}: {e}")
        # Usar validación segura como fallback
        validated_data = safe_validate_profile_data(filtered_data)
        logger.warning(f"Usando validación segura para perfil {validated_data['username']}")
    
    try:
        with get_db_connection_context() as conn:
            cursor = conn.cursor()
            
            # Insertar perfil usando la sintaxis moderna de MySQL 8.0
            cursor.execute("""
                INSERT INTO filtered_profiles (
                    username, bio, followers, following,
                    posts, avg_likes, avg_comments, avg_views, is_private, is_verified,
                    engagement_score, success_score, rubro
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                AS new_values
                ON DUPLICATE KEY UPDATE
                    bio = new_values.bio,
                    followers = new_values.followers,
                    following = new_values.following,
                    posts = new_values.posts,
                    avg_likes = new_values.avg_likes,
                    avg_comments = new_values.avg_comments,
                    avg_views = new_values.avg_views,
                    is_private = new_values.is_private,
                    is_verified = new_values.is_verified,
                    rubro = new_values.rubro,
                    engagement_score = new_values.engagement_score,
                    success_score = new_values.success_score
            """, (
                validated_data['username'],
                validated_data['bio'],
                validated_data['followers'],
                validated_data['following'],
                validated_data['posts'],
                validated_data['avg_likes'],
                validated_data['avg_comments'],
                validated_data['avg_views'],
                validated_data['is_private'],
                validated_data['is_verified'],
                validated_data['engagement_score'],
                validated_data['success_score'],
                validated_data['rubro']
            ))
            
            # Obtener el ID del perfil insertado o actualizado
            if cursor.lastrowid:
                profile_id = cursor.lastrowid
            else:
                cursor.execute("SELECT id FROM filtered_profiles WHERE username = %s", (validated_data['username'],))
                result = cursor.fetchone()
                profile_id = result[0] if result else None
            
            if profile_id:
                conn.commit()
                logger.info(f"Perfil {validated_data['username']} guardado exitosamente con ID: {profile_id}")
                return profile_id
                
            return None
            
    except Exception as e:
        logger.error(f"Error guardando perfil {validated_data['username']} en la base de datos: {e}")
        return None
    finally:
        if 'cursor' in locals():
            cursor.close()