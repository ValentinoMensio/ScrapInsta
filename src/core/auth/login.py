import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from core.utils.undetected import random_sleep
from exceptions.business_exceptions import InstagramLoginError
import time

logger = logging.getLogger(__name__)

def login_instagram(driver, account):
    """
    Realiza login en Instagram con manejo robusto de errores
    """
    try:
        logger.info(f"Iniciando login para {account['username']}")
        driver.get("https://www.instagram.com/accounts/login/")
        random_sleep(1.0, 2.0)

        # Esperar a que aparezcan los campos de login
        wait = WebDriverWait(driver, 20)
        username_field = wait.until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        password_field = driver.find_element(By.NAME, "password")

        # Limpiar campos antes de escribir
        username_field.clear()
        password_field.clear()
        
        username_field.send_keys(account['username'])
        password_field.send_keys(account['password'])

        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()

        # Esperar a que se complete el login
        time.sleep(5)
        random_sleep(2.0, 3.0)
        
        logger.info(f"Login exitoso para {account['username']}")
        return driver
        
    except TimeoutException:
        error_msg = f"Timeout esperando elementos de login para {account['username']}"
        logger.error(error_msg)
        raise InstagramLoginError(error_msg, account['username'], "timeout")
        
    except NoSuchElementException:
        error_msg = f"No se encontraron elementos de login para {account['username']}"
        logger.error(error_msg)
        raise InstagramLoginError(error_msg, account['username'], "element_not_found")
        
    except Exception as e:
        error_msg = f"Error inesperado en login para {account['username']}: {str(e)}"
        logger.error(error_msg)
        raise InstagramLoginError(error_msg, account['username'], "unexpected_error")