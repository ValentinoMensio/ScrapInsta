from __future__ import annotations

import logging
from typing import Optional

from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys

from scrapinsta.crosscutting.human.tempo import HumanScheduler, sleep_jitter
from scrapinsta.crosscutting.human.human_actions import human_scroll
from scrapinsta.domain.ports.message_port import (
    MessageSenderPort,
    DMTransientUIBlock,
    DMInputTimeout,
    DMUnexpectedError,
)
from scrapinsta.application.dto.messages import MessageRequest

from scrapinsta.infrastructure.browser.pages import profile_page
from scrapinsta.crosscutting.logging_config import get_logger

logger = get_logger("selenium_message_sender")


class SeleniumMessageSender(MessageSenderPort):
    """
    Adapter de envío de DM con Selenium.
    - PRIORIDAD: usa los métodos del programa original si existen en `profile_page`.
    - FALLBACK: si algún método no existe, usa XPATHs razonables.
    - Retries se manejan en el use case.
    """

    # ---------- Fallback selectors (solo si no existen métodos en profile_page) ----------
    _BTN_MESSAGE_XPATHS = (
        "//div[normalize-space()='Message']",
        "//button[.//div[normalize-space()='Message']]",
        "//button[normalize-space()='Message']",
        "//div[@role='button' and normalize-space()='Message']",
        "//span[normalize-space()='Message']/ancestor::button",
    )
    _TEXTAREA_XPATHS = (
        "//textarea[@aria-label='Message' or @placeholder='Message…' or @placeholder='Message...']",
        "//div[@role='textbox']",
        "//div[contains(@contenteditable,'true')]",
    )
    _SEND_BUTTON_XPATHS = (
        "//div[@role='button' and normalize-space()='Send']",
        "//button[normalize-space()='Send']",
        "//button[@aria-label='Send' or @aria-label='Enviar']",
    )

    def __init__(
        self,
        driver,
        *,
        scheduler: Optional[HumanScheduler] = None,
        base_url: str = "https://www.instagram.com",
        wait_timeout: float = 10.0,
        small_pause: float = 0.35,
        small_jitter: float = 0.4,
    ) -> None:
        self.driver = driver
        self._sched = scheduler or HumanScheduler()
        self._base_url = base_url.rstrip("/")
        self._wait_timeout = float(wait_timeout)
        self._small_pause = float(small_pause)
        self._small_jitter = float(small_jitter)

    # =====================================================================================
    # API pública (ambas firmas para compatibilidad)
    # =====================================================================================

    def send_message(self, req: MessageRequest, text: str) -> bool:
        """Firma usada por el use case nuevo."""
        username = (req.target_username or "").strip().lstrip("@")
        return self.send_direct_message(username, text)

    def send_direct_message(self, username: str, text: str) -> bool:
        """Firma histórica/minimalista (versión vieja)."""
        uname = (username or "").strip().lstrip("@")
        if not uname:
            raise DMUnexpectedError("username vacío")

        try:
            self._sched.wait_turn()
            logger.info("dm_step", step="open_profile", username=uname)
            self._open_profile(uname)
            logger.info("dm_step_done", step="open_profile", username=uname)
            self._sleep_short()
            try:
                human_scroll(self.driver, total_px=600, duration=0.9, scheduler=self._sched)
            except Exception:
                pass

            self._sched.wait_turn()
            logger.info("dm_step", step="open_message_dialog", username=uname)
            self._open_message_dialog()
            logger.info("dm_step_done", step="open_message_dialog", username=uname)
            self._sleep_short()

            self._sched.wait_turn()
            logger.info("dm_step", step="type_message", username=uname, text_length=len(text))
            self._type_message(text)
            logger.info("dm_step_done", step="type_message", username=uname)
            self._sleep_short()

            self._sched.wait_turn()
            logger.info("dm_step", step="send_action", username=uname)
            self._send_action()
            logger.info("dm_step_done", step="send_action", username=uname)
            self._sleep_short()

            return True

        except ElementClickInterceptedException as e:
            logger.warning("dm_step_error", step="click", error=str(e), error_type="ElementClickInterceptedException")
            raise DMTransientUIBlock(f"overlay intercept: {e}") from e
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
            logger.warning("dm_step_error", step="element_not_found", error=str(e), error_type=type(e).__name__)
            raise DMInputTimeout(f"input timeout: {e}") from e
        except WebDriverException as e:
            msg = (str(e) or "").lower()
            if "temporarily blocked" in msg or "try again later" in msg:
                raise DMTransientUIBlock("temporarily blocked by Instagram") from e
            raise DMUnexpectedError(str(e)) from e
        except DMUnexpectedError:
            raise
        except Exception as e:
            raise DMUnexpectedError(f"unexpected send error: {e}") from e

    # =====================================================================================
    # Internals — priorizan métodos del programa original; si no existen, caen a XPATHs
    # =====================================================================================

    def _open_profile(self, username: str) -> None:
        """Prioriza: profile_page.open_profile(driver, username). Fallback: GET + cerrar popup."""
        try:
            open_profile_fn = getattr(profile_page, "open_profile", None)
            if callable(open_profile_fn):
                open_profile_fn(self.driver, username)
            else:
                url = f"{self._base_url}/{username}/"
                self._get(url)
        finally:
            try:
                close_popup = getattr(profile_page, "close_instagram_login_popup", None)
                if callable(close_popup):
                    close_popup(self.driver, timeout=5)
            except Exception:
                pass

    def _open_message_dialog(self) -> None:
        """Prioriza: profile_page.open_message_dialog(driver). Fallback: botón 'Message'."""
        open_dm = getattr(profile_page, "open_message_dialog", None)
        if callable(open_dm):
            open_dm(self.driver)
            return

        btn = self._wait_any_xpath(self._BTN_MESSAGE_XPATHS)
        try:
            btn.click()
        except ElementClickInterceptedException:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            sleep_jitter(self._small_pause, self._small_jitter)
            btn.click()

    def _type_message(self, text: str) -> None:
        """Prioriza: profile_page.type_message(driver, text). Fallback: textarea/contenteditable."""
        type_fn = getattr(profile_page, "type_message", None)
        if callable(type_fn):
            type_fn(self.driver, text)
            return

        ta = self._wait_any_xpath(self._TEXTAREA_XPATHS)
        ta.click()
        sleep_jitter(self._small_pause, self._small_jitter)
        ta.send_keys(text)
        self._sleep_after_typing(text)

    def _send_action(self) -> None:
        """Prioriza: profile_page.send_message(driver). Fallback: botón 'Send' o ENTER."""
        send_fn = getattr(profile_page, "send_message", None)
        if callable(send_fn):
            send_fn(self.driver)
            return

        try:
            send_btn = WebDriverWait(self.driver, 1.8).until(
                EC.element_to_be_clickable((By.XPATH, self._SEND_BUTTON_XPATHS[0]))
            )
            send_btn.click()
            return
        except Exception:
            pass

        ta = self._wait_any_xpath(self._TEXTAREA_XPATHS, timeout=2.0)
        ta.send_keys(Keys.ENTER)

    # =====================================================================================
    # Utilidades comunes
    # =====================================================================================

    def _get(self, url: str) -> None:
        try:
            logger.debug("[dm] GET %s", url)
            self.driver.get(url)
        except (TimeoutException, WebDriverException) as e:
            raise DMInputTimeout(f"navigation failed: {e}") from e

    def _wait_any_xpath(self, xpaths: tuple[str, ...], *, timeout: Optional[float] = None):
        _timeout = timeout or self._wait_timeout
        last_exc = None
        for i, xp in enumerate(xpaths):
            try:
                el = WebDriverWait(self.driver, _timeout).until(
                    EC.presence_of_element_located((By.XPATH, xp))
                )
                logger.debug("dm_selector_ok", xpath_index=i, xpath_preview=xp[:80])
                return el
            except Exception as e:
                last_exc = e
                logger.debug("dm_selector_fail", xpath_index=i, xpath_preview=xp[:80], error=str(e))
                continue
        logger.warning("dm_all_selectors_failed", xpath_count=len(xpaths), last_error=str(last_exc))
        raise DMInputTimeout(f"element not found for any xpath: {xpaths}") from last_exc

    def _sleep_short(self) -> None:
        sleep_jitter(self._small_pause, self._small_jitter)

    def _sleep_after_typing(self, text: str) -> None:
        length = max(1, len(text))
        base = min(0.8 + (length * 0.02), 4.5)
        sleep_jitter(base, 0.4)
