from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import MoveTargetOutOfBoundsException
import random
import time
import logging

logger = logging.getLogger(__name__)

def random_sleep(min_seconds=1, max_seconds=3):
    time.sleep(random.uniform(min_seconds, max_seconds))

def random_mouse_movements(driver, num_movements=5):
    """
    Simula movimientos aleatorios del mouse sobre la página.
    Solo si el elemento bajo el cursor tiene tamaño visible.
    """
    actions = ActionChains(driver)
    width = driver.execute_script("return window.innerWidth")
    height = driver.execute_script("return window.innerHeight")

    for _ in range(num_movements):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)

        try:
            element = driver.execute_script("return document.elementFromPoint(arguments[0], arguments[1]);", x, y)

            if element is None:
                continue

            # Obtener dimensiones
            rect = driver.execute_script("""
                var el = arguments[0];
                var rect = el.getBoundingClientRect();
                return { width: rect.width, height: rect.height };
            """, element)

            if not rect or rect["width"] == 0 or rect["height"] == 0:
                continue

            # Mover si tiene tamaño
            actions.move_to_element_with_offset(element, 1, 1).perform()
            random_sleep(0.2, 0.6)

        except MoveTargetOutOfBoundsException:
            logger.warning("Elemento fuera del área visible")
            continue
        except Exception as e:
            logger.error(f"Error al mover el mouse: {e}")
            continue
