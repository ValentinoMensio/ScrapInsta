# src/core/profile/utils/reels.py

import logging
from typing import Dict, Set
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from core.profile.utils.detection import has_reels
from core.utils.parse import parse_number

# Helpers “humanos”
from core.utils.humanize_helpers import (
    HumanScheduler,
    hover_element_human,
    human_scroll,
    sleep_jitter,
)

logger = logging.getLogger(__name__)

# Ritmo humano (~18 acciones/min ≈ 1 acción cada ~3.3s con jitter)
SCHED = HumanScheduler(actions_per_min=18, jitter_pct=0.25, min_interval=0.9)


def extract_reel_metrics(driver, max_reels: int = 5) -> Dict[str, float]:
    """
    Extrae métricas de los primeros reels que muestren TODAS las métricas (vistas, likes y comentarios).
    """

    metrics = {
        'total_views': 0,
        'total_likes': 0,
        'total_comments': 0,
        'reel_count': 0,
        'reel_data': []
    }

    def refresh_reels():
        return driver.find_elements(By.CSS_SELECTOR, "a[href*='/reel/']")

    # JS helpers: acceso directo y rápido al DOM (menos round-trips)
    JS_GET_VIEWS = (
        "const r=arguments[0];"
        "let el=r.querySelector(\"div._aagv span.html-span, div._aajy span.html-span, div._aaj_ span.html-span\");"
        "return el ? el.textContent : '';"
    )
    JS_GET_HOVER_METRICS = (
        "const r=arguments[0];"
        "const ul=r.querySelector('ul.x6s0dn4');"
        "if(!ul) return null;"
        "const spans=ul.querySelectorAll('li span.html-span');"
        "if(spans.length<2) return null;"
        "return [spans[0].textContent, spans[1].textContent];"
    )

    if not has_reels(driver):
        logger.warning("No se encontraron reels visibles en el perfil")
        return metrics

    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/reel/']"))
        )
        all_reels = refresh_reels()
        logger.info(f"Se encontraron {len(all_reels)} reels")

        collected = 0
        index = 0
        attempts = 0
        seen: Set[str] = set()

        # Pequeña espera inicial (equivalente aprox. a 1-3s)
        sleep_jitter(mean=2.0, jitter_pct=0.5)

        while collected < max_reels and attempts < 100:
            # Si me quedo sin reels visibles, scrolleo para cargar más (scroll humano)
            if index >= len(all_reels):
                previous_count = len(all_reels)
                SCHED.wait_turn()  # ritmo antes del scroll
                human_scroll(driver, total_px=900, duration=1.1, step_px=140, jitter_px=40)
                # Pausa corta post-scroll (equiv. a 0.5-0.7s)
                sleep_jitter(mean=0.6, jitter_pct=0.2)
                all_reels = refresh_reels()
                logger.debug(f"[Scroll] Nuevos reels encontrados: {len(all_reels)}")
                if len(all_reels) == previous_count:
                    logger.debug("No se encontraron más reels nuevos. Finalizando.")
                    break
                continue

            try:
                reel = all_reels[index]
            except IndexError:
                logger.warning(f"[Reel {index}] Reel ya no está disponible en el DOM")
                break

            index += 1
            attempts += 1

            # Evitar reprocesar el mismo reel
            try:
                href = reel.get_attribute("href")
                if href in seen:
                    logger.debug(f"[Reel {index}] Duplicado (href repetido), descartado")
                    continue
                seen.add(href)
            except Exception:
                # Si no puedo leer href, igual intento
                pass

            reel_metrics = {'views': 0, 'likes': 0, 'comments': 0}

            try:
                # Llevar el reel al centro y pequeña pausa (humano) ~0.2-0.3s
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reel)
                sleep_jitter(mean=0.25, jitter_pct=0.2)

                # --- Paso 1: Vistas (sin hover) - lectura rápida por JS ---
                try:
                    # Espaciamos lecturas con el scheduler
                    SCHED.wait_turn()
                    views_text = driver.execute_script(JS_GET_VIEWS, reel) or ""
                    if not views_text.strip():
                        # Fallback corto: pequeño wait por si aún no pintó
                        WebDriverWait(driver, 1.0).until(
                            EC.visibility_of_element_located(
                                (By.XPATH, ".//div[contains(@class, '_aagv') or contains(@class, '_aajy') or contains(@class, '_aaj_')]//span[contains(@class, 'html-span')]")
                            )
                        )
                        views_text = driver.execute_script(JS_GET_VIEWS, reel) or ""
                    if not views_text.strip():
                        logger.debug(f"[Reel {index}] Sin vistas visibles, descartado")
                        continue

                    reel_metrics['views'] = parse_number(views_text)
                except Exception as e:
                    logger.debug(f"[Reel {index}] Sin vistas: {e}")
                    continue  # ⛔ Sin vistas → no sirve

                # --- Paso 2: Hover real para likes y comentarios ---
                try:
                    SCHED.wait_turn()  # ritmo antes del hover
                    hover_element_human(driver, reel, duration=0.4)  # hover con overshoot suave
                    # mini-pausa para que aparezcan contadores dependientes del hover (0.18-0.5s)
                    sleep_jitter(mean=0.34, jitter_pct=0.47)

                    # Lee ambos con un solo acceso JS; si no están, descarta
                    pair = driver.execute_script(JS_GET_HOVER_METRICS, reel)
                    if not pair or len(pair) < 2:
                        logger.debug(f"[Reel {index}] Hover parcial o sin métricas, descartado")
                        continue
                    likes_text, comments_text = pair[0] or "", pair[1] or ""
                    if not likes_text.strip() or not comments_text.strip():
                        logger.debug(f"[Reel {index}] Métricas de hover vacías, descartado")
                        continue

                    reel_metrics['likes'] = parse_number(likes_text)
                    reel_metrics['comments'] = parse_number(comments_text)
                except Exception as e:
                    logger.debug(f"[Reel {index}] Hover fallido: {e}")
                    continue  # ⛔ Hover fallido → no sirve

                # Confirmar que TODAS las métricas existen (tu requisito)
                if (reel_metrics['views'] == 0 and
                    reel_metrics['likes'] == 0 and
                    reel_metrics['comments'] == 0):
                    logger.debug(f"[Reel {index}] Todas métricas vacías, descartado")
                    continue

                metrics['reel_data'].append(reel_metrics)
                metrics['total_views'] += reel_metrics['views']
                metrics['total_likes'] += reel_metrics['likes']
                metrics['total_comments'] += reel_metrics['comments']
                metrics['reel_count'] += 1

                logger.info(
                    f"[Reel {index}] Views: {reel_metrics['views']}, Likes: {reel_metrics['likes']}, Comments: {reel_metrics['comments']}"
                )
                # Pausa corta entre reels (equiv. a 0.4-0.6s)
                sleep_jitter(mean=0.5, jitter_pct=0.2)
                collected += 1

            except Exception as e:
                logger.warning(f"[Reel {index}] Error inesperado: {e}")
                continue

    except TimeoutException:
        logger.warning("Timeout esperando carga de reels")
    except Exception as e:
        logger.error(f"Error general extrayendo métricas: {e}")

    logger.info(f"Métricas finales: {metrics}")
    return metrics
