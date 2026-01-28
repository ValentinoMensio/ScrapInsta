from __future__ import annotations
import time, random
from typing import Callable, Optional, List, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

from scrapinsta.infrastructure.auth.cookie_store import save_cookies, clear_cookies_file
from scrapinsta.domain.ports.browser_port import BrowserAuthError
from scrapinsta.crosscutting.logging_config import get_logger

try:
    from scrapinsta.crosscutting.human.tempo import sleep_jitter as _hsleep, HumanScheduler
except Exception:
    class HumanScheduler:  # type: ignore[no-redef]
        def wait_turn(self) -> None:
            return None
    def _hsleep(a: float, b: float) -> None:
        time.sleep(max(0.0, (a + b) / 2.0))

log = get_logger("login_flow")


def _maybe_wait(scheduler: Optional[HumanScheduler]) -> None:
    if scheduler is None:
        return
    try:
        scheduler.wait_turn()
    except Exception:
        pass


# ---------------------------
# Utilidades de texto y UI
# ---------------------------
def _clean_text(s: str, max_len: int = 220) -> str:
    """Normaliza y trunca para logs compactos."""
    if not s:
        return ""
    compact = " ".join(s.split())
    return compact if len(compact) <= max_len else compact[: max_len - 1] + "…"


def _accept_cookies_banner(
    driver: WebDriver,
    *,
    scheduler: Optional[HumanScheduler] = None,
    timeout: int = 8,
) -> None:
    """Cierra banner de cookies si está (no loggea ruido)."""
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Allow all cookies']")),
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Aceptar']")),
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Allow essential and optional cookies']")),
            )
        )
        _maybe_wait(scheduler)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _hsleep(0.2, 0.4)
        el.click()
        log.debug("auth_cookies_banner_accepted")
        _hsleep(0.5, 0.9)
    except Exception:
        log.debug("auth_cookies_banner_not_present")


def _extract_error_banner(driver: WebDriver) -> str | None:
    """
    Devuelve un mensaje de error breve (o genérico) evitando volcar el body.
    """
    try:
        for by, sel in (
            (By.ID, "slfErrorAlert"),
            (By.XPATH, "//*[@role='alert']"),
        ):
            try:
                el = driver.find_element(by, sel)
                txt = (el.text or "").strip()
                if 2 < len(txt) < 120:
                    return _clean_text(txt)
            except NoSuchElementException:
                pass

        elems = driver.find_elements(By.XPATH, "//*[string-length(normalize-space()) < 200]")
        keywords = ("incorrect", "incorrecta", "contraseña", "password", "intentos", "bloquead", "error", "código")
        for el in elems[:30]:
            txt = (el.text or "").strip()
            low = txt.lower()
            if txt and any(k in low for k in keywords):
                return _clean_text(txt)
    except Exception:
        pass

    return "formulario de login detectado (sin mensaje específico)"


def _on_login_page(driver: WebDriver) -> bool:
    url = (driver.current_url or "").lower().rstrip("/")
    return url.endswith("instagram.com/accounts/login") or "/accounts/login" in url


