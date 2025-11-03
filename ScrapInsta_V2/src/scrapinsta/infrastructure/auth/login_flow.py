from __future__ import annotations
import logging, time, random
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

# === Jitter humano, compatible con versión vieja (random_sleep) ===
try:
    from scrapinsta.crosscutting.human.tempo import sleep_jitter as _hsleep
except Exception:
    def _hsleep(a: float, b: float) -> None:
        time.sleep(max(0.0, (a + b) / 2.0))

logger = logging.getLogger(__name__)


# ---------------------------
# Utilidades de texto y UI
# ---------------------------
def _clean_text(s: str, max_len: int = 220) -> str:
    """Normaliza y trunca para logs compactos."""
    if not s:
        return ""
    compact = " ".join(s.split())
    return compact if len(compact) <= max_len else compact[: max_len - 1] + "…"


def _accept_cookies_banner(driver: WebDriver, timeout: int = 8) -> None:
    """Cierra banner de cookies si está (no loggea ruido)."""
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Allow all cookies']")),
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Aceptar']")),
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Allow essential and optional cookies']")),
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _hsleep(0.2, 0.4)
        el.click()
        logger.debug("[auth] Banner de cookies aceptado")
        _hsleep(0.5, 0.9)
    except Exception:
        logger.debug("[auth] Sin banner de cookies (ok)")


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


def _handle_save_login_info_popup(driver: WebDriver, timeout: int = 6) -> None:
    """Descarta popup 'Guardar información de inicio de sesión' si aparece."""
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Not Now']")),
                EC.element_to_be_clickable((By.XPATH, "//div[@role='dialog']//button[normalize-space()='Ahora no']")),
            )
        )
        btn.click()
        logger.debug("[auth] Dismiss 'Guardar info de inicio de sesión'")
        _hsleep(0.4, 0.8)
    except Exception:
        logger.debug("[auth] No apareció popup 'Guardar info' (ok)")


def _type_slow(el, text: str, min_pause: float = 0.045, max_pause: float = 0.11) -> None:
    """Tipeo humano aleatorio (similar a random_sleep del código viejo)."""
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(min_pause, max_pause))


def _paste_text(el, text: str) -> None:
    """
    Simula copiar y pegar: selecciona todo el contenido del campo (Ctrl+A)
    y luego escribe el texto completo de una vez (simula Ctrl+V).
    Más rápido y más realista que escribir carácter por carácter.
    """
    # Hacer foco en el elemento
    el.click()
    _hsleep(0.05, 0.12)
    
    # Seleccionar todo (Ctrl+A) - simula que vamos a reemplazar el contenido
    el.send_keys(Keys.CONTROL, "a")
    _hsleep(0.08, 0.15)
    
    # Simular pegar: escribir el texto completo de una vez
    # (Como no podemos acceder al portapapeles real, escribimos directamente)
    el.send_keys(text)
    _hsleep(0.1, 0.2)  # Pequeña pausa para que el navegador procese el "pegado"


def _locate_inputs(driver: WebDriver, wait_s: int) -> Tuple:
    """Localiza username/password con el patrón de la versión vieja (funcional)."""
    wait = WebDriverWait(driver, wait_s)
    user_input = wait.until(EC.presence_of_element_located((By.NAME, "username")))
    pass_input = driver.find_element(By.NAME, "password")
    return user_input, pass_input


def _click_submit_strict(driver: WebDriver, wait_s: int) -> None:
    """
    Plan A — Estilo viejo (que te funcionaba): botón submit simple.
    """
    btn = driver.find_element(By.XPATH, "//button[@type='submit']")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    _hsleep(0.15, 0.3)
    btn.click()


