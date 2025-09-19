from selenium.webdriver.common.action_chains import ActionChains
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from core.utils.undetected import random_sleep
from core.utils.chatgpt import generate_custom_message
from db.connection import get_db_connection_context

logger = logging.getLogger(__name__)


def get_profile_from_db(username):
    """Obtiene perfil de la base de datos usando connection pooling"""
    try:
        with get_db_connection_context() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT username, rubro, followers, posts, avg_views, engagement_score, success_score
                FROM filtered_profiles
                WHERE username = %s
            """, (username,))
            profile = cursor.fetchone()
            cursor.close()
            logger.debug(f"Perfil obtenido de la DB: {profile}")
            return profile
    except Exception as e:
        logger.error(f"Error obteniendo perfil {username} de la base de datos: {e}")
        return None


def send_message(driver, username, max_retries=3):
    profile = get_profile_from_db(username)
    
    if not profile:
        logger.warning(f"Perfil '{username}' no encontrado en la base de datos")
        return False

    logger.info(f"Generando mensaje para: {username}")
    message = generate_custom_message(profile)
    logger.debug(f"Mensaje generado: {message}")

    for attempt in range(max_retries):
        try:
            logger.info(f"Intento {attempt + 1} de {max_retries} para enviar mensaje a {username}")

            # Go to user's Instagram page
            url = f"https://www.instagram.com/{username}/"
            driver.get(url)
            random_sleep(3.0, 5.0)

            # Versión mejorada para el botón de mensaje (funciona en inglés y español)
            message_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(., 'Message') or contains(., 'Mensaje')][@role='button']"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", message_button)
            driver.execute_script("arguments[0].click();", message_button)
            random_sleep(2.5, 3.5)

            # Versión más robusta para el campo de mensaje
            input_field = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='textbox'] | //p[contains(@class, 'xat24cr')]/span"))
            )
            
            # Limpiar y escribir el mensaje de forma más fiable
            driver.execute_script("arguments[0].innerHTML = '';", input_field)
            input_field.click()
            random_sleep(0.5, 1.0)
            
            # Alternativa 1: Usar ActionChains para simular mejor la escritura
            actions = ActionChains(driver)
            actions.send_keys(message)
            actions.perform()
            
            random_sleep(1.0, 1.5)

            # Versión mejorada para el botón de enviar
            send_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(., 'Send') or contains(., 'Enviar')][@role='button']"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", send_button)
            driver.execute_script("arguments[0].click();", send_button)

            logger.info(f"Mensaje enviado exitosamente a {username}")
            random_sleep(2.0, 3.0)  # Espera adicional después de enviar
            return True

        except Exception as e:
            logger.error(f"Error enviando mensaje a {username}: {str(e)}")
            driver.save_screenshot(f"error_{username}_attempt_{attempt+1}.png")
            random_sleep(5.0, 8.0)  # Espera más larga entre intentos
            continue

    logger.error(f"Falló el envío de mensaje a {username} después de {max_retries} intentos")
    return False