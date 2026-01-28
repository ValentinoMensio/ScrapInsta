from __future__ import annotations

import logging
import re
from typing import Optional, Dict
from selenium.webdriver.remote.webdriver import WebDriver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from scrapinsta.domain.models.profile_models import ProfileSnapshot
from scrapinsta.crosscutting.human.tempo import HumanScheduler


from scrapinsta.crosscutting.parse import parse_number, extract_number

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilidades internas (robustas ante cambios menores de DOM)
# ---------------------------------------------------------------------------

def _find_first_text(driver: WebDriver, selectors: list[tuple[By, str]], timeout: int = 1) -> Optional[str]:
    """
    Intenta varios selectores en orden y devuelve el texto del primero que funcione.
    OPTIMIZADO: Timeouts reducidos y ordenados por probabilidad de éxito.
    """
    # Timeout reducido para selectores secundarios (los que menos funcionan)
    timeouts = [timeout, max(0.3, timeout * 0.5), max(0.3, timeout * 0.5)]
    
    for i, (by, selector) in enumerate(selectors):
        try:
            t = timeouts[i] if i < len(timeouts) else max(0.3, timeout * 0.5)
            elem = WebDriverWait(driver, t).until(
                EC.presence_of_element_located((by, selector))
            )
            text = elem.text or ""
            if text.strip():
                logger.info("Selector exitoso: %s='%s'", selector, text)
                return text.strip()
        except (NoSuchElementException, TimeoutException):
            logger.debug("Selector no encontrado o timeout: %s", selector)
        except StaleElementReferenceException:
            logger.debug("Elemento obsoleto para selector: %s", selector)
        except Exception as e:
            logger.debug("Error con selector %s: %s", selector, e)
    return None

# ---------------------------------------------------------------------------
# Extracción de campos puntuales
# ---------------------------------------------------------------------------

def close_instagram_login_popup(
    driver: WebDriver,
    *,
    scheduler: Optional[HumanScheduler] = None,
    timeout: int = 5,
) -> bool:
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@role='dialog']//div[@role='button' or @tabindex='0']"
                "//*[name()='svg' or name()='path']"
                "/ancestor::div[@role='button' or @tabindex='0']"
            ))
        )
        if scheduler is not None:
            try:
                scheduler.wait_turn()
            except Exception:
                pass
        btn.click()
        return True
    except (NoSuchElementException, ElementClickInterceptedException, TimeoutException):
        return False
    except Exception:
        return False


def extract_biography(driver: WebDriver) -> str:
    """
    Bio del perfil. Usa varios selectores por si cambia el DOM.
    OPTIMIZADO: Ordenado por probabilidad de éxito (más común primero).
    """
    try:
        # Orden optimizado: primero el más común (role='button'), luego los alternativos
        text = _find_first_text(driver, [
            (By.XPATH, "//div[@role='button']//span[@dir='auto']"),  # Más común primero
            (By.XPATH, "//header//h1/following-sibling::div//span[@dir='auto']"),
            (By.XPATH, "//section//ul/ancestor::section/preceding::div[1]//span[@dir='auto']"),
        ], timeout=0.8)  # Timeout base reducido de 1.0 a 0.8
        if not text:
            logger.debug("Bio no encontrada")
            return ""
        return text
    except Exception as e:
        logger.debug("extract_biography: error inesperado: %s", e)
        return ""
    

def _stat_number_from(elem) -> int:
    """Prefiere @title; si no, usa texto visible."""
    try:
        with_title = elem.find_element(By.XPATH, ".//span[@title]")
        raw = with_title.get_attribute("title") or ""
    except NoSuchElementException:
        raw = elem.text or ""
    num = parse_number(extract_number(raw))
    logger.info("   ↳ número detectado: %s (%s)", num, raw)
    return num


