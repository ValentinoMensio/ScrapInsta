import logging
import json
import os
from core.utils.undetected import random_sleep

logger = logging.getLogger(__name__)

COOKIES_DIR = "data/cookies"

def get_cookie_path(username):
    """Obtiene la ruta del archivo de cookies para un usuario específico."""
    return os.path.join(COOKIES_DIR, f"{username}.json")

def save_cookies(driver, username):
    """Guarda las cookies del navegador en un archivo JSON para un usuario específico."""
    file_path = get_cookie_path(username)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    cookies = driver.get_cookies()
    with open(file_path, "w") as file:
        json.dump(cookies, file, indent=4)
    logger.info(f"Cookies guardadas para {username} en {file_path}")

def has_sessionid(username):
    """Verifica si existe un sessionid válido para el usuario dado."""
    file_path = get_cookie_path(username)
    try:
        with open(file_path, "r") as file:
            cookies = json.load(file)
            for cookie in cookies:
                if cookie.get("name") == "sessionid":
                    logger.info(f"Sessionid encontrado para {username}: {cookie.get('value')[:10]}...")
                    return True
        logger.warning(f"No se encontró sessionid en las cookies para {username}.")
        return False
    except Exception as e:
        logger.error(f"Error al verificar sessionid para {username}: {e}")
        return False

def load_cookies(driver, username):
    """Carga las cookies desde un archivo JSON al navegador para un usuario específico."""
    file_path = get_cookie_path(username)
    try:
        driver.get("https://www.instagram.com/")
        random_sleep(1.0, 2.0)
        driver.delete_all_cookies()

        with open(file_path, "r") as file:
            cookies = json.load(file)

        for cookie in cookies:
            if 'instagram.com' not in cookie.get('domain', ''):
                cookie['domain'] = '.instagram.com'
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.error(f"Error al añadir cookie {cookie.get('name')} para {username}: {e}")

        logger.info(f"Cookies cargadas para {username} desde {file_path}")
        return True

    except FileNotFoundError:
        logger.error(f"Archivo de cookies no encontrado para {username} en {file_path}")
        return False
    except json.JSONDecodeError:
        logger.error(f"Error decodificando archivo JSON para {username} en {file_path}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al cargar cookies para {username}: {str(e)}")
        return False
