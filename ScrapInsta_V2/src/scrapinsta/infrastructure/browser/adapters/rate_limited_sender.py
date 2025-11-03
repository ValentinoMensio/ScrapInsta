from __future__ import annotations

import logging
import time
from typing import Optional

from scrapinsta.application.dto.messages import MessageRequest
from scrapinsta.crosscutting.rate_limit import SlidingWindowRateLimiter
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
        max_wait_s: float = 120.0,
    ) -> None:
        self._inner = inner
        self._limiter = limiter
        self._max_wait = float(max_wait_s)

    def send_message(self, req: MessageRequest, text: str) -> bool:
        self._wait_for_slot()
        try:
            ok = self._inner.send_message(req, text)
            self._limiter.record_event()
            return ok
        except DMTransientUIBlock:
            dur = self._limiter.apply_cooldown()
            logger.warning("[rate_limit] DMTransientUIBlock -> cooldown %.0fs", dur)
            raise

    def send_direct_message(self, username: str, text: str) -> bool:
        self._wait_for_slot()
        try:
            ok = self._inner.send_direct_message(username, text)
            self._limiter.record_event()
            return ok
        except DMTransientUIBlock:
            dur = self._limiter.apply_cooldown()
            logger.warning("[rate_limit] DMTransientUIBlock -> cooldown %.0fs", dur)
            raise

    def _wait_for_slot(self) -> None:
        start = time.time()
        while not self._limiter.allow_now():
            wait = self._limiter.next_available_in()
            if wait <= 0.0:
                break
            if (time.time() - start + wait) > self._max_wait:
                # esperar un máximo y seguir; upstream puede reintentar si falla
                logger.info("[rate_limit] max_wait excedido, continuando")
                break
            time.sleep(min(wait, 5.0))