def _is_logged_in(driver: WebDriver, timeout: int = 12) -> bool:
    """Señales inequívocas de sesión activa."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/direct/inbox/')]")),
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/accounts/edit')]")),
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/explore/')]")),
                EC.presence_of_element_located((By.XPATH, "//button[contains(.,'Log out') or contains(.,'Cerrar sesión')]")),
            )
        )
        return True
    except TimeoutException:
        return False


def _handle_save_login_info_popup(
    driver: WebDriver,
    *,
    scheduler: Optional[HumanScheduler] = None,
    timeout: int = 6,
) -> None:
    """Descarta popup 'Guardar información de inicio de sesión' si aparece."""
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Not Now']")),
                EC.element_to_be_clickable((By.XPATH, "//div[@role='dialog']//button[normalize-space()='Ahora no']")),
            )
        )
        _maybe_wait(scheduler)
        btn.click()
        log.debug("auth_save_login_info_popup_dismissed")
        _hsleep(0.4, 0.8)
    except Exception:
        log.debug("auth_save_login_info_popup_not_present")


def _type_slow(el, text: str, min_pause: float = 0.045, max_pause: float = 0.11) -> None:
    """Tipeo humano aleatorio (similar a random_sleep del código viejo)."""
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(min_pause, max_pause))


def _paste_text(el, text: str, *, scheduler: Optional[HumanScheduler] = None) -> None:
    """
    Simula copiar y pegar: selecciona todo el contenido del campo (Ctrl+A)
    y luego escribe el texto completo de una vez (simula Ctrl+V).
    Más rápido y más realista que escribir carácter por carácter.
    """
    _maybe_wait(scheduler)
    el.click()
    _hsleep(0.05, 0.12)
    
    el.send_keys(Keys.CONTROL, "a")
    _hsleep(0.08, 0.15)
    
    el.send_keys(text)
    _hsleep(0.1, 0.2)


def _locate_inputs(driver: WebDriver, wait_s: int) -> Tuple:
    """
    Localiza inputs de login.
    Instagram cambia frecuentemente los atributos; soportamos variantes comunes:
    - user: name="username" (legacy) o name="email" (actual), autocomplete="username"
    - pass: name="password" (legacy) o name="pass" (actual)
    """
    wait = WebDriverWait(driver, wait_s)

    # Username/email (usar any_of para evitar timeouts secuenciales largos)
    try:
        user_input = wait.until(
            EC.any_of(
                EC.presence_of_element_located((By.NAME, "username")),
                EC.presence_of_element_located((By.NAME, "email")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete*='username']")),
                # fallback extra (Instagram cambia atributos seguido)
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][name]")),
            )
        )
    except TimeoutException:
        log.error(
            "auth_login_input_username_not_found",
            url=(driver.current_url or ""),
            title=(getattr(driver, "title", "") or ""),
        )
        raise

    # Password
    try:
        pass_input = wait.until(
            EC.any_of(
                EC.presence_of_element_located((By.NAME, "password")),
                EC.presence_of_element_located((By.NAME, "pass")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")),
            )
        )
    except TimeoutException:
        log.error(
            "auth_login_input_password_not_found",
            url=(driver.current_url or ""),
            title=(getattr(driver, "title", "") or ""),
        )
        raise

    return user_input, pass_input


def _click_submit_strict(
    driver: WebDriver,
    *,
    wait_s: int,
    scheduler: Optional[HumanScheduler] = None,
) -> None:
    """
    Plan A — Estilo viejo (que te funcionaba): botón submit simple.
    """
    wait = WebDriverWait(driver, max(3, int(wait_s)))
    # 1) Botón submit clásico
    try:
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']")))
        _maybe_wait(scheduler)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        _hsleep(0.15, 0.3)
        btn.click()
        return
    except Exception:
        pass

    # 2) Div role=button con texto "Iniciar sesión" / "Log In" (nuevo UI)
    btn = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[@role='button'][.//span[normalize-space()='Iniciar sesión' or normalize-space()='Log In']]",
            )
        )
    )
    _maybe_wait(scheduler)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    _hsleep(0.15, 0.3)
    btn.click()


def _click_submit_fallbacks(
    driver: WebDriver,
    password_input,
    login_url: str,
    *,
    scheduler: Optional[HumanScheduler] = None,
) -> None:
    """
    Plan B/C — Fallbacks si el click 'viejo' no dispara el flujo:
      - Variantes de botón.
      - ENTER en password.
      - JS click directo.
    """
    tried = False
    selectors: List[Tuple[str, str]] = [
        (By.XPATH, "//form//button[@type='submit']"),
        (By.XPATH, "//div//button[@type='submit']"),
        (By.XPATH, "//button[normalize-space()='Iniciar sesión' or normalize-space()='Log In']"),
        (By.XPATH, "//button[.//div[text()='Iniciar sesión'] or .//div[text()='Log In']]"),
        (By.XPATH, "//*[@role='button'][.//span[normalize-space()='Iniciar sesión' or normalize-space()='Log In']]"),
    ]
    for by, sel in selectors:
        try:
            btn = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((by, sel)))
            _maybe_wait(scheduler)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            _hsleep(0.12, 0.25)
            btn.click()
            tried = True
            break
        except Exception:
            continue

    if not tried:
        try:
            _maybe_wait(scheduler)
            password_input.send_keys(Keys.ENTER)
            tried = True
        except Exception:
            pass
    if not tried:
        try:
            btn = driver.find_element(By.XPATH, "//button[@type='submit']")
            _maybe_wait(scheduler)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn)
        except Exception:
            pass

    _hsleep(0.5, 1.0)
    try:
        WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, "//*[@role='alert' or @id='slfErrorAlert']")),
                EC.url_changes(login_url),
            )
        )
    except TimeoutException:
        pass


# --------------
# Flujo de login
# --------------
def login_instagram(
    driver: WebDriver,
    *,
    username: str,
    password: Optional[str],
    base_url: str = "https://www.instagram.com/",
    login_url: str = "https://www.instagram.com/accounts/login/",
    two_factor_code_provider: Optional[Callable[[], str]] = None,
    wait_s: int = 25,
    scheduler: Optional[HumanScheduler] = None,
) -> None:
    """
    Login robusto que prioriza la forma de tocar la UI de la versión vieja (plan A)
    y agrega fallback modernos sólo si es necesario.
    - Logs compactos.
    - Reintentos acotados de submit.
    - Cookies solo si el login se verifica; si falla, se limpian.
    """
    if not username or password is None:
        raise BrowserAuthError("Faltan credenciales para login", username=username)

    log.info("auth_login_interactive_start", username=username)
    success = False

    try:
        _maybe_wait(scheduler)
        driver.get(login_url)
        log.debug("auth_nav_login_url", url=login_url)
        _hsleep(1.0, 2.0)
        _accept_cookies_banner(driver, scheduler=scheduler)

        user_input, pass_input = _locate_inputs(driver, wait_s)
        log.debug("auth_login_inputs_located")
        user_input.clear(); pass_input.clear()
        _paste_text(user_input, username, scheduler=scheduler)
        _hsleep(0.15, 0.3)
        _paste_text(pass_input, password, scheduler=scheduler)
        _hsleep(0.15, 0.3)

        submit_attempts = 3
        for attempt in range(1, submit_attempts + 1):
            log.debug("auth_submit_try", attempt=attempt, max_attempts=submit_attempts, plan="A")
            try:
                _click_submit_strict(driver, wait_s=8, scheduler=scheduler)
            except Exception as e:
                log.debug("auth_submit_plan_a_failed_fallback", error=str(e))
                _click_submit_fallbacks(driver, pass_input, login_url, scheduler=scheduler)

            _hsleep(0.6, 1.0)
            try:
                WebDriverWait(driver, 18).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/direct/inbox/') or contains(@href,'/accounts/edit') or contains(@href,'/explore/')]")),
                        EC.presence_of_element_located((By.XPATH, "//*[@role='alert' or @id='slfErrorAlert']")),
                        EC.url_changes(login_url),
                    )
                )
            except TimeoutException:
                continue

            banner = _extract_error_banner(driver)
            if banner and "formulario de login" not in banner:
                msg = _clean_text(f"Login falló: {banner}")
                log.warning("auth_login_failed_banner", username=username, message=msg)
                raise BrowserAuthError(msg, username=username)

            if not _on_login_page(driver):
                break

        if _on_login_page(driver):
            msg = "Login falló: permaneció en pantalla de login"
            log.warning("auth_login_stuck_on_login_page", username=username, message=msg)
            raise BrowserAuthError(msg, username=username)

        try:
            challenge = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.XPATH, "//input[@name='verificationCode' or @name='otpCode']"))
            )
            if challenge is not None:
                log.info("auth_two_factor_required", username=username)
                if two_factor_code_provider is None:
                    raise BrowserAuthError("Se requiere 2FA y no hay proveedor de código", username=username)
                code = (two_factor_code_provider() or "").strip()
                if not code:
                    raise BrowserAuthError("Código 2FA vacío", username=username)
                _maybe_wait(scheduler)
                challenge.clear()
                for ch in code:
                    challenge.send_keys(ch)
                    time.sleep(random.uniform(0.03, 0.08))
                _hsleep(0.3, 0.6)
                WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@type='button' or @type='submit']"))
                ).click()
                _hsleep(1.0, 1.5)
        except TimeoutException:
            log.debug("auth_two_factor_not_detected")

        _handle_save_login_info_popup(driver, scheduler=scheduler)
        _maybe_wait(scheduler)
        driver.get(base_url)
        log.debug("auth_nav_base_url_for_verification", url=base_url)

        if not _is_logged_in(driver, timeout=wait_s):
            msg = "No se pudo verificar sesión tras login"
            log.error("auth_login_verification_failed", username=username, message=msg)
            raise BrowserAuthError(msg, username=username)

        save_cookies(driver, username)
        success = True
        log.info("auth_login_success", username=username)

    except (TimeoutException, NoSuchElementException) as e:
        msg = f"Falló UI de login: {e.__class__.__name__}"
        log.error("auth_login_ui_failed", username=username, message=msg, error_type=e.__class__.__name__)
        raise BrowserAuthError(msg, username=username) from e

    except BrowserAuthError:
        raise

    except Exception as e:
        msg = _clean_text(f"Error inesperado durante login: {e}")
        log.error("auth_login_unexpected_error", username=username, message=msg, error=str(e))
        raise BrowserAuthError(msg, username=username) from e

    finally:
        if not success:
            try:
                clear_cookies_file(username)
                log.debug("auth_cookies_cleared_after_login_failure", username=username)
            except Exception:
                log.debug("auth_cookies_clear_failed_after_login_failure", username=username)
