from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException

def is_profile_private(driver, timeout: int = 5) -> bool:
    try:
        # Buscar elementos de texto que indiquen perfil privado
        spans = driver.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
        for span in spans:
            try:
                text = span.text.lower()
                if "esta cuenta es privada" in text or "síguela para ver" in text:
                    return True
            except StaleElementReferenceException:
                # Si el elemento se volvió stale, continuar con el siguiente
                continue
            except Exception:
                # Otros errores, continuar
                continue
        return False
    except Exception:
        return False

def is_profile_verified(driver) -> bool:
    try:
        driver.find_element(By.CSS_SELECTOR, "svg[aria-label='Verificado']")
        return True
    except NoSuchElementException:
        return False

def has_reels(driver) -> bool:
    try:
        # Buscar elementos de reels directamente sin wait
        reel_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/reel/']")
        return len(reel_elements) > 0
    except Exception:
        return False

def close_instagram_login_popup(driver, timeout=5):
    try:
        close_button = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@role='dialog']//div[@role='button' or @tabindex='0']//*[name()='svg' or name()='path']/ancestor::div[@role='button' or @tabindex='0']"
            ))
        )
        close_button.click()
        return True
    except (NoSuchElementException, ElementClickInterceptedException):
        return False
    except Exception:
        return False
