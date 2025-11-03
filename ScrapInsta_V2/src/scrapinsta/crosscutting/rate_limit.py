from __future__ import annotations

import time
import random
from dataclasses import dataclass
from typing import Deque, Optional
from collections import deque


@dataclass
class RateLimitConfig:
    """
    Configuración simple de límite por ventana deslizante y cooldown.
    - window_seconds: tamaño de ventana para contar eventos (p.ej. 3600 para 1h)
    - max_events: máximo de eventos permitidos por ventana
    - cooldown_range: rango de cooldown en segundos a aplicar cuando se gatilla bloqueo suave
    """
    window_seconds: int
    max_events: int
    cooldown_range: tuple[int, int] = (600, 2400)  # 10–40 min por defecto


class SlidingWindowRateLimiter:
    """
    Limitador de tasa por ventana deslizante en memoria.
    - Thread-safe suficiente para un único proceso/worker por cuenta.
    - Mantiene timestamps de los últimos eventos dentro de la ventana.
    - Soporta cooldown explícito (hasta epoch en segundos).
    """

    def __init__(self, cfg: RateLimitConfig, *, seed: Optional[int] = None) -> None:
        self._cfg = cfg
        self._events: Deque[float] = deque()
        self._cooldown_until: float = 0.0
        self._rng = random.Random(seed if seed is not None else time.time_ns())

    # -------------------- API --------------------
    def allow_now(self) -> bool:
        """Devuelve True si se puede ejecutar ahora mismo el evento."""
        now = time.time()
        if now < self._cooldown_until:
            return False
        self._evict_old(now)
        return len(self._events) < self._cfg.max_events

    def record_event(self) -> None:
        """Registra un nuevo evento (asumir que fue permitido)."""
        now = time.time()
        self._evict_old(now)
        self._events.append(now)

    def next_available_in(self) -> float:
        """Segundos hasta el próximo slot disponible (0 si ya hay capacidad)."""
        now = time.time()
        if now < self._cooldown_until:
            return max(0.0, self._cooldown_until - now)
        self._evict_old(now)
        if len(self._events) < self._cfg.max_events:
            return 0.0
        oldest = self._events[0]
        return max(0.0, oldest + self._cfg.window_seconds - now)

    def apply_cooldown(self) -> float:
        """Aplica un cooldown aleatorio en el rango y devuelve su duración en segundos."""
        low, high = self._cfg.cooldown_range
        duration = float(self._rng.randint(int(low), int(high)))
        self._cooldown_until = time.time() + duration
        return duration

    # -------------------- Internals --------------------
    def _evict_old(self, now: float) -> None:
        boundary = now - self._cfg.window_seconds
        while self._events and self._events[0] < boundary:
            self._events.popleft()


