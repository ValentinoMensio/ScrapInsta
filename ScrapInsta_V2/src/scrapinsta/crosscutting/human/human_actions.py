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
    min_pause: float = 0.18,
    max_pause: float = 0.38,
) -> None:
    """
    Hover con overshoot aleatorio y micro-pausas.
    - scheduler.wait_turn() regula el ritmo antes del gesto.
    - pausas internas con sleep_jitter para romper patrones exactos.
    """
    try:
        if scheduler:
            scheduler.wait_turn()

        actions = ActionChains(driver)

        # Overshoot inicial con offsets suaves y aleatorios
        off_x = random.randint(3, 14)
        off_y = random.randint(3, 14)

        actions.move_to_element_with_offset(el, off_x, off_y)
        actions.pause(random.uniform(min_pause * 0.4, max_pause * 0.6))

        # Corrección hacia el centro
        actions.move_to_element(el)
        actions.pause(random.uniform(min_pause * 0.6, max_pause))
        actions.perform()

        # Micro-pausa final para dar tiempo a UI (tooltips/counters)
        tempo.sleep_jitter(random.uniform(0.12, 0.3), 0.5)

    except Exception as e:
        log.debug("hover_element_failed_non_fatal", error=str(e))


def human_scroll(
    driver: WebDriver,
    *,
    total_px: int,
    duration: float = 1.2,
    min_step_px: int = 90,
    max_step_px: int = 160,
    scheduler: Optional[HumanScheduler] = None,
    occasional_back_scroll: bool = True,
) -> None:
    """
    Scroll fraccionado con aceleración y jitter entre pasos.
    - Pasos con tamaño variable (min_step_px..max_step_px).
    - Aceleración tipo ease-in/out para simular arrastre humano.
    - Ocasionalmente hace un “micro back-scroll” para naturalidad visual.
    """
    if scheduler:
        scheduler.wait_turn()

    steps = max(1, int(total_px / max(1, (min_step_px + max_step_px) // 2)))
    if steps <= 2:
        steps = 3  # garantizar curva

    for i in range(steps):
        # Curva de aceleración tipo S: ease-in/out
        t = i / max(1, (steps - 1))
        accel = 3 * t**2 - 2 * t**3  # polinomio suave [0..1]

        step = random.randint(min_step_px, max_step_px)
        delta = int(step * (0.6 + 0.8 * accel))  # escala con la aceleración

        driver.execute_script("window.scrollBy(0, arguments[0]);", delta)

        # Pausa entre pasos (subdividir duration con jitter)
        per_step = max(0.05, duration / max(1, steps))
        tempo.sleep_jitter(per_step, 0.5)

        # De vez en cuando, micro “back-scroll” (1 de cada ~7 pasos)
        if occasional_back_scroll and i > 0 and random.random() < (1.0 / 7.0):
            back = random.randint(8, 24)
            driver.execute_script("window.scrollBy(0, arguments[0]);", -back)
            tempo.sleep_jitter(0.05, 0.6)
