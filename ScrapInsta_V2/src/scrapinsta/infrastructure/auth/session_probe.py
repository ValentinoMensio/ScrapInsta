from __future__ import annotations

"""
Utilidades mínimas para sondear si el driver ya tiene una sesión activa
de Instagram, evitando disparar el login UI cuando no es necesario.

Diseño:
- No asume nada del resto del sistema (no importa Settings ni cookie_store).
- No persiste ni modifica cookies; sólo observa.
- "Best effort": primero inspecciona cookies, luego intenta una heurística de DOM.

Uso típico desde la factory o SessionService:
    from scrapinsta.infrastructure.auth.session_probe import has_active_session_in_driver
    if not has_active_session_in_driver(driver):
        # cargar cookies y/o iniciar login interactivo
"""

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
        # Presencia de input username o password es un buen indicador de pantalla de login
        login_username = wait.until(
            EC.presence_of_all_elements_located((By.NAME, "username"))
        )
        if login_username:
            return True
    except TimeoutException:
        # No apareció el formulario en el tiempo dado -> probablemente NO sea la pantalla de login
        return False
    except WebDriverException:
        # Errores transitorios de webdriver: no afirmar que es login
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
    # 1) Intentar llegar al home (no abortar por fallos transitorios)
    try:
        driver.get(base_url)
    except Exception:
        logger.debug("session_probe: error navegando a %s", base_url, exc_info=True)

    # 2) Cookie de sesión
    if _has_session_cookie(driver):
        return True

    # 3) ¿Se ve la pantalla de login?
    if _looks_like_login_page(driver, timeout=timeout_s):
        return False

    # 4) Caso ambiguo: no vimos login, tampoco cookie conocida -> asumir NO activa
    #    (podría ser un splash/landing; que el caller decida intentar cargar cookies).
    return False
