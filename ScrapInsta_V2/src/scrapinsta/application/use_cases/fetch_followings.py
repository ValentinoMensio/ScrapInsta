from __future__ import annotations

import time
from typing import Optional, Iterable, Any

# DTOs de transporte
from scrapinsta.application.dto.followings import (
    FetchFollowingsRequest,
    FetchFollowingsResponse,
)

# Modelos de dominio
from scrapinsta.domain.models.profile_models import (
    Username,
    Following,
)

# Puertos del dominio
from scrapinsta.domain.ports.browser_port import (
    BrowserPort,
    BrowserPortError,
    BrowserNavigationError,
    BrowserDOMError,
    BrowserRateLimitError,
)
from scrapinsta.domain.ports.followings_repo import (
    FollowingsRepo,
    FollowingsPersistenceError,
    FollowingsValidationError,
)

from scrapinsta.crosscutting.logging_config import get_logger


class FetchFollowingsUseCase:
    """
    Caso de uso: obtiene los followings de un perfil y los persiste idempotentemente.

    Flujo:
        1. Normaliza y valida el owner como VO (Username).
        2. Usa BrowserPort.fetch_followings(owner, limit) → Iterable[Username].
        3. Crea entidades de dominio (Following) y aplica dedup/clip.
        4. Persiste con FollowingsRepo.save_for_owner(owner, followings).
        5. Devuelve un DTO con los followings y cantidad de nuevos guardados.
    """

    def __init__(
        self,
        browser: BrowserPort,
        repo: FollowingsRepo,
        logger: Optional[Any] = None,
    ) -> None:
        self._browser = browser
        self._repo = repo
        self._log = logger or get_logger("fetch_followings")

    def __call__(self, req: FetchFollowingsRequest) -> FetchFollowingsResponse:
        owner = Username(value=req.username)
        limit = req.max_followings

        if limit is not None and limit <= 0:
            self._log.info("fetch_followings_invalid_limit", owner=owner.value, limit=limit)
            return FetchFollowingsResponse(owner=owner.value, followings=[], new_saved=0)

        try:
            start_time = time.time()
            targets = list(self._browser.fetch_followings(owner, limit))
            scraping_duration = time.time() - start_time

            if not isinstance(targets, list):
                self._log.warning("fetch_followings_invalid_browser_return", owner=owner.value, got_type=type(targets).__name__)
                return FetchFollowingsResponse(owner=owner.value, followings=[], new_saved=0)

            for t in targets:
                if not isinstance(t, Username):
                    self._log.error(
                        "fetch_followings_invalid_target_type",
                        owner=owner.value,
                        expected="Username",
                        got=type(t).__name__,
                    )
                    return FetchFollowingsResponse(owner=owner.value, followings=[], new_saved=0)

            if not targets:
                self._log.info("fetch_followings_empty", owner=owner.value)
                return FetchFollowingsResponse(owner=owner.value, followings=[], new_saved=0)

            self._log.info(
                "fetch_followings_scrape_done",
                owner=owner.value,
                count=len(targets),
                duration_s=round(scraping_duration, 2),
            )

            rels = []
            seen = set()
            for t in targets:
                if limit and len(rels) >= limit:
                    break
                key = (owner.value, t.value)
                if key not in seen:
                    rels.append(Following(owner=owner, target=t))
                    seen.add(key)

            inserted = self._repo.save_for_owner(owner, rels)

            self._log.info("fetch_followings_done", owner=owner.value, fetched=len(rels), inserted_new=inserted)

            source = getattr(self._browser, "source", "selenium")
            
            return FetchFollowingsResponse(
                owner=owner.value,
                followings=[f.target.value for f in rels],
                new_saved=inserted,
                source=source,
            )

        except (BrowserNavigationError, BrowserDOMError, BrowserRateLimitError) as e:
            self._log.error("fetch_followings_scrape_error", owner=owner.value, limit=limit, error=str(e))
            raise

        except (FollowingsValidationError, FollowingsPersistenceError) as e:
            self._log.error("fetch_followings_persistence_error", owner=owner.value, error=str(e))
            raise

        except BrowserPortError as e:
            self._log.error("fetch_followings_browser_error", owner=owner.value, error=str(e))
            raise

    def run(self, username_origin: str, max_followings: int = 100) -> FetchFollowingsResponse:
        req = FetchFollowingsRequest(username=username_origin, max_followings=max_followings)
        return self(req)

    def execute(self, **kwargs) -> FetchFollowingsResponse:
        return self(FetchFollowingsRequest(**kwargs))
