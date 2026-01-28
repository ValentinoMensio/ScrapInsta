from __future__ import annotations

import math
import os
import random
import time
from dataclasses import dataclass

from scrapinsta.crosscutting.logging_config import get_logger

log = get_logger("human_tempo")


@dataclass
class HumanTempoConfig:
    """
    Configuración del ritmo humano.
    - base_apm: acciones por minuto "objetivo".
    - apm_jitter: variación relativa del APM en cada acción (0.3 => ±30%).
    - long_pause_every: cada cuántas acciones insertar una pausa larga.
    - long_pause_range: rango de la pausa larga (segundos).
    """
    base_apm: int = 45  # Optimizado: aumentado de 24 a 45 (~2x más rápido para scraping masivo)
    apm_jitter: float = 0.25  # Reducido de 0.35 a 0.25 para más consistencia
    long_pause_every: int = 50  # Aumentado de 20 a 50 (menos pausas largas)
    long_pause_range: tuple[float, float] = (2.0, 5.0)  # Reducido de 6-12 a 2-5

    # Semilla opcional para reproducibilidad por sesión/cuenta
    seed: int | None = None

    def __post_init__(self) -> None:
        env_base_apm = os.getenv("HUMAN_BASE_APM")
        if env_base_apm:
            try:
                self.base_apm = int(env_base_apm)
            except Exception:
                pass
        env_apm_jitter = os.getenv("HUMAN_APM_JITTER")
        if env_apm_jitter:
            try:
                self.apm_jitter = float(env_apm_jitter)
            except Exception:
                pass
        env_long_every = os.getenv("HUMAN_LONG_PAUSE_EVERY")
        if env_long_every:
            try:
                self.long_pause_every = int(env_long_every)
            except Exception:
                pass
        env_long_min = os.getenv("HUMAN_LONG_PAUSE_MIN")
        env_long_max = os.getenv("HUMAN_LONG_PAUSE_MAX")
        if env_long_min or env_long_max:
            try:
                min_v = float(env_long_min or self.long_pause_range[0])
                max_v = float(env_long_max or self.long_pause_range[1])
                self.long_pause_range = (min_v, max_v)
            except Exception:
                pass


class HumanScheduler:
    """
    Controla el ritmo humano entre acciones exitosas (NO maneja errores; para eso está retry.py).
    - Aplica jitter en el APM.
    - Inserta pausas largas cada N acciones.
    - Permite “backoff humano” explícito ante señales (ej. bloqueo suave de Instagram).
    """

    def __init__(self, cfg: HumanTempoConfig | None = None) -> None:
        self.cfg = cfg or HumanTempoConfig()
        self._rng = random.Random(self.cfg.seed if self.cfg.seed is not None else time.time_ns())
        self._actions = 0
        self._next_ts = time.monotonic()
        self._human_backoff: float = 0.0

    # ---------------------------
    # API pública
    # ---------------------------

    def wait_turn(self) -> None:
        """
        Espera hasta el próximo “turno humano” para ejecutar la acción.
        Llama a este método ANTES de cada acción visible (scroll, hover, click, etc.)
        """
        now = time.monotonic()
        if now < self._next_ts:
            time.sleep(self._next_ts - now)

        self._actions += 1

        # APM con jitter relativo
        apm = max(4.0, self.cfg.base_apm * (1.0 + self._rng.uniform(-self.cfg.apm_jitter, self.cfg.apm_jitter)))
        delay = 60.0 / apm

        # Pausas largas periódicas
        if self.cfg.long_pause_every > 0 and (self._actions % self.cfg.long_pause_every == 0):
            extra = self._rng.uniform(*self.cfg.long_pause_range)
            log.debug("human_pause_long", extra_s=round(extra, 2), actions=self._actions)
            delay += extra

        # Backoff humano explícito (si fue seteado por señales externas)
        delay += self._human_backoff

        # Jitter final (ligero) para evitar patrones
        delay *= (1.0 + self._rng.uniform(-0.2, 0.3))
        min_delay = float(os.getenv("HUMAN_MIN_DELAY", "0.1"))
        max_delay = float(os.getenv("HUMAN_MAX_DELAY", "15.0"))
        delay = max(min_delay, min(delay, max_delay))  # cota superior por seguridad

        self._next_ts = time.monotonic() + delay

    def record_block(self, *, min_extra: float = 10.0, max_extra: float = 40.0) -> None:
        """
        Señal de “bloqueo/ratelimit suave” detectado: aumenta el backoff humano temporalmente.
        Útil cuando ves mensajes tipo “Please wait a few minutes”.
        """
        added = self._rng.uniform(min_extra, max_extra)
        self._human_backoff = min(120.0, self._human_backoff + added)
        log.warning("human_backoff_increased", backoff_s=round(self._human_backoff, 2), added_s=round(added, 2))

    def record_success(self, *, decay: float = 0.5) -> None:
        """
        Disminuye progresivamente el backoff humano tras acciones exitosas.
        decay: proporción de reducción (0.5 => se reduce ~50% cada éxito).
        """
        if self._human_backoff > 0.0:
            before = self._human_backoff
            self._human_backoff *= decay
            if self._human_backoff < 2.0:
                self._human_backoff = 0.0
            log.debug("human_backoff_decayed", before_s=round(before, 2), after_s=round(self._human_backoff, 2), decay=decay)


def sleep_jitter(base: float, jitter: float = 0.35, mode: str = "uniform", *, max_factor: float = 3.0) -> None:
    """
    Pausa con jitter “humano”.
    - base: segundos base.
    - jitter: intensidad del jitter.
    - mode: "uniform" (±jitter relativo) | "lognormal" (sesgo a derecha).
    - max_factor: cota superior para evitar sleeps excesivos (base*max_factor).
    """
    base = max(0.05, float(base))
    if mode == "lognormal":
        # Mantener media cerca de 'base' y sigma ~jitter razonable
        mu = math.log(base + 1e-9)
        sigma = max(0.05, min(1.0, jitter))
        delay = random.lognormvariate(mu, sigma)
    else:
        delay = base * (1.0 + random.uniform(-jitter, jitter))

    delay = max(0.02, min(delay, base * max_factor))
    time.sleep(delay)

