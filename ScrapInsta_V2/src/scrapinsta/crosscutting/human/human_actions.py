from __future__ import annotations

import random
from typing import Optional

from selenium.webdriver import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from . import tempo
from .tempo import HumanScheduler

from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("human_actions")


def hover_element_human(
    driver: WebDriver,
    el: WebElement,
    *,
    scheduler: Optional[HumanScheduler] = None,
    min_pause: float = 0.05,  # Reducido de 0.18 a 0.05
    max_pause: float = 0.12,  # Reducido de 0.38 a 0.12
) -> None:
    """
    Hover optimizado con micro-pausas mínimas.
    - scheduler.wait_turn() regula el ritmo antes del gesto.
    - pausas reducidas para scraping más rápido.
    """
    try:
        if scheduler:
            scheduler.wait_turn()

        actions = ActionChains(driver)

        # Overshoot mínimo
        off_x = random.randint(2, 8)
        off_y = random.randint(2, 8)

        actions.move_to_element_with_offset(el, off_x, off_y)
        actions.pause(random.uniform(min_pause, max_pause * 0.5))

        # Corrección hacia el centro
        actions.move_to_element(el)
        actions.pause(random.uniform(min_pause, max_pause))
        actions.perform()

        # Micro-pausa mínima para UI
        tempo.sleep_jitter(random.uniform(0.04, 0.1), 0.3)

    except Exception as e:
        log.debug("hover_element_failed_non_fatal", error=str(e))


def human_scroll(
    driver: WebDriver,
    *,
    total_px: int,
    duration: float = 0.4,  # Reducido de 1.2 a 0.4
    min_step_px: int = 150,  # Aumentado de 90 a 150 (menos pasos)
    max_step_px: int = 300,  # Aumentado de 160 a 300 (pasos más grandes)
    scheduler: Optional[HumanScheduler] = None,
    occasional_back_scroll: bool = False,  # Desactivado por defecto para velocidad
) -> None:
    """
    Scroll fraccionado optimizado para velocidad.
    - Pasos grandes para menos operaciones.
    - Pausas mínimas entre pasos.
    - Back-scroll desactivado por defecto.
    """
    if scheduler:
        scheduler.wait_turn()

    steps = max(1, int(total_px / max(1, (min_step_px + max_step_px) // 2)))
    if steps <= 1:
        steps = 2  # mínimo para variabilidad

    for i in range(steps):
        # Curva de aceleración simplificada
        t = i / max(1, (steps - 1))
        accel = 3 * t**2 - 2 * t**3

        step = random.randint(min_step_px, max_step_px)
        delta = int(step * (0.7 + 0.6 * accel))

        driver.execute_script("window.scrollBy(0, arguments[0]);", delta)

        # Pausa mínima entre pasos
        per_step = max(0.02, duration / max(1, steps))
        tempo.sleep_jitter(per_step, 0.3)

        # Back-scroll solo si está activado (1 de cada ~10 pasos)
        if occasional_back_scroll and i > 0 and random.random() < 0.1:
            back = random.randint(8, 20)
            driver.execute_script("window.scrollBy(0, arguments[0]);", -back)
            tempo.sleep_jitter(0.02, 0.3)
