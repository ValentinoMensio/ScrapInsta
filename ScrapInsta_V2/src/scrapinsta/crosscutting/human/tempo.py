from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class HumanTempoConfig:
    """
    Configuración del ritmo humano.
    - base_apm: acciones por minuto “objetivo”.
    - apm_jitter: variación relativa del APM en cada acción (0.3 => ±30%).
    - long_pause_every: cada cuántas acciones insertar una pausa larga.
    - long_pause_range: rango de la pausa larga (segundos).
    """
    base_apm: int = 24  # Optimizado: aumentado de 18 a 24 (~25% más rápido, aún humano)
    apm_jitter: float = 0.35
    long_pause_every: int = 20
    long_pause_range: tuple[float, float] = (6.0, 12.0)

    # Semilla opcional para reproducibilidad por sesión/cuenta
    seed: int | None = None


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
            log.debug("HumanScheduler: pausa larga de %.2fs tras %d acciones", extra, self._actions)
            delay += extra

        # Backoff humano explícito (si fue seteado por señales externas)
        delay += self._human_backoff

        # Jitter final (ligero) para evitar patrones
        delay *= (1.0 + self._rng.uniform(-0.2, 0.3))
        delay = max(0.1, min(delay, 15.0))  # cota superior por seguridad

        self._next_ts = time.monotonic() + delay

    def record_block(self, *, min_extra: float = 10.0, max_extra: float = 40.0) -> None:
        """
        Señal de “bloqueo/ratelimit suave” detectado: aumenta el backoff humano temporalmente.
        Útil cuando ves mensajes tipo “Please wait a few minutes”.
        """
        added = self._rng.uniform(min_extra, max_extra)
        self._human_backoff = min(120.0, self._human_backoff + added)
        log.warning("HumanScheduler: record_block -> backoff humano ahora %.2fs (+=%.2fs)", self._human_backoff, added)

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
            log.debug("HumanScheduler: record_success -> backoff %.2fs -> %.2fs", before, self._human_backoff)


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

