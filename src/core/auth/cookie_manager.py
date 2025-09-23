import os
import json
import time
import logging

logger = logging.getLogger(__name__)

COOKIES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cookies")
COOKIES_DIR = os.path.abspath(COOKIES_DIR)

def get_cookie_path(username: str) -> str:
    """Obtiene la ruta del archivo de cookies para un usuario específico."""
    return os.path.join(COOKIES_DIR, f"{username}.json")


def _normalize_expiry(cookie: dict) -> int | None:
    """
    Devuelve el epoch de expiración si existe y es válido.
    Selenium usa 'expiry' (int). A veces quedan como 'expires' o string.
    """
    expiry = cookie.get("expiry", None)
    if expiry is None:
        expiry = cookie.get("expires", None)

    if expiry is None:
        return None

    try:
        return int(float(expiry))
    except Exception:
        return None


def _is_cookie_valid_sessionid(cookie: dict, now: int) -> tuple[bool, str]:
    """
    Valida que la cookie 'sessionid' tenga valor y no esté vencida.
    Devuelve (ok, motivo_si_falla).
    """
    if cookie.get("name") != "sessionid":
        return False, "no_sessionid"

    value = cookie.get("value")
    if not value or not isinstance(value, str) or value.strip() == "":
        return False, "sessionid_vacio"

    expiry_epoch = _normalize_expiry(cookie)
    if expiry_epoch is not None and expiry_epoch <= now:
        return False, f"sessionid_expirado_{expiry_epoch}"

    return True, "ok"


def save_cookies(driver, username: str) -> None:
    """Guarda las cookies del navegador en un archivo JSON para un usuario específico."""
    file_path = get_cookie_path(username)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    cookies = driver.get_cookies()
    with open(file_path, "w") as file:
        json.dump(cookies, file, indent=4)
    logger.info(f"Cookies guardadas para {username} en {file_path}")


def has_sessionid(username: str) -> bool:
    """
    Verifica si existe un sessionid aparentemente válido para el usuario dado.
    Considera:
      - Que exista la cookie 'sessionid'
      - Que tenga value no vacío
      - Que no esté vencida si hay 'expiry'
    """
    file_path = get_cookie_path(username)
    now = int(time.time())
    try:
        with open(file_path, "r") as file:
            cookies = json.load(file)

        if not isinstance(cookies, list):
            logger.warning(f"Formato de cookies inválido para {username} (no es lista).")
            return False

        for cookie in cookies:
            ok, reason = _is_cookie_valid_sessionid(cookie, now)
            if ok:
                val = cookie.get("value", "")
                logger.info(f"sessionid OK para {username}: {val[:10]}... "
                            f"(exp={_normalize_expiry(cookie)})")
                return True
            elif cookie.get("name") == "sessionid":
                logger.warning(f"sessionid inválido para {username}: {reason}")

        logger.warning(f"No se encontró sessionid válido en las cookies para {username}.")
        return False

    except FileNotFoundError:
        logger.info(f"No hay archivo de cookies para {username} en {file_path}")
        return False
    except json.JSONDecodeError:
        logger.error(f"JSON de cookies corrupto para {username} en {file_path}")
        return False
    except Exception as e:
        logger.error(f"Error al verificar sessionid para {username}: {e}")
        return False


def load_cookies(driver, username: str) -> bool:
    """Carga las cookies desde un archivo JSON al navegador para un usuario específico."""
    file_path = get_cookie_path(username)
    try:
        driver.get("https://www.instagram.com/")
        driver.delete_all_cookies()

        with open(file_path, "r") as file:
            cookies = json.load(file)

        if not isinstance(cookies, list):
            logger.error(f"Formato inválido en {file_path}: se esperaba lista de cookies.")
            return False

        for cookie in cookies:
            domain = cookie.get("domain") or ".instagram.com"
            if "instagram.com" not in domain:
                domain = ".instagram.com"
            cookie["domain"] = domain

            if not cookie.get("path"):
                cookie["path"] = "/"

            # Selenium permite: name, value, domain, path, secure, httpOnly, expiry, sameSite (algunas builds)
            allowed = {"name", "value", "domain", "path", "secure", "httpOnly", "expiry", "sameSite"}
            filtered = {k: v for k, v in cookie.items() if k in allowed}

            exp = _normalize_expiry(filtered)
            if exp is not None:
                filtered["expiry"] = exp
            elif "expiry" in filtered and filtered["expiry"] is None:
                filtered.pop("expiry", None)

            if not filtered.get("name") or filtered.get("value") is None:
                continue

            try:
                driver.add_cookie(filtered)
            except Exception as e:
                logger.error(f"Error al añadir cookie {filtered.get('name')} para {username}: {e}")

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