def _click_submit_fallbacks(driver: WebDriver, password_input, login_url: str) -> None:
    """
    Plan B/C — Fallbacks si el click 'viejo' no dispara el flujo:
      - Variantes de botón.
      - ENTER en password.
      - JS click directo.
    """
    tried = False
    # B1) variantes de botón
    selectors: List[Tuple[str, str]] = [
        (By.XPATH, "//form//button[@type='submit']"),
        (By.XPATH, "//div//button[@type='submit']"),
        (By.XPATH, "//button[normalize-space()='Iniciar sesión' or normalize-space()='Log In']"),
        (By.XPATH, "//button[.//div[text()='Iniciar sesión'] or .//div[text()='Log In']]"),
    ]
    for by, sel in selectors:
        try:
            btn = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            _hsleep(0.12, 0.25)
            btn.click()
            tried = True
            break
        except Exception:
            continue

    # B2) ENTER en password
    if not tried:
        try:
            password_input.send_keys(Keys.ENTER)
            tried = True
        except Exception:
            pass

    # B3) JS click sobre cualquier submit visible
    if not tried:
        try:
            btn = driver.find_element(By.XPATH, "//button[@type='submit']")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn)
        except Exception:
            # último recurso: nada más que hacer aquí; el caller evaluará si seguimos en login
            pass

    # pequeña espera para que la UI reaccione
    _hsleep(0.5, 1.0)
    try:
        WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, "//*[@role='alert' or @id='slfErrorAlert']")),
                EC.url_changes(login_url),
            )
        )
    except TimeoutException:
        # caller decidirá reintentar según siga en pantalla de login
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

    logger.info("[auth] Iniciando login interactivo para %s", username)
    success = False

    try:
        # 1) Ir a /accounts/login
        driver.get(login_url)
        logger.debug("[auth] GET %s", login_url)
        _hsleep(1.0, 2.0)  # estilo viejo: pequeña pausa antes de interactuar
        _accept_cookies_banner(driver)

        # 2) Completar formulario simulando copiar y pegar
        user_input, pass_input = _locate_inputs(driver, wait_s)
        logger.debug("[auth] Inputs localizados (username/password)")
        user_input.clear(); pass_input.clear()
        _paste_text(user_input, username)
        _hsleep(0.15, 0.3)  # Pausa entre campos
        _paste_text(pass_input, password)
        _hsleep(0.15, 0.3)  # Pausa antes de submit

        # 3) Intento de submit — Plan A (viejo)
        submit_attempts = 3
        for attempt in range(1, submit_attempts + 1):
            logger.debug("[auth] Submit try %d/%d (plan A)", attempt, submit_attempts)
            try:
                _click_submit_strict(driver, wait_s=8)
            except Exception as e:
                logger.debug("[auth] Plan A click submit falló, probando fallbacks (detalle suprimido)")
                _click_submit_fallbacks(driver, pass_input, login_url)

            # Esperar reacción mínima
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
                # Si no pasó nada visible, reintentar
                continue

            banner = _extract_error_banner(driver)
            if banner and "formulario de login" not in banner:
                msg = _clean_text(f"Login falló: {banner}")
                logger.warning("[auth] %s (usuario=%s)", msg, username)
                raise BrowserAuthError(msg, username=username)

            if not _on_login_page(driver):
                break  # salimos de login → continuar

        # Si seguimos en login tras los intentos, es fallo
        if _on_login_page(driver):
            msg = "Login falló: permaneció en pantalla de login"
            logger.warning("[auth] %s (usuario=%s)", msg, username)
            raise BrowserAuthError(msg, username=username)

        # 4) 2FA (si aparece)
        try:
            challenge = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.XPATH, "//input[@name='verificationCode' or @name='otpCode']"))
            )
            if challenge is not None:
                logger.info("[auth] Se requiere 2FA para %s", username)
                if two_factor_code_provider is None:
                    raise BrowserAuthError("Se requiere 2FA y no hay proveedor de código", username=username)
                code = (two_factor_code_provider() or "").strip()
                if not code:
                    raise BrowserAuthError("Código 2FA vacío", username=username)
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
            logger.debug("[auth] No se detectó flujo de 2FA (ok)")

        # 5) Dismiss popups + verificación final
        _handle_save_login_info_popup(driver)
        driver.get(base_url)
        logger.debug("[auth] GET %s para verificación de sesión", base_url)

        if not _is_logged_in(driver, timeout=wait_s):
            msg = "No se pudo verificar sesión tras login"
            logger.error("[auth] %s (usuario=%s)", msg, username)
            raise BrowserAuthError(msg, username=username)

        # 6) Guardar cookies SOLO si login verificado
        save_cookies(driver, username)
        success = True
        logger.info("[auth] Login exitoso y cookies guardadas para %s", username)

    except (TimeoutException, NoSuchElementException) as e:
        msg = f"Falló UI de login: {e.__class__.__name__}"
        logger.error("[auth] %s (usuario=%s)", msg, username)
        raise BrowserAuthError(msg, username=username) from e

    except BrowserAuthError:
        # Re-lanzamos; el finally limpia cookies si no hubo éxito
        raise

    except Exception as e:
        msg = _clean_text(f"Error inesperado durante login: {e}")
        logger.exception("[auth] %s (usuario=%s)", msg, username)
        raise BrowserAuthError(msg, username=username) from e

    finally:
        if not success:
            try:
                clear_cookies_file(username)
                logger.debug("[auth] Cookies previas eliminadas tras fallo de login (%s)", username)
            except Exception:
                logger.debug("[auth] No se pudo eliminar cookies previas (%s)", username, exc_info=True)
