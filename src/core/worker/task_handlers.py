import time
import logging
from config.settings import RETRY_CONFIG, INSTAGRAM_CONFIG
from core.profile.fetch_profile import analyze_profile
from core.profile.fetch_followings import fetch_followings
from db.repositories import save_followings, save_profile_to_db
from core.utils.selenium_helpers import is_logged_in
from core.profile.send_message import send_message
from core.worker.messages import (
    RES_PROFILE_ANALYZED,
    RES_FOLLOWINGS_FETCHED,
    RES_MESSAGE_SENT,
    RES_ERROR
)
from utils.validation_helpers import (
    validate_analyze_task,
    validate_fetch_followings_task,
    validate_send_message_task,
    log_validation_error
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)

def ensure_driver_and_session(driver, initialize_func, initialize_session_func):
    """
    Verifica que el driver esté activo y que la sesión esté iniciada.
    Reinicia el driver o la sesión si es necesario.
    """
    try:
        _ = driver.current_url
    except Exception:
        logger.info("Driver no responde, reiniciando...")
        if not initialize_func():
            raise Exception("No se pudo reiniciar el driver")
        if not initialize_session_func():
            raise Exception("No se pudo refrescar la sesión tras reiniciar el driver")

    if not is_logged_in(driver):
        logger.info("Sesión no activa, refrescando...")
        if not initialize_session_func():
            raise Exception("No se pudo refrescar la sesión")

def handle_analyze_profiles(driver, task, initialize_func, initialize_session_func, has_session):
    # Validar datos de la tarea
    try:
        validated_task = validate_analyze_task(task)
        if not validated_task:
            error_msg = "Datos de tarea de análisis inválidos"
            logger.error(error_msg)
            return {'type': RES_ERROR, 'error': error_msg}
        
        username = validated_task.profile
        logger.info(f"Analizando perfil: {username}")
    except ValidationError as e:
        log_validation_error(e, "tarea de análisis")
        return {'type': RES_ERROR, 'error': f"Error de validación: {str(e)}"}
    except Exception as e:
        logger.error(f"Error validando tarea de análisis: {e}")
        return {'type': RES_ERROR, 'error': f"Error inesperado: {str(e)}"}

    for attempt in range(RETRY_CONFIG['max_retries']):
        try:
            ensure_driver_and_session(driver, initialize_func, initialize_session_func)

            profile_result = analyze_profile(
                driver=driver,
                username=username,
                max_profiles=None,
                has_session=has_session
            )

            if profile_result.get('status') == 'error':
                logger.info(f"{username} - Sin coincidencia de rubro (resultado válido)")
                return {
                    'type': RES_PROFILE_ANALYZED,
                    'results': [{
                        'username': username,
                        'status': profile_result.get('reason', 'no_match'),
                        'data': None
                    }]
                }

            if profile_result.get('status') == 'success':
                profile_id = save_profile_to_db(profile_result)
                if profile_id is None:
                    logger.error(f"Error guardando perfil {username} en la base de datos")
                    return {
                        'type': RES_PROFILE_ANALYZED,
                        'results': [{
                            'username': username,
                            'status': 'db_error',
                            'error': 'No se pudo guardar el perfil en la base de datos'
                        }]
                    }

                logger.info(f"Perfil {username} analizado exitosamente")
                return {
                    'type': RES_PROFILE_ANALYZED,
                    'results': [{
                        'username': username,
                        'status': 'success',
                        'data': profile_result
                    }]
                }

            # Si por alguna razón no fue ni success ni error explícito
            logger.warning(f"Resultado inesperado para {username}: {profile_result}")
            return {
                'type': RES_PROFILE_ANALYZED,
                'results': [{
                    'username': username,
                    'status': RES_ERROR,
                    'error': 'Resultado desconocido del análisis'
                }]
            }

        except Exception as e:
            logger.error(f"Intento {attempt + 1} fallido para {username}: {e}")
            if attempt < RETRY_CONFIG['max_retries'] - 1:
                time.sleep(RETRY_CONFIG['initial_delay'] * (attempt + 1))
                continue
            # Último intento: devolvés error
            return {
                'type': RES_PROFILE_ANALYZED,
                'results': [{
                    'username': username,
                    'status': RES_ERROR,
                    'error': str(e)
                }]
            }