def extract_basic_stats(driver: WebDriver, timeout: int = 5):
    """
    Extrae posts, followers y following desde el <header>.
    - Usa anchors /followers y /following si existen (más confiables).
    - Busca bloque de posts por texto ('posts' o 'publicaciones').
    - Usa parse_number(extract_number(...)).
    """
    try:
        header = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//header"))
        )
        stats = {"posts": 0, "followers": 0, "following": 0}

        # --- Followers ---
        try:
            el = header.find_element(By.XPATH, ".//a[contains(@href,'/followers')]/span")
            if el.is_displayed():
                stats["followers"] = _stat_number_from(el)
                logger.info("[followers] %s", stats["followers"])
        except NoSuchElementException:
            logger.info("   ↳ no se encontró bloque /followers")

        # --- Following ---
        try:
            el = header.find_element(By.XPATH, ".//a[contains(@href,'/following')]/span")
            if el.is_displayed():
                stats["following"] = _stat_number_from(el)
                logger.info("[following] %s", stats["following"])
        except NoSuchElementException:
            logger.info("   ↳ no se encontró bloque /following")

        # --- Posts ---
        try:
            posts_el = header.find_element(
                By.XPATH,
                ".//span[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜ','abcdefghijklmnopqrstuvwxyzáéíóúü'),'posts') "
                "or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜ','abcdefghijklmnopqrstuvwxyzáéíóúü'),'publicaciones')]"
            )
            if posts_el.is_displayed():
                try:
                    num_el = posts_el.find_element(By.XPATH, ".//span[normalize-space()]")
                    stats["posts"] = _stat_number_from(num_el)
                except NoSuchElementException:
                    stats["posts"] = parse_number(extract_number(posts_el.text or ""))
                logger.info("[posts] %s", stats["posts"])
        except NoSuchElementException:
            logger.info("   ↳ no se encontró bloque de publicaciones")

        # --- Verificación final ---
        if all(v == 0 for v in stats.values()):
            logger.warning("No se pudieron leer stats (0/0/0). Revisar layout o bloqueos.")
            return None

        logger.info("Stats extraídas: posts=%s, followers=%s, following=%s",
                    stats["posts"], stats["followers"], stats["following"])
        return stats

    except Exception as e:
        logger.exception("Error extrayendo estadísticas básicas: %s", e)
        return None


def is_profile_private(driver: WebDriver) -> bool:
    """
    Detecta si el perfil es privado escaneando textos típicos.
    """
    try:
        spans = driver.find_elements(By.CSS_SELECTOR, "span[dir='auto']")
        for s in spans:
            try:
                t = (s.text or "").lower()
                if "esta cuenta es privada" in t or "síguela para ver" in t or "this account is private" in t:
                    return True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return False
    except Exception:
        return False


def is_profile_verified(driver: WebDriver) -> bool:
    """
    Busca el badge de verificación accesible por aria-label.
    """
    try:
        driver.find_element(By.CSS_SELECTOR, "svg[aria-label='Verificado'], svg[aria-label='Verified']")
        return True
    except NoSuchElementException:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# API principal para el caso de uso
# ---------------------------------------------------------------------------

def get_profile_snapshot(driver: WebDriver, username: str, wait_seconds: int = 8) -> ProfileSnapshot:
    """
    Navega el DOM ya cargado y arma un ProfileSnapshot (DTO de dominio).
    - NO hace get(url); se asume que el caller ya navegó a https://instagram.com/<username>/.
    - Usa heurísticas robustas y logs claros, sin tirar excepciones al caller.
    """
    ctx = {"username": username}

    # Espera mínima a que exista el header (mejora estabilidad post-navegación)
    try:
        WebDriverWait(driver, wait_seconds).until(
            EC.presence_of_element_located((By.TAG_NAME, "header"))
        )
    except TimeoutException:
        logger.warning("[profile] %s header no disponible tras %ss", username, wait_seconds, extra=ctx)

    # Popups (si aparece el popup de login, cerrarlo y seguir)
    if close_instagram_login_popup(driver):
        logger.info("[profile] %s popup de login cerrado", username, extra=ctx)

    # Extracciones robustas (reusan tus helpers actuales)
    stats = extract_basic_stats(driver) or {}

    
    # Aceptar legado 'following' → normalizar a 'followings'
    if "followings" not in stats and "following" in stats:
        stats["followings"] = stats.get("following")

    bio = extract_biography(driver)
    is_verified = is_profile_verified(driver)
    is_private = is_profile_private(driver)

    # Log sintético para trazabilidad
    logger.info(
        "[profile] %s snapshot extraído: posts=%s, followers=%s, followings=%s, verified=%s, private=%s",
        username,
        stats.get("posts"),
        stats.get("followers"),
        stats.get("followings"),
        is_verified,
        is_private,
        extra=ctx
    )

    # Armar DTO de dominio
    try:
        snapshot = ProfileSnapshot(
            username=username,
            bio=bio or "",
            followers=stats.get("followers"),
            followings=stats.get("followings"),
            posts=stats.get("posts"),
            is_verified=bool(is_verified),
            privacy="private" if is_private else "public"
        )
    except Exception as e:
        # Fallback súper defensivo: si la firma del DTO cambiara, no rompemos al caller
        logger.info("ProfileSnapshot build fallback (%s): %s", username, e, extra=ctx)
        snapshot = ProfileSnapshot(
            username=str(username or ""),
            bio=str(bio or ""),
            followers=stats.get("followers"),
            followings=stats.get("followings"),
            posts=stats.get("posts"),
            is_verified=bool(is_verified),
            privacy="private" if is_private else "public",
        )

    return snapshot

