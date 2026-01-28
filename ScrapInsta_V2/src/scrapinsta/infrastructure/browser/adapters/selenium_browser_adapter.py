from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple, List, Sequence, Set

from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
    Username,
)
from scrapinsta.crosscutting.human.tempo import HumanScheduler, sleep_jitter
from scrapinsta.crosscutting.retry import retry, RetryError
from scrapinsta.domain.ports.browser_port import (
    BrowserPort,
    BrowserPortError,
    BrowserNavigationError,
    BrowserDOMError,
    BrowserRateLimitError,
)
from scrapinsta.crosscutting.metrics import (
    browser_actions_total,
    browser_action_duration_seconds,
)

from scrapinsta.infrastructure.browser.pages import profile_page, reels_page

logger = logging.getLogger(__name__)

FOLLOWING_DIALOG_XPATH = "//div[@role='dialog']"
FOLLOWING_BUTTON_XPATH = "//a[contains(@href, '/following')]"


class SeleniumBrowserAdapter(BrowserPort):
    """
    Adapter de Selenium para nuestro puerto de navegador.
    - `get_followings`: abre el modal, scrollea lo justo y extrae usernames.
    - El snapshot y los reels viven en helpers dedicados (profile_page / reels_page).
    """

    def __init__(
        self,
        driver,
        *,
        scheduler: Optional[HumanScheduler] = None,
        rubro_detector: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
        read_usernames_js: Optional[str] = None,
        base_url: str = "https://www.instagram.com",
        wait_timeout: float = 10.0,
        small_pause: float = 0.30,
        small_jitter: float = 0.30,
        max_scrolls_without_growth: int = 5,
        **_: object,
    ) -> None:
        self.driver = driver
        self._sched = scheduler or HumanScheduler()
        self._rubro_detector = rubro_detector


        self._read_usernames_js = read_usernames_js or self._default_read_usernames_js()
        self._base_url = base_url.rstrip("/")
        self._wait_timeout = float(wait_timeout)
        self._small_pause = float(small_pause)
        self._small_jitter = float(small_jitter)
        self._max_scrolls_no_growth = int(max_scrolls_without_growth)
        self._scroll_step = 145 

        self._open_profile: Callable[[str], None] = self.__open_profile_default
        self._open_following_modal: Callable[[], None] = self.__open_following_modal_default
        self._scroll_following_modal_once: Callable[[], None] = self.__scroll_following_modal_once_default
        self._sleep_human: Callable[[], None] = self.__sleep_human_default

    # --------------------------------------------------------------------- utils

    def _go_profile(self, username: str) -> None:
        url = f"{self._base_url}/{username.strip().lstrip('@')}/"
        try:
            logger.debug("[browser] GET %s", url)
            self._sched.wait_turn()
            self.driver.get(url)
            try:
                profile_page.close_instagram_login_popup(self.driver, timeout=5, scheduler=self._sched)
            except Exception:
                pass
            sleep_jitter(1.0, 0.35)
        except (TimeoutException, WebDriverException) as e:
            raise BrowserNavigationError(f"navigation to profile failed: {e}") from e

    def _go_reels(self, username: str) -> None:
        """Navega a https://www.instagram.com/<username>/reels/ (con fallback por click en tab)."""
        self._go_profile(username)

        u = username.strip().lstrip("@").lower()
        reels_url = f"{self._base_url}/{u}/reels/"

        try:
            self.driver.get(reels_url)
            WebDriverWait(self.driver, self._wait_timeout).until(EC.url_contains("/reels"))
        except Exception:
            try:
                tab = WebDriverWait(self.driver, self._wait_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href$='/reels/']"))
                )
                self.driver.execute_script("arguments[0].click();", tab)
                WebDriverWait(self.driver, self._wait_timeout).until(EC.url_contains("/reels"))
            except Exception as e:
                raise BrowserNavigationError(f"No se pudo abrir la pestaña Reels de {username}: {e}") from e

    # -------------------------------------------------------------- BrowserPort

    def get_followings(self, username: str, max_followings: int) -> Sequence[str]:
        """
        Abre el modal de "Following", scrollea lo mínimo y extrae usernames.
        Devuelve una lista deduplicada hasta `max_followings`.
        """
        username = (username or "").strip().lstrip("@").lower()
        if not username:
            return []

        account = getattr(self.driver, "account_id", "unknown")
        start = time.time()
        browser_actions_total.labels(action="get_followings", account=account).inc()
        
        try:
            self._open_profile(username)
            self._sleep_human()

            # Caso esperado: perfil privado (y la cuenta no lo sigue) => Instagram no permite abrir "siguiendo".
            # En vez de fallar por timeout del modal, devolvemos lista vacía (resultado válido).
            try:
                if profile_page.is_profile_private(self.driver):
                    logger.info("fetch_followings_skipped_private_profile owner=%s", username)
                    duration = time.time() - start
                    browser_action_duration_seconds.labels(action="get_followings", account=account).observe(duration)
                    return []
            except Exception:
                # best-effort: si no podemos determinarlo, seguimos con el flujo normal
                pass

            self._open_following_modal()

            unique: List[str] = []
            seen: Set[str] = set()
            no_growth = 0
            scrolls_done = 0
            last_gain = 0

            self._sleep_human()

            while len(unique) < max_followings:
                try:
                    batch = self._read_visible_usernames()
                except RetryError as e:
                    # Importante: no ocultar la causa real. Si el retry se agotó por caída del driver
                    # (invalid session / devtools disconnected), propagamos el mensaje para que el
                    # worker lo marque como retryable y el router reencole.
                    last = getattr(e, "last_error", None) or getattr(e, "__cause__", None)
                    msg = (str(last) if last else "").lower()
                    if (
                        "invalid session id" in msg
                        or "not connected to devtools" in msg
                        or "session deleted as the browser has closed the connection" in msg
                    ):
                        raise BrowserDOMError(f"driver dead: {last}") from e
                    raise BrowserDOMError("usernames list stale") from e
                except WebDriverException as e:
                    msg = (str(e) or "").lower()
                    if "temporarily blocked" in msg or "try again later" in msg:
                        raise BrowserRateLimitError("temporarily blocked by Instagram") from e
                    raise BrowserDOMError(str(e)) from e

                before = len(unique)
                for s in batch:
                    if s in seen:
                        continue
                    unique.append(s)
                    seen.add(s)
                    if len(unique) >= max_followings:
                        break

                if len(unique) >= max_followings:
                    break

                if len(unique) == before:
                    no_growth += 1
                    if no_growth >= self._max_scrolls_no_growth:
                        break
                else:
                    no_growth = 0
                    last_gain = len(unique) - before

                remaining = max(0, max_followings - len(unique))
                self._scroll_step = 145 if remaining < 20 else 400

                try:
                    self._scroll_following_modal_once()
                finally:
                    self._sleep_human()
                    scrolls_done += 1

                avg_gain = last_gain if last_gain > 0 else 10
                import math
                max_reasonable_scrolls = math.ceil(remaining / max(1, avg_gain))
                if scrolls_done >= max_reasonable_scrolls and remaining > 0:
                    break

            duration = time.time() - start
            browser_action_duration_seconds.labels(action="get_followings", account=account).observe(duration)
            return unique
        except Exception:
            duration = time.time() - start
            browser_action_duration_seconds.labels(action="get_followings", account=account).observe(duration)
            raise

    def get_profile_snapshot(self, username: str) -> ProfileSnapshot:
        account = getattr(self.driver, "account_id", "unknown")
        start = time.time()
        browser_actions_total.labels(action="get_profile_snapshot", account=account).inc()
        
        try:
            self._go_profile(username)
            result = profile_page.get_profile_snapshot(self.driver, username, wait_seconds=int(self._wait_timeout))
            duration = time.time() - start
            browser_action_duration_seconds.labels(action="get_profile_snapshot", account=account).observe(duration)
            return result
        except (NoSuchElementException, StaleElementReferenceException, TimeoutException) as e:
            raise BrowserDOMError(f"snapshot scrape failed: {e}") from e
        except BrowserPortError:
            raise
        except Exception as e:
            raise BrowserPortError(f"snapshot unexpected error: {e}") from e

    def get_reel_metrics(
        self,
        username: str,
        *,
        max_reels: int = 5,
        fast_mode: bool = True,
    ) -> Tuple[List[ReelMetrics], BasicStats]:
        account = getattr(self.driver, "account_id", "unknown")
        start = time.time()
        browser_actions_total.labels(action="get_reel_metrics", account=account).inc()
        
        try:
            self._go_reels(username)
            rows = reels_page.extract_reel_metrics_list(
                self.driver,
                limit=max_reels,
                scheduler=self._sched,
                fast_mode=fast_mode,
            )
            reels: List[ReelMetrics] = []
            for r in rows:
                try:
                    reels.append(
                        ReelMetrics(
                            url=r.get("url", ""),
                            code=r.get("code", "") or "",
                            views=int(r.get("views") or 0) if r.get("views") is not None else None,
                            likes=int(r.get("likes") or 0) if r.get("likes") is not None else None,
                            comments=int(r.get("comments") or 0) if r.get("comments") is not None else None,
                        )
                    )
                except Exception as map_err:
                    logger.debug("[browser] map ReelMetrics error: %s row=%s", map_err, r)
                    continue

            bs = BasicStats(
                avg_views_last_n=None,
                avg_likes_last_n=None,
                avg_comments_last_n=None,
                engagement_score=None,
                success_score=None,
            )
            duration = time.time() - start
            browser_action_duration_seconds.labels(action="get_reel_metrics", account=account).observe(duration)
            return reels, bs

        except (NoSuchElementException, StaleElementReferenceException, TimeoutException) as e:
            raise BrowserDOMError(f"reels scrape failed: {e}") from e
        except BrowserPortError:
            raise
        except Exception as e:
            raise BrowserPortError(f"reels unexpected error: {e}") from e

    def get_post_metrics(
        self,
        username: str,
        *,
        max_posts: int = 30,
    ) -> List[PostMetrics]:
        logger.debug("[browser] get_post_metrics noop username=%s max=%d", username, max_posts)
        return []

    def detect_rubro(self, username: str, bio: Optional[str]) -> Optional[str]:
        if not self._rubro_detector:
            return None
        try:
            return self._rubro_detector(username, bio)
        except Exception as e:
            logger.debug("[browser] rubro_detector error: %s", e)
            return None

    # ---------------------------------------------------------- Followings helper

    def _default_read_usernames_js(self) -> str:
        return r"""
        const dlg = document.evaluate("//div[@role='dialog']", document, null,
            XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        if (!dlg) return [];
        const anchors = dlg.querySelectorAll("a[href*='instagram.com/'], a[href^='/']");
        const users = [];
        for (const a of anchors) {
            let href = (a.getAttribute('href') || '').split('?')[0].split('#')[0];
            if (!href) continue;
            if (href.startsWith('/')) href = 'https://www.instagram.com' + href;
            try {
            const u = new URL(href).pathname.split('/').filter(Boolean)[0] || '';
            if (u && u.length <= 30 && !u.includes(' ')) users.push(u.toLowerCase());
            } catch {}
        }
        return [...new Set(users)];
        """

    @retry((WebDriverException,))
    def _read_visible_usernames(self) -> List[str]:
        WebDriverWait(self.driver, self._wait_timeout).until(
            EC.presence_of_element_located((By.XPATH, FOLLOWING_DIALOG_XPATH))
        )

        try:
            WebDriverWait(self.driver, self._wait_timeout).until(
                lambda driver: len(driver.find_elements(By.XPATH, FOLLOWING_DIALOG_XPATH + "//a[@href]")) > 0
            )
        except TimeoutException:
            logger.warning("No se encontraron links en el modal después de esperar")

        sleep_jitter(0.5, 0.3)

        try:
            result = self.driver.execute_script(self._read_usernames_js)
        except WebDriverException:
            raise
        except Exception as e:
            raise WebDriverException(str(e)) from e

        if not isinstance(result, list):
            raise WebDriverException("script did not return a list")

        out: List[str] = []
        for x in result:
            if isinstance(x, str):
                s = x.strip().lstrip("@").lower()
                if s and "/" not in s and " " not in s:
                    out.append(s)
        seen: Set[str] = set()
        uniq: List[str] = []
        for u in out:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq

    # ----------------------- default hooks -----------------------

    def __open_profile_default(self, username: str) -> None:
        self._go_profile(username)

    def __open_following_modal_default(self) -> None:
        try:
            btn = WebDriverWait(self.driver, self._wait_timeout).until(
                EC.element_to_be_clickable((By.XPATH, FOLLOWING_BUTTON_XPATH))
            )
            self._sched.wait_turn()
            try:
                from selenium.webdriver import ActionChains
                ActionChains(self.driver).move_to_element(btn).pause(0.2).perform()
            except Exception:
                pass
            try:
                import random
                if random.random() < 0.25:
                    from selenium.webdriver import ActionChains
                    ActionChains(self.driver).move_by_offset(2, 1).pause(0.15).move_by_offset(-1, 0).perform()
            except Exception:
                pass
            btn.click()
            WebDriverWait(self.driver, self._wait_timeout).until(
                EC.presence_of_element_located((By.XPATH, FOLLOWING_DIALOG_XPATH))
            )
            sleep_jitter(0.45, 0.35)
        except TimeoutException as e:
            raise BrowserDOMError(f"opening following modal timed out: {e}") from e
        except WebDriverException as e:
            raise BrowserDOMError(f"opening following modal failed: {e}") from e

    def __scroll_following_modal_once_default(self) -> None:
        try:
            self.driver.execute_script(
                """
                const xp = arguments[0];
                const step = arguments[1];
                const dlg = document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!dlg) return;
                let target = null;
                const nodes = dlg.querySelectorAll('div');
                for (const n of nodes) {
                  if (n.scrollHeight > n.clientHeight + 8) { target = n; break; }
                }
                if (!target) target = dlg;
                target.scrollTop = Math.min(target.scrollTop + step, target.scrollHeight);
                """,
                FOLLOWING_DIALOG_XPATH,
                int(self._scroll_step) if hasattr(self, "_scroll_step") else 145,
            )
        except Exception:
            pass

    def __sleep_human_default(self) -> None:
        sleep_jitter(self._small_pause, self._small_jitter)

    # ---------------------------------------------------- Protocol implementation

    def fetch_followings(
        self,
        owner: Username,
        max_items: Optional[int] = None,
    ) -> List[Username]:
        """
        Implementación del Protocol: fetch_followings.
        Usa get_followings internamente y convierte los strings a Username.
        """
        username_strs = self.get_followings(owner.value, max_items or 100)
        return [Username(value=s) for s in username_strs]
