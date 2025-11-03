from __future__ import annotations

import logging
from typing import Optional, Callable

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from scrapinsta.domain.ports.browser_port import BrowserAuthError
from scrapinsta.infrastructure.auth.cookie_store import (
    has_sessionid,
    load_cookies,
    clear_cookies_file,
)
from scrapinsta.infrastructure.auth.login_flow import login_instagram

logger = logging.getLogger(__name__)


def _is_logged_in(driver: WebDriver, timeout: int = 10) -> bool:
    """
    Señales inequívocas de sesión autenticada.
    Se alinea con la verificación usada en login_flow.
    """
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[contains(@href,'/direct/inbox/')]")
                ),
                EC.presence_of_element_located(
                    (By.XPATH, "//a[contains(@href,'/accounts/edit')]")
                ),
                EC.presence_of_element_located(
                    (By.XPATH, "//a[contains(@href,'/explore/')]")
                ),
                EC.presence_of_element_located(
                    (By.XPATH, "//button[contains(.,'Log out') or contains(.,'Cerrar sesión')]")
                ),
            )
        )
        return True
    except Exception:
        return False


class SessionService:
    """
    Orquesta el establecimiento de sesión en Instagram:
      1) Cookie-first: si hay sessionid válido -> cargar cookies y verificar sesión.
      2) Si no, login interactivo (que persiste cookies sólo si verifica sesión).
    - Nunca deja cookies inválidas en disco: si algo falla, las borra.
    - No guarda cookies si el login no es exitoso (lo garantiza login_instagram).
    """

    def __init__(
        self,
        driver: WebDriver,
        *,
        username: str,
        password: Optional[str],
        base_url: str = "https://www.instagram.com/",
        login_url: str = "https://www.instagram.com/accounts/login/",
        two_factor_code_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        self._driver = driver
        self._username = (username or "").strip()
        self._password = password
        self._base_url = base_url
        self._login_url = login_url
        self._two_factor_code_provider = two_factor_code_provider

    def ensure_session(self) -> None:
        """
        Establece sesión. Intenta primero con cookies, si no, con login.
        Lanza BrowserAuthError con mensaje corto y útil si falla.
        """
        if not self._username:
            raise BrowserAuthError("Username vacío para sesión", username=self._username)

        logger.info("[%s] Iniciando login interactivo…", self._username)

        # 1) Intento vía cookies (cookie-first)
        if self._try_cookies_first():
            logger.info("[%s] Sesión verificada con cookies", self._username)
            return

        # 2) Login interactivo (si cookies no funcionaron o no existen)
        self._login_and_persist()

    # -----------------------------
    # Internals
    # -----------------------------
    def _try_cookies_first(self) -> bool:
        """
        Intenta establecer sesión sólo con cookies si hay sessionid válido.
        Nunca guarda cookies aquí; sólo las carga (persistencia está en login_flow).
        """
        try:
            if not has_sessionid(self._username):
                logger.debug("[%s] No hay sessionid válido en cookies", self._username)
                return False

            # Cargar cookies y verificar
            if not load_cookies(self._driver, self._username):
                logger.debug("[%s] No se pudieron cargar cookies", self._username)
                return False

            # Navegar al home y verificar señales de sesión
            self._driver.get(self._base_url)
            if _is_logged_in(self._driver, timeout=10):
                return True

            logger.debug("[%s] Cookies cargadas pero no se verificó sesión", self._username)
            # Si llegamos aquí, las cookies no sirven: limpiar archivo para evitar loops
            clear_cookies_file(self._username)
            return False

        except Exception as e:
            logger.debug("[%s] Error usando cookies: %s", self._username, e, exc_info=True)
            # Cualquier error de lectura/decode deja el archivo limpio
            try:
                clear_cookies_file(self._username)
            except Exception:
                pass
            return False

    def _login_and_persist(self) -> None:
        """
        Hace login interactivo y deja que login_flow persista cookies
        sólo si la sesión es verificada. Si falla, borra cookies.
        """
        try:
            login_instagram(
                self._driver,
                username=self._username,
                password=self._password,
                base_url=self._base_url,
                login_url=self._login_url,
                two_factor_code_provider=self._two_factor_code_provider,
            )
            # login_flow guarda cookies sólo si verifica sesión.
            # Aun así, verificamos aquí por robustez:
            if not _is_logged_in(self._driver, timeout=10):
                raise BrowserAuthError(
                    "No se pudo verificar sesión tras login",
                    username=self._username,
                )

        except BrowserAuthError:
            # Aseguramos no dejar cookies rotas (login_flow ya lo intenta también)
            try:
                clear_cookies_file(self._username)
            except Exception:
                pass
            raise

        except Exception as e:
            # Cualquier excepción inesperada se normaliza a BrowserAuthError
            try:
                clear_cookies_file(self._username)
            except Exception:
                pass
            raise BrowserAuthError(
                f"Error inesperado en login: {e}",
                username=self._username,
            ) from e
