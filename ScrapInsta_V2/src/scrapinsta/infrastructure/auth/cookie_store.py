from __future__ import annotations
import json, logging, time, os
from pathlib import Path
from typing import Any, Dict, Optional
from scrapinsta.config.settings import Settings

logger = logging.getLogger(__name__)

def cookies_dir() -> Path:
    """Devuelve el directorio donde se guardan las cookies (según settings)."""
    settings = Settings()
    base = settings.get_data_dir()  # siempre resuelve y crea <data_dir>
    cookies = base / "cookies"
    cookies.mkdir(parents=True, exist_ok=True)
    return cookies

def cookie_path(username: str) -> Path:
    """Ruta al archivo JSON de cookies del usuario."""
    if not username:
        raise ValueError("username requerido para cookie_path()")
    return cookies_dir() / f"{username.strip().lower()}.json"

def _normalize_expiry(cookie: Dict[str, Any]) -> Optional[int]:
    exp = cookie.get("expiry")
    if exp is None:
        return None
    try:
        if isinstance(exp, (int, float)):
            return int(exp)
        if isinstance(exp, str) and exp.strip():
            return int(float(exp.strip()))
    except Exception:
        pass
    return None

def _filter_cookie_fields(cookie: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"name", "value", "domain", "path", "expiry", "httpOnly", "secure", "sameSite"}
    filtered = {k: v for k, v in cookie.items() if k in allowed}
    filtered.setdefault("path", "/")

    exp = _normalize_expiry(filtered)
    if exp is not None:
        filtered["expiry"] = exp
    else:
        filtered.pop("expiry", None)

    for key in ("httpOnly", "secure"):
        if key in filtered and isinstance(filtered[key], str):
            filtered[key] = filtered[key].lower() == "true"

    return filtered

def has_sessionid(username: str) -> bool:
    path = cookie_path(username)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        now = int(time.time())
        for c in data if isinstance(data, list) else []:
            if c.get("name") == "sessionid":
                exp = _normalize_expiry(c)
                if exp is None or exp > now:
                    return True
        return False
    except Exception as e:
        logger.warning("Error leyendo cookies %s: %s", path, e)
        return False

def save_cookies(driver, username: str) -> None:
    path = cookie_path(username)
    cookies = driver.get_cookies()
    path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Cookies guardadas para %s en %s", username, path)

def load_cookies(driver, username: str, *, base_url: str = "https://www.instagram.com/", require_sessionid: bool = True) -> bool:
    path = cookie_path(username)
    if not path.exists():
        logger.info("No se encontró archivo de cookies para %s", username)
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("Archivo inválido de cookies: %s", path)
            return False

        if require_sessionid and not has_sessionid(username):
            logger.info("Cookies de %s expiradas o sin sessionid", username)
            return False

        try:
            driver.get(base_url)
        except Exception:
            logger.debug("Error navegando a %s antes de cargar cookies", base_url, exc_info=True)

        loaded = 0
        for c in data:
            try:
                cookie = _filter_cookie_fields(c)
                if not cookie.get("name") or cookie.get("value") is None:
                    continue
                if not cookie.get("domain"):
                    cookie["domain"] = ".instagram.com"
                driver.add_cookie(cookie)
                loaded += 1
            except Exception:
                logger.debug("Error al añadir cookie %s", c.get("name"), exc_info=True)

        logger.info("Cargadas %d cookies para %s", loaded, username)
        return loaded > 0

    except Exception as e:
        logger.error("Error cargando cookies %s: %s", path, e)
        return False

def clear_cookies_file(username: str) -> None:
    path = cookie_path(username)
    try:
        if path.exists():
            path.unlink()
            logger.info("Archivo de cookies eliminado para %s", username)
    except Exception:
        logger.warning("No se pudo eliminar cookies %s", path, exc_info=True)

