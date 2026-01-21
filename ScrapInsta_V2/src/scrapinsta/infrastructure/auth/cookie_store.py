from __future__ import annotations
import json, time, os
from pathlib import Path
from typing import Any, Dict, Optional
from scrapinsta.config.settings import Settings
from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("cookie_store")

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
        log.warning("cookies_read_failed", path=str(path), error=str(e))
        return False

def save_cookies(driver, username: str) -> None:
    path = cookie_path(username)
    cookies = driver.get_cookies()
    path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("cookies_saved", username=username, path=str(path))

def load_cookies(driver, username: str, *, base_url: str = "https://www.instagram.com/", require_sessionid: bool = True) -> bool:
    path = cookie_path(username)
    if not path.exists():
        log.info("cookies_file_missing", username=username)
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            log.warning("cookies_file_invalid", path=str(path))
            return False

        if require_sessionid and not has_sessionid(username):
            log.info("cookies_missing_or_expired_sessionid", username=username)
            return False

        try:
            driver.get(base_url)
        except Exception:
            log.debug("cookies_preload_nav_failed", base_url=base_url)

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
                log.debug("cookie_add_failed", name=c.get("name"))

        log.info("cookies_loaded", username=username, loaded=loaded)
        return loaded > 0

    except Exception as e:
        log.error("cookies_load_failed", path=str(path), error=str(e))
        return False

def clear_cookies_file(username: str) -> None:
    path = cookie_path(username)
    try:
        if path.exists():
            path.unlink()
            log.info("cookies_file_deleted", username=username, path=str(path))
    except Exception:
        log.warning("cookies_file_delete_failed", username=username, path=str(path))