def handle_fetch_followings(driver, task, initialize_func, initialize_session_func):
    # Validar datos de la tarea
    try:
        validated_task = validate_fetch_followings_task(task)
        if not validated_task:
            error_msg = "Datos de tarea de followings inválidos"
            logger.error(error_msg)
            return {'type': RES_ERROR, 'error': error_msg}
        
        username = validated_task.profile
        limit = validated_task.max_followings or INSTAGRAM_CONFIG.get('max_followings') or 12
        logger.info(f"Obteniendo seguidores de {username} (límite: {limit})")
    except ValidationError as e:
        log_validation_error(e, "tarea de followings")
        return {'type': RES_ERROR, 'error': f"Error de validación: {str(e)}"}
    except Exception as e:
        logger.error(f"Error validando tarea de followings: {e}")
        return {'type': RES_ERROR, 'error': f"Error inesperado: {str(e)}"}
    
    followings = []

    for attempt in range(RETRY_CONFIG['max_retries']):
        try:
            ensure_driver_and_session(driver, initialize_func, initialize_session_func)

            followings = fetch_followings(
                driver=driver,
                username_origin=username,
                max_followings=limit
            )

            if followings:
                save_followings(username, followings)
            break

        except Exception as e:
            logger.error(f"Error obteniendo seguidores para {username}: {e}")
            if attempt == RETRY_CONFIG['max_retries'] - 1:
                return {'type': RES_ERROR, 'error': str(e)}
            time.sleep(RETRY_CONFIG['initial_delay'] * (attempt + 1))

    return {
        'type': RES_FOLLOWINGS_FETCHED,
        'data': {
            'origin': username,
            'followings': followings
        }
    }


def handle_send_message(driver, task, initialize_session_func):
    # Validar datos de la tarea
    try:
        validated_task = validate_send_message_task(task)
        if not validated_task:
            error_msg = "Datos de tarea de mensaje inválidos"
            logger.error(error_msg)
            return {'type': RES_ERROR, 'error': error_msg}
        
        username = validated_task.profile
        max_retries = validated_task.max_retries or 3
        logger.info(f"Enviando mensaje a {username} (max reintentos: {max_retries})")
    except ValidationError as e:
        log_validation_error(e, "tarea de mensaje")
        return {'type': RES_ERROR, 'error': f"Error de validación: {str(e)}"}
    except Exception as e:
        logger.error(f"Error validando tarea de mensaje: {e}")
        return {'type': RES_ERROR, 'error': f"Error inesperado: {str(e)}"}
    
    error = None

    for attempt in range(max_retries):
        try:
            if not is_logged_in(driver):
                logger.info("Sesión expirada, refrescando...")
                if not initialize_session_func():
                    raise Exception("No se pudo refrescar la sesión")

            success = send_message(driver, username)
            if not success:
                raise Exception("La función send_message devolvió False")

            logger.info(f"Mensaje enviado exitosamente a {username}")
            return {
                'type': RES_MESSAGE_SENT,
                'profile': username
            }

        except Exception as e:
            error = str(e)
            logger.error(f"Intento {attempt + 1} fallido al enviar mensaje a {username}: {error}")
            if attempt < max_retries - 1:
                wait_time = RETRY_CONFIG['initial_delay'] * (attempt + 1)
                logger.info(f"Reintentando en {wait_time} segundos...")
                time.sleep(wait_time)

    return {
        'type': RES_ERROR,
        'error': f"Fallo después de {max_retries} intentos al enviar mensaje a {username}: {error}"
    }
