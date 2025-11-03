from __future__ import annotations

import logging
from typing import Optional

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


def _has_session_cookie(driver) -> bool:
    """
    Heurística 1: existe cookie 'sessionid' (o 'ds_user_id') en el perfil/cookies cargadas.
    No valida expiración (Chrome/driver ya filtra expiradas al exponerlas).
    """
    try:
        for c in driver.get_cookies():
            name = (c.get("name") or "").lower()
            if name in ("sessionid", "ds_user_id"):
                return True
    except Exception:
        logger.debug("session_probe: fallo leyendo cookies", exc_info=True)
    return False


def _looks_like_login_page(driver, timeout: float) -> bool:
    """
    Heurística 2: detectar la UI de login.
    Buscamos campos del formulario de login. Si aparecen rápido, asumimos que NO hay sesión.
    Si no aparecen y tampoco fallan los waits, asumimos que probablemente sí hay sesión.
    """
    try:
        wait = WebDriverWait(driver, timeout)
        login_username = wait.until(
            EC.presence_of_all_elements_located((By.NAME, "username"))
        )
        if login_username:
            return True
    except TimeoutException:
        return False
    except WebDriverException:
        logger.debug("session_probe: error sondando DOM login", exc_info=True)
        return False
    return False


def has_active_session_in_driver(
    driver,
    *,
    base_url: str = "https://www.instagram.com/",
    timeout_s: float = 6.0,
) -> bool:
    """
    Devuelve True si el driver parece tener una sesión activa de Instagram.

    Estrategia:
      1) Navegar al home (best-effort).
      2) Si ya hay cookie de sesión conocida -> True.
      3) Si NO hay cookie, inspeccionar DOM para ver si carga la pantalla de login -> False si es login.

    Notas:
      - Es una heurística conservadora (preferimos no forzar login si ya hay sesión).
      - No levanta excepciones: ante dudas, intenta ser permisivo y devolver False sólo si vemos el login.
    """
    try:
        driver.get(base_url)
    except Exception:
        logger.debug("session_probe: error navegando a %s", base_url, exc_info=True)

    if _has_session_cookie(driver):
        return True


    if _looks_like_login_page(driver, timeout=timeout_s):
        return False

    return False
