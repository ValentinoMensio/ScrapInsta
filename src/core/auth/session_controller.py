import logging
from datetime import datetime
from config.settings import INSTAGRAM_CONFIG
from core.utils.undetected import random_sleep
from core.auth.cookie_manager import load_cookies, save_cookies
from core.auth.login import login_instagram
from core.utils.selenium_helpers import is_logged_in, handle_save_login_info_popup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

def should_refresh_cookies(last_cookie_check):
    if last_cookie_check is None:
        return True
    return (datetime.now() - last_cookie_check).total_seconds() > INSTAGRAM_CONFIG['cookie_refresh_interval'] * 60


def initialize_session(driver, account, last_cookie_check):
    if not account or 'username' not in account:
        logger.error("No se proporcionó una cuenta: omitiendo inicio de sesión")
        return True, last_cookie_check

    logger.info("Iniciando sesión en Instagram...")

    # Primero intentamos cargar cookies válidas, sin hacer driver.get aún
    if should_refresh_cookies(last_cookie_check):
        try:
            cookies_loaded = load_cookies(driver, account['username'])
            if cookies_loaded:
                driver.get("https://www.instagram.com/")
                random_sleep(1.0, 2.0)

                if is_logged_in(driver):
                    logger.info("Sesión verificada con cookies")
                    return True, datetime.now()
        except Exception as e:
            logger.error(f"Error cargando cookies: {e}")

    # Si las cookies no funcionan o no hay, hacemos login manual
    try:
        logger.info("Intentando login manual...")
        driver.get("https://www.instagram.com/accounts/login/")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )

        driver = login_instagram(driver, account)
        handle_save_login_info_popup(driver)

        if is_logged_in(driver):
            logger.info("Login manual exitoso")
            try:
                save_cookies(driver, account['username'])
            except Exception as e:
                logger.error(f"Error guardando cookies: {e}")
            return True, datetime.now()

        raise Exception("No se pudo verificar el estado de login")

    except Exception as e:
        logger.error(f"Error en inicialización de sesión: {e}")
        return False, last_cookie_check
