from __future__ import annotations

import logging
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from scrapinsta.crosscutting.human.tempo import sleep_jitter

logger = logging.getLogger(__name__)

# Selectores con fallbacks razonables (2025-10)
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
    logger.debug("[dm_page] GET %s", url)
    driver.get(url)


def open_message_dialog(driver: WebDriver, timeout: float = 10.0) -> None:
    """Clic en el botón 'Message' del perfil."""
    for xp in _BTN_MESSAGE_XPATHS:
        try:
            btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click()
            sleep_jitter(0.3, 0.2)
            return
        except TimeoutException:
            continue
        except Exception as e:
            logger.debug("[dm_page] fallo selector Message %s: %s", xp, e)
            continue
    raise TimeoutException("no se encontró el botón 'Message'")


def type_message(driver: WebDriver, text: str, timeout: float = 10.0) -> None:
    """Escribe el texto en el área de mensaje."""
    for xp in _TEXTAREA_XPATHS:
        try:
            area = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xp)))
            area.click()
            sleep_jitter(0.25, 0.2)
            area.send_keys(text)
            return
        except TimeoutException:
            continue
        except Exception as e:
            logger.debug("[dm_page] error escribiendo mensaje con %s: %s", xp, e)
            continue
    raise TimeoutException("no se encontró el textarea del mensaje")


def send_message(driver: WebDriver, timeout: float = 5.0) -> None:
    """Envía el mensaje con botón 'Send' o ENTER como fallback."""
    for xp in _BTN_SEND_XPATHS:
        try:
            btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click()
            sleep_jitter(0.25, 0.15)
            return
        except TimeoutException:
            continue
        except Exception as e:
            logger.debug("[dm_page] botón Send falló con %s: %s", xp, e)
            continue

    # Fallback ENTER
    try:
        area = WebDriverWait(driver, 2.0).until(EC.presence_of_element_located((By.XPATH, _TEXTAREA_XPATHS[0])))
        area.send_keys(Keys.ENTER)
    except Exception as e:
        raise WebDriverException(f"fallback ENTER falló: {e}") from e
