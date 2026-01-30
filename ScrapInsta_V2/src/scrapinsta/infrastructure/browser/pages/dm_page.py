from __future__ import annotations

from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from scrapinsta.crosscutting.human.tempo import sleep_jitter
from scrapinsta.crosscutting.logging_config import get_logger

logger = get_logger("dm_page")

_BTN_MESSAGE_XPATHS = (
    "//button//div[normalize-space()='Message']",
    "//div[@role='button' and normalize-space()='Message']",
    "//span[normalize-space()='Message']/ancestor::button",
)
_TEXTAREA_XPATHS = (
    "//textarea[@aria-label='Message' or @placeholder='Message…' or @placeholder='Message...']",
    "//div[@role='textbox']",
    "//div[contains(@contenteditable,'true')]",
)
_BTN_SEND_XPATHS = (
    "//div[@role='button' and normalize-space()='Send']",
    "//button[normalize-space()='Send']",
    "//button[@aria-label='Send' or @aria-label='Enviar']",
)


def open_profile(driver: WebDriver, username: str, base_url: str = "https://www.instagram.com") -> None:
    """Abre el perfil (sin reintentos; sin cerrar popups)."""
    url = f"{base_url.rstrip('/')}/{username.strip().lstrip('@')}/"
    logger.info("dm_page_step", step="open_profile", username=username, url=url)
    driver.get(url)
    logger.info("dm_page_step_done", step="open_profile", username=username)


def open_message_dialog(driver: WebDriver, timeout: float = 10.0) -> None:
    """Clic en el botón 'Message' del perfil."""
    logger.info("dm_page_step", step="open_message_dialog", timeout=timeout)
    for i, xp in enumerate(_BTN_MESSAGE_XPATHS):
        try:
            btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click()
            sleep_jitter(0.3, 0.2)
            logger.info("dm_page_step_done", step="open_message_dialog", selector_index=i)
            return
        except TimeoutException:
            logger.debug("dm_page_selector_fail", step="Message", selector_index=i, xpath_preview=xp[:60])
            continue
        except Exception as e:
            logger.debug("dm_page_selector_error", step="Message", selector_index=i, error=str(e))
            continue
    logger.warning("dm_page_step_failed", step="open_message_dialog", message="no se encontró el botón Message")
    raise TimeoutException("no se encontró el botón 'Message'")


def type_message(driver: WebDriver, text: str, timeout: float = 10.0) -> None:
    """Escribe el texto en el área de mensaje."""
    logger.info("dm_page_step", step="type_message", text_length=len(text))
    for i, xp in enumerate(_TEXTAREA_XPATHS):
        try:
            area = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xp)))
            area.click()
            sleep_jitter(0.25, 0.2)
            area.send_keys(text)
            length = max(1, len(text))
            base = min(0.8 + (length * 0.02), 4.5)
            sleep_jitter(base, 0.4)
            logger.info("dm_page_step_done", step="type_message", selector_index=i)
            return
        except TimeoutException:
            logger.debug("dm_page_selector_fail", step="textarea", selector_index=i, xpath_preview=xp[:60])
            continue
        except Exception as e:
            logger.debug("dm_page_selector_error", step="textarea", selector_index=i, error=str(e))
            continue
    logger.warning("dm_page_step_failed", step="type_message", message="no se encontró el textarea")
    raise TimeoutException("no se encontró el textarea del mensaje")


def send_message(driver: WebDriver, timeout: float = 5.0) -> None:
    """Envía el mensaje con botón 'Send' o ENTER como fallback."""
    logger.info("dm_page_step", step="send_message", timeout=timeout)
    for i, xp in enumerate(_BTN_SEND_XPATHS):
        try:
            btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click()
            sleep_jitter(0.25, 0.15)
            logger.info("dm_page_step_done", step="send_message", selector_index=i)
            return
        except TimeoutException:
            logger.debug("dm_page_selector_fail", step="Send", selector_index=i, xpath_preview=xp[:60])
            continue
        except Exception as e:
            logger.debug("dm_page_selector_error", step="Send", selector_index=i, error=str(e))
            continue

    # Fallback ENTER
    logger.info("dm_page_step", step="send_message_fallback_enter")
    try:
        area = WebDriverWait(driver, 2.0).until(EC.presence_of_element_located((By.XPATH, _TEXTAREA_XPATHS[0])))
        area.send_keys(Keys.ENTER)
        logger.info("dm_page_step_done", step="send_message_fallback_enter")
    except Exception as e:
        logger.warning("dm_page_step_failed", step="send_message", message="fallback ENTER falló", error=str(e))
        raise WebDriverException(f"fallback ENTER falló: {e}") from e
