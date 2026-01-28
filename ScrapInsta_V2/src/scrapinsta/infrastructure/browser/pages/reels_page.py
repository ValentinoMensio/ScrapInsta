from __future__ import annotations

import logging
from typing import Dict, List, Set, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Helpers de tu proyecto
from scrapinsta.crosscutting.parse import parse_number
from scrapinsta.crosscutting.human.tempo import HumanScheduler, sleep_jitter
from scrapinsta.crosscutting.human.human_actions import hover_element_human, human_scroll

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Utilidades internas
# -----------------------------------------------------------------------------
def _shortcode_from_href(href: str) -> str:
    """Extrae el shortcode del reel desde la URL: /reel/<code>/ -> <code>"""
    try:
        parts = href.strip("/").split("/")
        i = parts.index("reel")
        return parts[i + 1] if i + 1 < len(parts) else ""
    except Exception:
        return ""


def _query_reels(driver):
    """Devuelve los anchors que apuntan a reels."""
    return driver.find_elements(By.CSS_SELECTOR, "a[href*='/reel/']")


def has_reels(driver, timeout: float = 3.0) -> bool:
    """Detector local de reels visibles (evitamos dependencia cruzada)."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/reel/']"))
        )
        return True
    except TimeoutException:
        return False
    except Exception:
        return False


# JS helpers: evitamos múltiples round-trips
JS_GET_VIEWS = (
    "const r=arguments[0];"
    # Distintos contenedores que suele usar IG para el contador visible
    "let el=r.querySelector(\"div._aagv span, div._aajy span, div._aaj_ span\");"
    "return el ? el.textContent : '';"
)


JS_GET_HOVER_METRICS = (
    "const r=arguments[0];"
    "const ul=r.querySelector('ul.x6s0dn4, ul');"
    "if(!ul) return null;"
    "const lis=ul.querySelectorAll('li');"
    "if(lis.length<2) return null;"
    "const s0=lis[0].querySelector('span');"
    "const s1=lis[1].querySelector('span');"
    "return [s0 ? s0.textContent.trim() : '', s1 ? s1.textContent.trim() : ''];"
)


def hover_element_human_fast(
    driver,
    el,
    *,
    scheduler: Optional[HumanScheduler] = None,
    min_pause: float = 0.03,
    max_pause: float = 0.08,
) -> None:
    """
    Hover ultra-optimizado para reels - máxima velocidad manteniendo naturalidad mínima.
    - Pausas mínimas para navegación rápida.
    - Movimiento directo sin overshoot significativo.
    """
    try:
        # NO llamar scheduler.wait_turn() aquí para mayor velocidad
        # El scheduler se usa solo en puntos críticos del flujo principal

        from selenium.webdriver import ActionChains
        import random
        
        actions = ActionChains(driver)

        # Movimiento directo al elemento con offset mínimo
        off_x = random.randint(1, 4)
        off_y = random.randint(1, 4)

        actions.move_to_element_with_offset(el, off_x, off_y)
        actions.pause(random.uniform(min_pause, max_pause * 0.5))

        # Corrección rápida hacia el centro
        actions.move_to_element(el)
        actions.pause(random.uniform(min_pause, max_pause))
        actions.perform()

        # Micro-pausa mínima solo para que aparezca el overlay
        sleep_jitter(random.uniform(0.03, 0.07), 0.2)

    except Exception as e:
        logger.debug("hover_element_human_fast: fallo no crítico: %s", e)


def has_hover_available(driver, reel) -> bool:
    """
    Verificación rápida si un reel tiene hover disponible sin hacer hover.
    - Detecta si el elemento tiene la estructura necesaria para mostrar métricas.
    - Permite saltar reels que no tienen hover más rápido.
    """
    try:
        # Verificar si existe la estructura de hover sin hacer hover
        ul = driver.execute_script(
            "const r=arguments[0]; return r.querySelector('ul.x6s0dn4, ul');", 
            reel
        )
        if not ul:
            return False
            
        # Verificar si tiene al menos 2 elementos li (likes y comments)
        li_count = driver.execute_script(
            "const ul=arguments[0]; return ul ? ul.querySelectorAll('li').length : 0;", 
            ul
        )
        return li_count >= 2
    except Exception:
        return False


# -----------------------------------------------------------------------------
# API principal
# -----------------------------------------------------------------------------
def extract_reel_metrics_list(
    driver,
    *,
    limit: int = 5,
    scheduler: Optional[HumanScheduler] = None,
    fast_mode: bool = True,
) -> List[Dict[str, int | str]]:
    """
    Recolecta métricas por reel (lista de dicts):
        [{"url", "code", "views", "likes", "comments"}, ...]
    - Solo usa vistas y, tras hover humano, likes y comentarios.
    - Sin duración ni fecha.
    - fast_mode=True (default): tiempos ultra-reducidos para scraping masivo.
    """
    sched = scheduler or HumanScheduler()

    if not has_reels(driver):
        logger.warning("[reels] sin reels visibles")
        return []

    # Espera mínima a que aparezcan anchors de reels
    try:
        WebDriverWait(driver, 3).until(  # Reducido de 5 a 3
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/reel/']"))
        )
    except TimeoutException:
        logger.warning("[reels] timeout esperando anchors de reels")
        return []

    reels = _query_reels(driver)
    logger.info("[reels] visibles=%d fast_mode=%s", len(reels), fast_mode)

    # Arranque rápido
    sleep_jitter(0.15, 0.15) if fast_mode else sleep_jitter(0.5, 0.25)
    collected: List[Dict[str, int | str]] = []
    seen: Set[str] = set()
    idx = 0

    while len(collected) < limit:
        if idx >= len(reels):
            # Scroll rápido para cargar más
            human_scroll(driver, total_px=900, duration=0.25 if fast_mode else 0.6, scheduler=None)
            sleep_jitter(0.05, 0.1) if fast_mode else sleep_jitter(0.15, 0.15)

            reels_new = _query_reels(driver)
            if len(reels_new) <= len(reels):
                logger.debug("[reels] sin nuevos tras scroll; fin")
                break
            reels = reels_new
            continue

        reel = reels[idx]
        idx += 1

        # URL y shortcode
        href = ""
        try:
            href = reel.get_attribute("href") or ""
        except Exception:
            logger.debug("[reels] idx=%d sin href (DOM)", idx)
            continue

        if not href or href in seen:
            logger.debug("[reels] idx=%d duplicado o vacío", idx)
            continue
        seen.add(href)

        row: Dict[str, int | str] = {"url": href, "code": _shortcode_from_href(href), "views": 0, "likes": 0, "comments": 0}

        try:
            # Centrar el reel en viewport - mínima pausa
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reel)
            sleep_jitter(0.02, 0.05) if fast_mode else sleep_jitter(0.08, 0.08)

            # --- Vistas (sin hover) - ultra-rápido ---
            try:
                views_text = driver.execute_script(JS_GET_VIEWS, reel) or ""
                if not views_text.strip():
                    # Verificación rápida - timeout mínimo
                    try:
                        WebDriverWait(driver, 0.25 if fast_mode else 0.5).until(
                            EC.visibility_of_element_located(
                                (By.XPATH, ".//div[contains(@class,'_aagv') or contains(@class,'_aajy') or contains(@class,'_aaj_')]//span")
                            )
                        )
                        views_text = driver.execute_script(JS_GET_VIEWS, reel) or ""
                    except TimeoutException:
                        pass

                if not views_text.strip():
                    logger.debug("[reels] idx=%d sin vistas visibles", idx)
                    continue

                row["views"] = parse_number(views_text)
            except Exception as e:
                logger.debug("[reels] idx=%d vistas no leídas: %s", idx, e)
                continue

            # --- Likes / Comments (hover rápido) ---
            try:
                # Verificación rápida previa: ¿tiene hover disponible?
                if not has_hover_available(driver, reel):
                    logger.debug("[reels] idx=%d sin hover disponible -> skip", idx)
                    continue
                
                # Hover ultra-rápido
                hover_element_human_fast(driver, reel, scheduler=None)
                sleep_jitter(0.04, 0.08) if fast_mode else sleep_jitter(0.12, 0.15)

                # Verificación de métricas
                pair = driver.execute_script(JS_GET_HOVER_METRICS, reel)
                if not pair or len(pair) < 2:
                    # Un solo intento adicional rápido
                    sleep_jitter(0.03, 0.05) if fast_mode else sleep_jitter(0.08, 0.1)
                    pair = driver.execute_script(JS_GET_HOVER_METRICS, reel)
                    if not pair or len(pair) < 2:
                        logger.debug("[reels] idx=%d hover sin métricas -> skip", idx)
                        continue

                likes_text = (pair[0] or "").strip()
                comments_text = (pair[1] or "").strip()
                if not likes_text or not comments_text:
                    logger.debug("[reels] idx=%d métricas hover vacías -> skip", idx)
                    continue

                row["likes"] = parse_number(likes_text)
                row["comments"] = parse_number(comments_text)

                if row["likes"] == 0 and row["comments"] == 0:
                    logger.debug("[reels] idx=%d métricas 0/0 tras parse -> skip", idx)
                    continue
            except Exception as e:
                logger.debug("[reels] idx=%d hover fallido: %s -> skip", idx, e)
                continue

            collected.append(row)
            logger.info("[reels] idx=%d code=%s v=%s l=%s c=%s", idx, row["code"], row["views"], row["likes"], row["comments"])
            # Pausa mínima entre reels exitosos
            sleep_jitter(0.05, 0.1) if fast_mode else sleep_jitter(0.15, 0.15)

        except Exception as e:
            logger.warning("[reels] idx=%d error inesperado: %s", idx, e)
            continue

    logger.info("[reels] recolectados=%d", len(collected))
    return collected


def extract_reel_metrics(
    driver,
    max_reels: int = 5,
    *,
    scheduler: Optional[HumanScheduler] = None,
    fast_mode: bool = True,
) -> Dict[str, int | List[Dict[str, int | str]]]:
    """
    Wrapper retrocompatible con tu firma anterior:
    - Devuelve totales y lista por reel.
    - fast_mode=True (default): tiempos ultra-reducidos para scraping masivo.
    """
    data = extract_reel_metrics_list(driver, limit=max_reels, scheduler=scheduler, fast_mode=fast_mode)

    totals = {
        "total_views": sum(int(d.get("views", 0) or 0) for d in data),
        "total_likes": sum(int(d.get("likes", 0) or 0) for d in data),
        "total_comments": sum(int(d.get("comments", 0) or 0) for d in data),
        "reel_count": len(data),
        "reel_data": data,
    }
    logger.info("[reels] totales=%s", totals)
    return totals
