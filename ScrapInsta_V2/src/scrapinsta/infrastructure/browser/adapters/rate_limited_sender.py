from __future__ import annotations

import logging
import time
from typing import Optional, Dict

from scrapinsta.application.dto.messages import MessageRequest
from scrapinsta.crosscutting.rate_limit import SlidingWindowRateLimiter, RateLimitConfig
from scrapinsta.domain.ports.message_port import (
    MessageSenderPort,
    DMTransientUIBlock,
)


logger = logging.getLogger(__name__)


class RateLimitedSender(MessageSenderPort):
    """
    Decorador que aplica limitación de tasa por cuenta y cooldown ante bloqueos suaves.
    """

    def __init__(
        self,
        inner: MessageSenderPort,
        limiter: SlidingWindowRateLimiter,
        *,
        daily_limiter: Optional[SlidingWindowRateLimiter] = None,
        per_target_cfg: Optional[RateLimitConfig] = None,
        max_wait_s: float = 120.0,
    ) -> None:
        self._inner = inner
        self._limiter = limiter
        self._daily_limiter = daily_limiter
        self._per_target_cfg = per_target_cfg
        self._per_target: Dict[str, SlidingWindowRateLimiter] = {}
        self._max_wait = float(max_wait_s)

    def send_message(self, req: MessageRequest, text: str) -> bool:
        target = (req.target_username or "").strip().lower()
        self._wait_for_slot(target)
        try:
            ok = self._inner.send_message(req, text)
            self._limiter.record_event()
            if self._daily_limiter:
                self._daily_limiter.record_event()
            if target and self._per_target_cfg:
                self._get_target_limiter(target).record_event()
            return ok
        except DMTransientUIBlock:
            dur = self._limiter.apply_cooldown()
            logger.warning("[rate_limit] DMTransientUIBlock -> cooldown %.0fs", dur)
            if target and self._per_target_cfg:
                self._get_target_limiter(target).apply_cooldown()
            raise

    def send_direct_message(self, username: str, text: str) -> bool:
        target = (username or "").strip().lower()
        self._wait_for_slot(target)
        try:
            ok = self._inner.send_direct_message(username, text)
            self._limiter.record_event()
            if self._daily_limiter:
                self._daily_limiter.record_event()
            if target and self._per_target_cfg:
                self._get_target_limiter(target).record_event()
            return ok
        except DMTransientUIBlock:
            dur = self._limiter.apply_cooldown()
            logger.warning("[rate_limit] DMTransientUIBlock -> cooldown %.0fs", dur)
            if target and self._per_target_cfg:
                self._get_target_limiter(target).apply_cooldown()
            raise

    def _wait_for_slot(self, target: Optional[str]) -> None:
        start = time.time()
        while True:
            waits = []
            if not self._limiter.allow_now():
                waits.append(self._limiter.next_available_in())
            if self._daily_limiter and not self._daily_limiter.allow_now():
                waits.append(self._daily_limiter.next_available_in())
            if target and self._per_target_cfg:
                tlim = self._get_target_limiter(target)
                if not tlim.allow_now():
                    waits.append(tlim.next_available_in())
            if not waits:
                break
            wait = max(waits) if waits else 0.0
            if wait <= 0.0:
                break
            if (time.time() - start + wait) > self._max_wait:
                # esperar un máximo y seguir; upstream puede reintentar si falla
                logger.info("[rate_limit] max_wait excedido, continuando")
                break
            time.sleep(min(wait, 5.0))

    def _get_target_limiter(self, target: str) -> SlidingWindowRateLimiter:
        key = target.strip().lower()
        limiter = self._per_target.get(key)
        if limiter is None:
            cfg = self._per_target_cfg
            if cfg is None:
                raise ValueError("per_target_cfg no configurado")
            limiter = SlidingWindowRateLimiter(cfg, seed=hash(key) & 0xFFFFFFFF)
            self._per_target[key] = limiter
        return limiter


