from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from selenium_stealth import stealth
from seleniumwire.undetected_chromedriver.v2 import Chrome as ChromeWire

from scrapinsta.config.settings import Settings
from scrapinsta.crosscutting.logging_config import get_logger

from .browser_utils import detect_chrome_major, quick_probe, safe_quit, safe_username
from .driver_factory import build_chrome_options

log = get_logger("driver_provider")


class DriverManagerError(RuntimeError):
    """Errores de inicialización/gestión del driver."""


class DriverProvider:
    """
    Administra el ciclo de vida de un Chrome *local* con undetected_chromedriver v2 (ChromeWire)
    en todos los entornos (local y Docker). No usa Selenium remoto.
    """

    def __init__(
        self,
        *,
        account_username: str,
        proxy: Optional[str] = None,   # "user:pass@host:port"
        page_load_timeout: float = 90.0,
        script_timeout: float = 30.0,
        headless: Optional[bool] = None,
        chrome_version_main: Optional[int] = None,
        user_agent: Optional[str] = None,
        disable_images: bool = True,
        extra_flags: Optional[list[str]] = None,
        retry_attempts: int = 3,
        retry_initial_delay: float = 4.0,
        settings: Optional[Settings] = None,
    ) -> None:
        username = (account_username or "").strip()
        if not username:
            raise ValueError("account_username requerido")
        self.username = username

        self.proxy_str = proxy
        self.page_load_timeout = float(page_load_timeout)
        self.script_timeout = float(script_timeout)

        # HEADLESS: por env HEADLESS=true/false o parámetro; default True en Docker, False en local
        if headless is None:
            env_val = os.getenv("HEADLESS", "").lower()
            if env_val in ("true", "1", "yes"):
                self.headless = True
            elif env_val in ("false", "0", "no"):
                self.headless = False
            else:
                self.headless = bool(os.getenv("CI") or os.path.exists("/.dockerenv"))
        else:
            self.headless = bool(headless)

        self.chrome_version_main = chrome_version_main or detect_chrome_major()
        self.user_agent = user_agent
        self.disable_images = bool(disable_images)
        self.extra_flags = extra_flags or []
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_initial_delay = max(0.1, float(retry_initial_delay))
        self.settings = settings or Settings()

        self.driver = None
        self._seleniumwire_options: Dict[str, Any] = {}

        # Directorio raíz para perfiles (centralizado)
        self.profile_root: Path = self.settings.profiles_path

    # ------------------------------------------------------------------ public

    def initialize_driver(self):
        """Inicializa y retorna un Chrome (UC v2) con selenium-wire; reintenta ante fallos."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                options, sw_options = build_chrome_options(
                    headless=self.headless,
                    disable_images=self.disable_images,
                    extra_flags=self.extra_flags,
                    user_agent=self.user_agent,
                    proxy_str=self.proxy_str,
                )
                self._seleniumwire_options = sw_options

                # Perfil persistente único por usuario
                profile_dir = self.profile_root / safe_username(self.username)
                profile_dir.mkdir(parents=True, exist_ok=True)
                options.add_argument(f"--user-data-dir={profile_dir.as_posix()}")

                driver_args: Dict[str, Any] = {
                    "options": options,
                    "seleniumwire_options": self._seleniumwire_options,
                    "use_subprocess": True,
                }
                if self.chrome_version_main:
                    driver_args["version_main"] = int(self.chrome_version_main)
                    log.info("driver_version_main", version_main=int(self.chrome_version_main))

                driver = ChromeWire(**driver_args)

                # Timeouts & waits
                driver.set_page_load_timeout(self.page_load_timeout)
                driver.set_script_timeout(self.script_timeout)
                driver.implicitly_wait(0)

                # Stealth (best-effort)
                try:
                    stealth(
                        driver,
                        languages=["es-AR", "es"],
                        vendor="Google Inc.",
                        platform="Win32",
                        webgl_vendor="Intel Inc.",
                        renderer="Intel Iris OpenGL Engine",
                        fix_hairline=True,
                    )
                except Exception:
                    log.debug("selenium_stealth_apply_failed", account=self.username)

                # Warm-up opcional (best-effort)
                quick_probe(driver)

                self.driver = driver
                log.info("driver_initialized", account=self.username, mode="uc_local")
                return self.driver

            except Exception as e:
                last_error = e
                log.error(
                    "driver_init_failed",
                    account=self.username,
                    attempt=attempt,
                    max_attempts=self.retry_attempts,
                    error=str(e),
                )
                safe_quit(self.driver)
                self.driver = None
                if attempt < self.retry_attempts:
                    time.sleep(self.retry_initial_delay * attempt)

        raise DriverManagerError(
            f"No se pudo inicializar el driver tras {self.retry_attempts} intentos: {last_error}"
        )

    def cleanup(self) -> None:
        """Cierra el driver si está vivo (idempotente)."""
        safe_quit(self.driver)
        self.driver = None
