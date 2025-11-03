from __future__ import annotations
import logging
from typing import Optional, Dict

from scrapinsta.config.settings import Settings

# Puertos
from scrapinsta.domain.ports.browser_port import BrowserPort
from scrapinsta.domain.ports.profile_repo import ProfileRepository
from scrapinsta.domain.ports.followings_repo import FollowingsRepo
from scrapinsta.domain.ports.message_port import MessageSenderPort, MessageComposerPort

# Adapters (infra)
from scrapinsta.infrastructure.browser.core.driver_provider import DriverProvider
from scrapinsta.infrastructure.browser.adapters.selenium_browser_adapter import SeleniumBrowserAdapter
from scrapinsta.infrastructure.auth.session_service import SessionService
from scrapinsta.infrastructure.auth.cookie_store import load_cookies
from scrapinsta.infrastructure.auth.session_probe import has_active_session_in_driver
from scrapinsta.infrastructure.db.profile_repo_sql import ProfileRepoSQL
from scrapinsta.infrastructure.db.connection_provider import ConnectionProvider
from scrapinsta.infrastructure.db.followings_repo_sql import FollowingsRepoSQL
from scrapinsta.infrastructure.browser.adapters.selenium_message_sender import SeleniumMessageSender
from scrapinsta.infrastructure.browser.adapters.rate_limited_sender import RateLimitedSender
from scrapinsta.infrastructure.ai.chatgpt_openai import OpenAIMessageComposer
from scrapinsta.infrastructure.db.connection_provider import make_mysql_conn_factory
from scrapinsta.crosscutting.rate_limit import SlidingWindowRateLimiter, RateLimitConfig

# Use cases
from scrapinsta.application.use_cases.analyze_profile import AnalyzeProfileUseCase
from scrapinsta.application.use_cases.fetch_followings import FetchFollowingsUseCase
from scrapinsta.application.use_cases.send_message import SendMessageUseCase

logger = logging.getLogger(__name__)


class UseCaseFactory:
    def create_analyze_profile(self) -> AnalyzeProfileUseCase: ...
    def create_fetch_followings(self) -> FetchFollowingsUseCase: ...
    def create_send_message(self) -> SendMessageUseCase: ...
    def close(self) -> None: ...


class FactoryImpl(UseCaseFactory):
    def __init__(self, account_username: str, settings: Optional[Settings] = None) -> None:
        self._account = account_username.strip().lower()
        self._settings = settings or Settings()

        self._password: Optional[str] = self._settings.get_account_password(self._account)

        self._driver_manager: Optional[DriverProvider] = None
        self._browser: Optional[BrowserPort] = None
        self._profile_repo: Optional[ProfileRepository] = None
        self._followings_repo: Optional[FollowingsRepo] = None
        self._sender: Optional[MessageSenderPort] = None
        self._composer: Optional[MessageComposerPort] = None

    def _ensure_driver(self) -> DriverProvider:
        if self._driver_manager is None:
            proxy = self._settings.get_account_proxy(self._account)
            self._driver_manager = DriverProvider(
                account_username=self._account,
                proxy=proxy,
                headless=self._settings.headless,
                disable_images=True,
                retry_attempts=self._settings.retry_max_retries,
                retry_initial_delay=self._settings.retry_base_delay,
            )
        return self._driver_manager

    @property
    def browser(self) -> BrowserPort:
        if self._browser is None:
            dm = self._ensure_driver()
            driver = dm.initialize_driver()

            if not has_active_session_in_driver(driver, base_url="https://www.instagram.com/"):
                try:
                    load_cookies(
                        driver,
                        self._account,
                        base_url="https://www.instagram.com/",
                        require_sessionid=False,
                    )
                except Exception:
                    logger.debug("[%s] No se pudieron cargar cookies persistidas", self._account)

                if not has_active_session_in_driver(driver, base_url="https://www.instagram.com/"):
                    session = SessionService(
                        driver=driver,
                        username=self._account,
                        password=self._password,
                        two_factor_code_provider=None,
                    )
                    session.ensure_session()

            self._browser = SeleniumBrowserAdapter(
                driver=driver,
                base_url="https://www.instagram.com",
                account_username=self._account,
            )
        return self._browser

    @property
    def profile_repo(self) -> ProfileRepository:
        if self._profile_repo is None:
            cp = ConnectionProvider(self._settings.db_dsn)
            self._profile_repo = ProfileRepoSQL(cp)
        return self._profile_repo

    @property
    def followings_repo(self) -> FollowingsRepo:
        if self._followings_repo is None:
            factory = make_mysql_conn_factory(self._settings.db_dsn)
            self._followings_repo = FollowingsRepoSQL(conn_factory=factory)
        return self._followings_repo

    @property
    def sender(self) -> MessageSenderPort:
        if self._sender is None:
            dm = self._ensure_driver()
            driver = dm.initialize_driver()
            base_sender = SeleniumMessageSender(driver=driver)
            # Limitar 8–15 DMs por hora (aleatorio por arranque) y cooldown 10–40 min
            rng_key = hash(self._account) & 0xFFFFFFFF
            low, high = 8, 15
            per_hour = low + (rng_key % (high - low + 1))
            limiter = SlidingWindowRateLimiter(
                RateLimitConfig(window_seconds=3600, max_events=per_hour)
            )
            self._sender = RateLimitedSender(base_sender, limiter)
        return self._sender

    @property
    def composer(self) -> MessageComposerPort:
        if self._composer is None:
            self._composer = OpenAIMessageComposer(
                api_key=self._settings.openai_api_key,
                model=getattr(self._settings, "openai_model", "gpt-4o-mini"),
            )
        return self._composer

    def create_analyze_profile(self) -> AnalyzeProfileUseCase:
        return AnalyzeProfileUseCase(browser=self.browser, profile_repo=self.profile_repo)

    def create_fetch_followings(self) -> FetchFollowingsUseCase:
        return FetchFollowingsUseCase(browser=self.browser, repo=self.followings_repo)

    def create_send_message(self) -> SendMessageUseCase:
        return SendMessageUseCase(
            browser=self.browser,
            sender=self.sender,
            composer=self.composer,
            profile_repo=self.profile_repo,
        )

    def close(self) -> None:
        if self._driver_manager:
            try:
                self._driver_manager.cleanup()
            except Exception:
                logger.warning("[%s] Error cerrando driver", self._account, exc_info=True)
            self._driver_manager = None


_factory_cache: Dict[str, FactoryImpl] = {}


def get_factory(account_username: str, settings: Optional[Settings] = None) -> UseCaseFactory:
    account = account_username.strip().lower()
    if account not in _factory_cache:
        _factory_cache[account] = FactoryImpl(account, settings=settings)
    return _factory_cache[account]
