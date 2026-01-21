from __future__ import annotations

from typing import Optional, Callable

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from scrapinsta.domain.ports.browser_port import BrowserAuthError
from scrapinsta.crosscutting.logging_config import get_logger
from scrapinsta.infrastructure.auth.cookie_store import (
    has_sessionid,
    load_cookies,
    clear_cookies_file,
)
from scrapinsta.infrastructure.auth.login_flow import login_instagram

log = get_logger("session_service")


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

        log.info("session_ensure_start", username=self._username)

        if self._try_cookies_first():
            log.info("session_verified_with_cookies", username=self._username)
            return

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
                log.debug("cookies_no_valid_sessionid", username=self._username)
                return False

            if not load_cookies(self._driver, self._username):
                log.debug("cookies_load_failed", username=self._username)
                return False

            self._driver.get(self._base_url)
            if _is_logged_in(self._driver, timeout=10):
                return True

            log.debug("cookies_loaded_but_not_logged_in", username=self._username)
            clear_cookies_file(self._username)
            return False

        except Exception as e:
            log.debug("cookies_flow_error", username=self._username, error=str(e))
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
            if not _is_logged_in(self._driver, timeout=10):
                raise BrowserAuthError(
                    "No se pudo verificar sesión tras login",
                    username=self._username,
                )

        except BrowserAuthError:
            try:
                clear_cookies_file(self._username)
            except Exception:
                pass
            raise

        except Exception as e:
            try:
                clear_cookies_file(self._username)
            except Exception:
                pass
            raise BrowserAuthError(
                f"Error inesperado en login: {e}",
                username=self._username,
            ) from e
