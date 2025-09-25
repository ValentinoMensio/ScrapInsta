# src/core/browser/driver_manager.py
import os
import time
import json
import logging
from pathlib import Path
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire.undetected_chromedriver.v2 import Chrome as ChromeWire, ChromeOptions
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from core.utils.humanize_helpers import choose_and_apply_user_agent

from config.settings import BROWSER_CONFIG, RETRY_CONFIG

logger = logging.getLogger(__name__)

class DriverManager:
    def __init__(self, account: dict):
        """
        account must contain:
          - 'username': str
          - 'proxy': 'user:pass@host:port'
        """
        self.account = account
        self.driver = None
        self.profile_dir = None
        self.seleniumwire_options = {}

    def initialize_driver(self):
        """Inicializa Chrome + selenium-wire con proxy; retorna driver o None."""
        for attempt in range(RETRY_CONFIG.get('max_retries', 3)):
            try:
                username = self.account.get('username', f'worker_{os.getpid()}')
                options = self._get_chrome_options(username)

                # profile dir (persist cookies/session)
                unique = f"{username}_{os.getpid()}"
                self.profile_dir = Path(f"./data/profiles/{unique}")
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                options.add_argument(f"--user-data-dir={self.profile_dir.as_posix()}")

                # capabilities
                caps = DesiredCapabilities.CHROME.copy()
                caps["pageLoadStrategy"] = "eager"

                driver_args = dict(
                    options=options,
                    seleniumwire_options=self.seleniumwire_options,
                    use_subprocess=True,
                    desired_capabilities=caps,
                )

                vm = BROWSER_CONFIG.get("chrome_version")
                if vm:
                    driver_args["version_main"] = vm
                    logger.info(f"[DriverManager] Forzando undetected_chromedriver version_main={vm}")

                driver = ChromeWire(**driver_args)


                # Timeouts agresivos y sin implicit waits
                driver.set_page_load_timeout(BROWSER_CONFIG['timeouts']['page_load'])
                driver.set_script_timeout(BROWSER_CONFIG['timeouts']['script'])
                driver.implicitly_wait(0)   # usar solo explicit waits

                # Quick warm-up & proxy probe (no bloqueante)
                probe = self._probe_proxy(driver, timeout=8)
                logger.info(f"[{username}] Proxy probe: {probe}")

                # Si probe devolvió ip y es plausible, continuar.
                self.driver = driver
                stealth(
                    driver,
                    languages=["es-AR", "es"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True
                )


                return driver

            except Exception as e:
                logger.exception(f"[DriverManager] Error al inicializar el driver (attempt {attempt+1}): {e}")
                try:
                    if self.driver:
                        self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                if attempt < RETRY_CONFIG.get('max_retries', 3) - 1:
                    wait = RETRY_CONFIG.get('initial_delay', 5) * (attempt + 1)
                    logger.info(f"Reintentando en {wait:.1f} segundos...")
                    time.sleep(wait)
        return None

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"[DriverManager] Error cerrando driver: {e}")
            finally:
                self.driver = None

    def _parse_proxy(self, proxy_str: str):
        """
        parsea 'user:pass@host:port' -> (user, pass, host, port) o raise ValueError
        """
        if not proxy_str or '@' not in proxy_str:
            raise ValueError("Proxy inválido, requiere formato user:pass@host:port")
        credentials, address = proxy_str.split('@', 1)
        if ':' not in credentials or ':' not in address:
            raise ValueError("Proxy inválido, formato user:pass@host:port")
        user, password = credentials.split(':', 1)
        host, port = address.split(':', 1)
        return user, password, host, port

    def _get_chrome_options(self, username: str):
        options = ChromeOptions()

        # Flags de rendimiento + evitar ruido
        flags = [
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
            "--disable-software-rasterizer", "--disable-extensions",
            "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows", "--metrics-recording-only",
            "--no-first-run", "--no-default-browser-check",
            "--disable-features=TranslateUI,AutomationControlled",
            "--ignore-certificate-errors",
            "--window-size=1200,800",
            #no cargar imagenes
            "--blink-settings=imagesEnabled=false",
            
        ]
        for f in flags:
            options.add_argument(f)

        # UA: deja que tu helper elija un UA creíble (usa stable_key para consistencia)
        try:
            ua = choose_and_apply_user_agent(options, BROWSER_CONFIG, stable_key=username)
            logger.info(f"[{username}] User-Agent configurado: {ua}")
        except Exception:
            logger.exception("Error aplicando user-agent")

        # Proxy: solo user:pass@host:port
        proxy = self.account.get('proxy')
        if not proxy:
            raise ValueError("No hay proxy configurado para la cuenta")

        p_user, p_pass, p_host, p_port = self._parse_proxy(proxy)
        # Selenium-wire options optimizadas para reducir overhead
        self.seleniumwire_options = {
            'proxy': {
                'http':  f'http://{p_user}:{p_pass}@{p_host}:{p_port}',
                'https': f'https://{p_user}:{p_pass}@{p_host}:{p_port}',
                'no_proxy': 'localhost,127.0.0.1'
            },
            'disable_capture': True,
            'mitm_http2': False,
            'verify_ssl': True,              # si confías en proxy, True; si pruebas, False acelera
            'connection_timeout': 15,
            'suppress_connection_errors': True,
            # 'exclude_hosts': []  # no incluir api.ipify durante pruebas
        }
        logger.info(f"[{username}] Proxy configurado: {p_host}:{p_port} (user=***, pass=***)")

        # prefs: webRTC off, password manager off
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "intl.accept_languages": "es-AR,es",
            "webrtc.ip_handling_policy": "disable_non_proxied_udp",
            "webrtc.multiple_routes_enabled": False,
            "webrtc.nonproxied_udp_enabled": False
        }
        options.add_experimental_option("prefs", prefs)

        return options

    def _probe_proxy(self, driver, timeout=8):
        """
        Verifica rápidamente si el proxy está activo:
        - consulta https://api.ipify.org?format=json
        - inspecciona driver.requests recientes via selenium-wire
        Retorna dict con resultados.
        """
        result = {'ipify': None, 'httpbin_headers': None, 'requests_sample': []}
        try:
            driver.get("https://api.ipify.org?format=json")
            WebDriverWait(driver, timeout).until(lambda d: d.find_element(By.TAG_NAME, "body"))
            body = driver.find_element(By.TAG_NAME, "body").text
            j = json.loads(body)
            result['ipify'] = j.get('ip')
        except Exception as e:
            result['ipify_error'] = str(e)

        try:
            driver.get("https://httpbin.org/headers")
            WebDriverWait(driver, timeout).until(lambda d: d.find_element(By.TAG_NAME, "body"))
            body = driver.find_element(By.TAG_NAME, "body").text
            j = json.loads(body)
            result['httpbin_headers'] = j.get('headers', {})
        except Exception as e:
            result['httpbin_error'] = str(e)

        try:
            # últimas 10 requests
            for req in getattr(driver, 'requests', [])[-10:]:
                result['requests_sample'].append({
                    'url': req.url,
                    'method': req.method,
                    'status': (req.response.status_code if req.response else None),
                    'resp_headers': (dict(req.response.headers) if req.response and hasattr(req.response, 'headers') else {})
                })
        except Exception as e:
            result['requests_error'] = str(e)

        return result
