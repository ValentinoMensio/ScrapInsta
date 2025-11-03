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
    min_pause: float = 0.08,
    max_pause: float = 0.18,
) -> None:
    """
    Hover optimizado para reels - más rápido que hover_element_human.
    - Pausas reducidas para navegación más ágil.
    - Menos overshoot para transiciones más directas.
    """
    try:
        if scheduler:
            scheduler.wait_turn()

        from selenium.webdriver import ActionChains
        import random
        
        actions = ActionChains(driver)

        # Overshoot mínimo para velocidad
        off_x = random.randint(2, 8)  # Reducido de 3-14 a 2-8
        off_y = random.randint(2, 8)  # Reducido de 3-14 a 2-8

        actions.move_to_element_with_offset(el, off_x, off_y)
        actions.pause(random.uniform(min_pause * 0.3, max_pause * 0.4))  # Reducido

        # Corrección rápida hacia el centro
        actions.move_to_element(el)
        actions.pause(random.uniform(min_pause * 0.4, max_pause * 0.6))  # Reducido
        actions.perform()

        # Micro-pausa mínima para UI
        sleep_jitter(random.uniform(0.06, 0.15), 0.3)  # Reducido de 0.12-0.3 a 0.06-0.15

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
) -> List[Dict[str, int | str]]:
    """
    Recolecta métricas por reel (lista de dicts):
        [{"url", "code", "views", "likes", "comments"}, ...]
    - Solo usa vistas y, tras hover humano, likes y comentarios.
    - Sin duración ni fecha.
    """
    sched = scheduler or HumanScheduler()

    if not has_reels(driver):
        logger.warning("[reels] sin reels visibles")
        return []

    # Espera mínima a que aparezcan anchors de reels
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/reel/']"))
        )
    except TimeoutException:
        logger.warning("[reels] timeout esperando anchors de reels")
        return []

    reels = _query_reels(driver)
    logger.info("[reels] visibles=%d", len(reels))

    # Arranque "humano" - reducido
    sleep_jitter(0.5, 0.25)  # Optimizado: reducido de 0.8±0.3 a 0.5±0.25
    collected: List[Dict[str, int | str]] = []
    seen: Set[str] = set()
    idx = 0

    while len(collected) < limit:
        if idx >= len(reels):
            # Scroll humano para cargar más - más rápido
            sched.wait_turn()
            human_scroll(driver, total_px=900, duration=0.6, scheduler=sched)  # Optimizado: reducido de 0.8 a 0.6
            sleep_jitter(0.15, 0.15)  # Optimizado: reducido de 0.2±0.2 a 0.15±0.15

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
            # Centrar el reel en viewport - sin pausa innecesaria
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reel)
            sleep_jitter(0.08, 0.08)  # Optimizado: reducido de 0.1±0.1 a 0.08±0.08

            # --- Vistas (sin hover) - optimizado ---
            try:
                sched.wait_turn()
                views_text = driver.execute_script(JS_GET_VIEWS, reel) or ""
                if not views_text.strip():
                    # Verificación rápida de visibilidad - timeout reducido
                    try:
                        WebDriverWait(driver, 0.5).until(  # Reducido de 1.0 a 0.5
                            EC.visibility_of_element_located(
                                (By.XPATH, ".//div[contains(@class,'_aagv') or contains(@class,'_aajy') or contains(@class,'_aaj_')]//span")
                            )
                        )
                        views_text = driver.execute_script(JS_GET_VIEWS, reel) or ""
                    except TimeoutException:
                        pass  # Continuar sin vistas si no aparecen rápido

                if not views_text.strip():
                    logger.debug("[reels] idx=%d sin vistas visibles", idx)
                    continue

                row["views"] = parse_number(views_text)
            except Exception as e:
                logger.debug("[reels] idx=%d vistas no leídas: %s", idx, e)
                continue

            # --- Likes / Comments (hover humano) - OPTIMIZADO ---
            try:
                # Verificación rápida previa: ¿tiene hover disponible?
                if not has_hover_available(driver, reel):
                    logger.debug("[reels] idx=%d sin hover disponible -> skip", idx)
                    continue  # ← saltar rápido sin hacer hover
                
                sched.wait_turn()
                
                # Hover más rápido con configuración optimizada
                hover_element_human_fast(driver, reel, scheduler=sched)
                sleep_jitter(0.12, 0.15)  # Reducido aún más: 0.15±0.2 a 0.12±0.15

                # Verificación rápida de hover con timeout reducido
                pair = driver.execute_script(JS_GET_HOVER_METRICS, reel)
                if not pair or len(pair) < 2:
                    # Intento rápido adicional si no hay métricas
                    sleep_jitter(0.08, 0.1)  # Reducido de 0.1±0.1 a 0.08±0.1
                    pair = driver.execute_script(JS_GET_HOVER_METRICS, reel)
                    if not pair or len(pair) < 2:
                        logger.debug("[reels] idx=%d hover sin métricas -> skip", idx)
                        continue  # ← no guardamos el reel

                likes_text = (pair[0] or "").strip()
                comments_text = (pair[1] or "").strip()
                if not likes_text or not comments_text:
                    logger.debug("[reels] idx=%d métricas hover vacías -> skip", idx)
                    continue  # ← no guardamos el reel

                row["likes"] = parse_number(likes_text)
                row["comments"] = parse_number(comments_text)

                # (Opcional) si ambos quedan 0, probablemente falló el overlay igual
                if row["likes"] == 0 and row["comments"] == 0:
                    logger.debug("[reels] idx=%d métricas 0/0 tras parse -> skip", idx)
                    continue  # ← no guardamos el reel
            except Exception as e:
                logger.debug("[reels] idx=%d hover fallido: %s -> skip", idx, e)
                continue  # ← no guardamos el reel

            collected.append(row)
            logger.info("[reels] idx=%d code=%s v=%s l=%s c=%s", idx, row["code"], row["views"], row["likes"], row["comments"])
            sleep_jitter(0.15, 0.15)  # Optimizado: reducido de 0.25±0.2 a 0.15±0.15

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
) -> Dict[str, int | List[Dict[str, int | str]]]:
    """
    Wrapper retrocompatible con tu firma anterior:
    - Devuelve totales y lista por reel.
    """
    data = extract_reel_metrics_list(driver, limit=max_reels, scheduler=scheduler)

    totals = {
        "total_views": sum(int(d.get("views", 0) or 0) for d in data),
        "total_likes": sum(int(d.get("likes", 0) or 0) for d in data),
        "total_comments": sum(int(d.get("comments", 0) or 0) for d in data),
        "reel_count": len(data),
        "reel_data": data,
    }
    logger.info("[reels] totales=%s", totals)
    return totals
