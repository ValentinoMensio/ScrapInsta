import logging
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from core.utils.undetected import random_sleep

logger = logging.getLogger(__name__)

def handle_save_login_info_popup(driver):
    """Maneja el popup de 'Guardar información de inicio de sesión'."""
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        random_sleep(1.0, 2.0)
        
        try:
            popup = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog']"))
            )
            buttons = popup.find_elements(By.CSS_SELECTOR, "div[role='button'], button")
            
            if len(buttons) >= 2:
                buttons[1].click()
                logger.info("Popup de 'Guardar información' - Clic en 'Ahora no'")
                random_sleep(1.0, 2.0)
                
        except Exception as e:
            logger.debug("No se encontró popup de 'Guardar información' o no se pudo interactuar")
            
    except Exception as e:
        logger.warning(f"Error al manejar popup de inicio de sesión: {str(e)}")

def is_logged_in(driver):
    """Verifica si el usuario está logueado en Instagram."""
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        current_url = driver.current_url
        if "accounts/login" in current_url:
            logger.debug("URL contiene 'accounts/login' - Usuario no logueado")
            return False
            
        if "instagram.com" in current_url and not any(x in current_url for x in ["login", "signup"]):
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                        "svg[aria-label='Nueva publicación'], "
                        "svg[aria-label='New post'], "
                        "a[href*='/accounts/edit/'], "
                        "a[href*='/direct/inbox/']"))
                )
                logger.debug("Elementos de sesión activa encontrados - Usuario logueado")
                return True
            except Exception as e:
                logger.debug("No se encontraron elementos de sesión activa")
                return False
                
        return False
        
    except Exception as e:
        logger.error(f"Error al verificar estado de login: {str(e)}")
        return False

def kill_chrome_processes():
    """Finaliza todos los procesos de Chrome/Chromedriver asociados."""
    try:
        main_pid = os.getpid()
        
        # Primer intento de cierre normal
        os.system(f"pkill -f 'chrome.*_{main_pid}'")
        os.system(f"pkill -f 'chromedriver.*_{main_pid}'")
        random_sleep(1.0, 2.0)
        
        # Verificación de procesos residuales
        chrome_processes = os.popen(f"ps aux | grep -i 'chrome.*_{main_pid}' | grep -v grep").read()
        chromedriver_processes = os.popen(f"ps aux | grep -i 'chromedriver.*_{main_pid}' | grep -v grep").read()
        
        if chrome_processes or chromedriver_processes:
            logger.warning("Algunos procesos de Chrome no se cerraron correctamente")
            logger.debug(f"Procesos de Chrome restantes:\n{chrome_processes}")
            logger.debug(f"Procesos de Chromedriver restantes:\n{chromedriver_processes}")
            
            # Intento forzoso de cierre
            os.system(f"pkill -9 -f 'chrome.*_{main_pid}'")
            os.system(f"pkill -9 -f 'chromedriver.*_{main_pid}'")
            random_sleep(1.0, 2.0)
            
    except Exception as e:
        logger.error(f"Error crítico al cerrar procesos de Chrome: {str(e)}")
        raise