import os
import time
import logging
import socket
from pathlib import Path
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire.undetected_chromedriver.v2 import Chrome as ChromeWire, ChromeOptions
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from config.settings import (
    BROWSER_CONFIG,
    RETRY_CONFIG,
    PORT_CONFIG,
)
from core.utils.undetected import random_sleep
from core.utils.humanize_helpers import choose_and_apply_user_agent  # <-- NUEVO

logger = logging.getLogger(__name__)

class DriverManager:
    def __init__(self, account, proxy_auth=None):
        self.account = account
        self.driver = None
        self.profile_dir = None
        self.proxy_auth = proxy_auth
        self.seleniumwire_options = {}

    def initialize_driver(self):
        for attempt in range(RETRY_CONFIG['max_retries']):
            try:

                username = self.account.get('username', f'worker_{os.getpid()}')

                options = self._get_chrome_options(username)
                self.profile_dir = Path(f"./data/profiles/{username}")
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                options.add_argument(f"--user-data-dir={self.profile_dir}")

                port = self.find_available_port()
                if not port:
                    raise Exception("No se pudo encontrar un puerto libre")
                options.add_argument(f"--remote-debugging-port={port}")

                caps = DesiredCapabilities.CHROME.copy()
                caps["pageLoadStrategy"] = "eager"

                kwargs = dict(
                    options=options,
                    seleniumwire_options=self.seleniumwire_options,
                    use_subprocess=False,
                    port=port,
                    desired_capabilities=caps
                )
                vm = BROWSER_CONFIG.get('chrome_version')
                if vm:  # solo si está seteado
                    kwargs['version_main'] = vm

                driver = ChromeWire(**kwargs)
                
                if self.proxy_auth:
                    try:
                        driver.execute_cdp_cmd("Network.enable", {})
                        driver.execute_cdp_cmd(
                            "Network.setExtraHTTPHeaders",
                            {"headers": {"Authorization": self.proxy_auth}}
                        )
                        logger.info("Cabeceras de autenticación aplicadas vía CDP")
                    except Exception as e:
                        logger.warning(f"Error aplicando auth con CDP: {e}")

                # Verificación de IP pública
                test_url = "https://api.ipify.org"
                logger.info(f"Abriendo {test_url} para verificar IP pública...")
                driver.get(test_url)
                WebDriverWait(driver, 10).until(lambda d: d.find_element(By.TAG_NAME, "body"))
                ip = driver.find_element(By.TAG_NAME, "body").text.strip()
                logger.info(f"IP pública detectada por Selenium: {ip}")

                # Evasión básica
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                stealth(driver,
                        languages=["es-AR", "es"],
                        vendor="Google Inc.",
                        platform="Win32",
                        webgl_vendor="Intel Inc.",
                        renderer="Intel Iris OpenGL Engine",
                        fix_hairline=True)

                # Timeouts
                driver.set_page_load_timeout(BROWSER_CONFIG['timeouts']['page_load'])
                driver.set_script_timeout(BROWSER_CONFIG['timeouts']['script'])
                driver.implicitly_wait(2)

                # Inicialización en blanco
                driver.get("about:blank")
                WebDriverWait(driver, BROWSER_CONFIG['timeouts']['explicit']).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )

                random_sleep(2.0, 5.0)
                self.driver = driver
                return driver

            except Exception as e:
                logger.error(f"[DriverManager] Error al inicializar el driver: {e}")
                self.cleanup()
                if attempt < RETRY_CONFIG['max_retries'] - 1:
                    wait = RETRY_CONFIG['initial_delay'] * (attempt + 1)
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

    def find_available_port(self):
        for _ in range(PORT_CONFIG['max_port_attempts']):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                return s.getsockname()[1]
        return None

    def _get_chrome_options(self, username: str):  # <-- recibe username
        options = ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--window-size=1280,800")
        options.add_argument("blink-settings=imagesEnabled=false")
        options.headless = False

        ua = choose_and_apply_user_agent(options, BROWSER_CONFIG, stable_key=username)
        logger.info(f"User-Agent configurado: {ua}")

        proxy = self.account.get('proxy')
        if proxy:
            if '@' in proxy:  # tiene user:pass
                credentials, address = proxy.split('@', 1)
                proxy_user, proxy_pass = credentials.split(':', 1)
                proxy_host, proxy_port = address.split(':', 1)
                self.seleniumwire_options = {
                    'proxy': {
                        'http': f'http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}',
                        'https': f'https://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}',
                        'no_proxy': 'localhost,127.0.0.1'
                    },
                    'disable_capture': True
                }
                logger.info("Proxy configurado: %s:%s (user=***, pass=***)", proxy_host, proxy_port)
            else:
                self.seleniumwire_options = {
                    'proxy': {
                        'http': f'http://{proxy}',
                        'https': f'https://{proxy}',
                        'no_proxy': 'localhost,127.0.0.1'
                    },
                    'disable_capture': True
                }
                logger.info(f"Proxy sin autenticación configurado: {proxy}")

        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "intl.accept_languages": "es-AR,es",
            # WebRTC: evitar fugas IP fuera del proxy
            "webrtc.ip_handling_policy": "disable_non_proxied_udp",
            "webrtc.multiple_routes_enabled": False,
            "webrtc.nonproxied_udp_enabled": False
        }
        options.add_experimental_option("prefs", prefs)

        return options
