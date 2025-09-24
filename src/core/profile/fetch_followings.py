# src/core/profile/utils/fetch_followings.py

import logging
from typing import List, Set

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


from db.repositories import save_followings

# Helpers “humanos”
from core.utils.humanize_helpers import (
    HumanScheduler,
    sleep_jitter,
    hover_element_human,
    click_careful,
)

logger = logging.getLogger(__name__)

FOLLOWING_DIALOG_XPATH = "//div[@role='dialog']"

FOLLOWING_BUTTON_XPATH = "//a[contains(@href, '/following')]"

# Ritmo humano (~18 acciones/min ≈ 1 acción cada ~3.3s con jitter)
SCHED = HumanScheduler(actions_per_min=18, jitter_pct=0.25, min_interval=0.9)


def fetch_followings(driver, username_origin: str, max_followings: int = 100, max_retries: int = 3) -> List[str]:
    for attempt in range(max_retries):
        try:
            logger.info(f"Intento {attempt + 1} de {max_retries} para obtener followings de {username_origin}")

            # Navegar al perfil con un leve ritmo humano
            SCHED.wait_turn()
            driver.get(f"https://www.instagram.com/{username_origin}/")
            sleep_jitter(1.2, 0.4)  # pequeña pausa tras la carga inicial

            if not open_following_list(driver):
                logger.warning("No se pudo abrir el modal de 'Following'")
                _retry_backoff(attempt, max_retries)
                continue

            usernames = extract_followings_from_dialog(driver, max_followings)
            logger.info(f"Total recolectado: {len(usernames)}")

            if usernames:
                save_followings(username_origin, usernames)
                return usernames

            # Si no recolectó nada, reintentar
            _retry_backoff(attempt, max_retries)

        except Exception as e:
            logger.error(f"Error general en el intento {attempt + 1}: {e}")
            _retry_backoff(attempt, max_retries, is_error=True)
            if attempt >= max_retries - 1:
                # último intento fallido
                raise

    return []


def open_following_list(driver) -> bool:
    """Abre el modal de 'Following' con click cuidadoso y pequeñas pausas humanas."""
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, FOLLOWING_BUTTON_XPATH))
        )
        # Hover breve para “activar” tooltips/estados y luego click con pausa
        SCHED.wait_turn()
        hover_element_human(driver, btn, duration=0.35)
        click_careful(driver, btn)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, FOLLOWING_DIALOG_XPATH))
        )
        sleep_jitter(0.4, 0.35)  # dar tiempo a que pinte la lista
        return True
    except TimeoutException:
        logger.error("Timeout esperando el modal de 'Following'")
        return False
    except Exception as e:
        logger.error(f"Error al abrir la lista de 'Following': {e}")
        return False


def extract_followings_from_dialog(driver, max_followings: int) -> List[str]:
    """Extrae usernames del modal 'Following' sin scrollear si ya alcanza con lo visible."""
    from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

    usernames: List[str] = []
    seen: Set[str] = set()
    last_count = 0
    same_count_repeats = 0
    scroll_attempts = 0

    # Asegurar modal presente
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, FOLLOWING_DIALOG_XPATH))
    )

    def read_usernames_js() -> List[str]:
        return driver.execute_script("""
            const dlg = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (!dlg) return [];
            const anchors = dlg.querySelectorAll("a[href*='/']");
            const names = [];
            for (const a of anchors) {
              const t = (a.textContent || "").trim();
              if (t && t.length <= 30 && !t.includes(" ") && !t.toLowerCase().includes("explore")) {
                names.push(t);
              }
            }
            return [...new Set(names)];
        """, FOLLOWING_DIALOG_XPATH) or []

    initial_names = read_usernames_js()
    for name in initial_names:
        if name not in seen:
            usernames.append(name)
            seen.add(name)
            if len(usernames) >= max_followings:
                break

    if len(usernames) >= max_followings:
        logger.info("Se alcanzó el cupo solo con la vista inicial. Sin scroll.")
        return usernames[:max_followings]

    while len(usernames) < max_followings and same_count_repeats < 5:
        try:
            # Releer visibles (DOM puede cambiar)
            current_names = read_usernames_js()
            for name in current_names:
                if name not in seen:
                    usernames.append(name)
                    seen.add(name)
                    if len(usernames) >= max_followings:
                        break

            if len(usernames) >= max_followings:
                break

            SCHED.wait_turn()
            _human_scroll_dialog_fresh(driver, step_px=145, steps=6)
            sleep_jitter(mean=0.45, jitter_pct=0.35)
            scroll_attempts += 1

            if len(usernames) == last_count:
                same_count_repeats += 1
            else:
                last_count = len(usernames)
                same_count_repeats = 0

        except StaleElementReferenceException:
            logger.debug("Dialog stale; re-localizando modal…")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, FOLLOWING_DIALOG_XPATH))
            )
            sleep_jitter(0.5, 0.4)
            continue
        except TimeoutException as e:
            logger.warning(f"Timeout durante el scroll [{scroll_attempts}]: {e}")
            sleep_jitter(0.9, 0.35)
            continue
        except Exception as e:
            logger.warning(f"Error durante el scroll [{scroll_attempts}]: {e}")
            sleep_jitter(0.9, 0.35)
            continue

    logger.info(f"Scrolls realizados: {scroll_attempts}")
    return usernames[:max_followings]



def _human_scroll_dialog_fresh(driver, *, step_px: int = 120, steps: int = 5) -> None:
    """Resuelve el contenedor scrolleable en cada paso y scrollea con micro-pausas."""
    for _ in range(max(1, steps)):
        driver.execute_script("""
            const dlg = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (!dlg) return;
            let target = null;
            const nodes = dlg.querySelectorAll('div');
            for (const n of nodes) {
              if (n.scrollHeight > n.clientHeight + 8) { target = n; break; }
            }
            if (!target) target = dlg; // fallback
            target.scrollTop = Math.min(target.scrollTop + arguments[1], target.scrollHeight);
        """, FOLLOWING_DIALOG_XPATH, step_px)
        sleep_jitter(0.08, 0.5)



def _retry_backoff(attempt: int, max_retries: int, *, is_error: bool = False) -> None:
    """Backoff suave entre intentos, usando el scheduler si es error repetido."""
    # Ligero incremento con el número de intento
    base = 1.2 + attempt * 0.6
    if is_error and attempt >= 1:
        # si fue error, damos un respiro mayor y respetamos ritmo
        SCHED.wait_turn()
        sleep_jitter(base + 1.0, 0.35)
    else:
        sleep_jitter(base, 0.35)
