"""
Humanization helpers for Selenium scraping on Instagram.
- Platform-coherent User-Agent selection (stable per account if desired)
- Human-like sleeps (uniform or lognormal jitter)
- Action scheduler with exponential backoff (soft-block aware)
- Smooth hover/scroll/click/typing helpers

Quickstart:
    from core.utils.humanize_helpers import (
        pick_user_agent, choose_and_apply_user_agent,
        sleep_jitter, HumanScheduler,
        human_scroll, hover_element_human, click_careful, type_like_human,
        ActionBudget,
    )
"""
from __future__ import annotations
import math
import os
import random
import sys
import time
import hashlib
from dataclasses import dataclass
from typing import Iterable, Optional, Literal

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

# -----------------------------------------------------------------------------
# User-Agent selection helpers
# -----------------------------------------------------------------------------

def detect_platform() -> str:
    """Return a coarse platform: 'linux' | 'windows' | 'mac'."""
    p = sys.platform.lower()
    if p.startswith("linux"):
        return "linux"
    if p.startswith("win"):
        return "windows"
    if p.startswith("darwin") or "mac" in p:
        return "mac"
    return "linux"


def is_chromium_ua(ua: str) -> bool:
    ua_l = ua.lower()
    # Accept Chromium (Chrome/Edg). Exclude Firefox. Safari will still match due to "Safari/" token in Chrome UAs
    return ("chrome/" in ua_l or "edg/" in ua_l) and "firefox" not in ua_l and "safari/" in ua_l


def matches_platform(ua: str, platform: str) -> bool:
    ua_l = ua.lower()
    if platform == "linux":
        return "x11; linux" in ua_l
    if platform == "windows":
        return "windows nt" in ua_l
    if platform == "mac":
        return "macintosh" in ua_l or "mac os x" in ua_l
    return True


def _stable_choice(seq: Iterable[str], stable_key: Optional[str]) -> str:
    seq = list(seq)
    if not seq:
        raise ValueError("Empty sequence for stable choice")
    if stable_key is None:
        # process-scoped randomness (avoid per-action rotation)
        random.seed(os.getpid())
        return random.choice(seq)
    # stable per key (e.g., username) across runs
    h = hashlib.sha256(str(stable_key).encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(seq)
    return seq[idx]


def pick_user_agent(bconfig: dict, platform: Optional[str] = None, *, stable_key: Optional[str] = None) -> str:
    """Pick a Chromium UA from BROWSER_CONFIG coherent with the current platform.

    Args:
        bconfig: dict holding "user_agents" list
        platform: override detected platform (linux/windows/mac)
        stable_key: if provided (e.g., username), returns a deterministic UA per key
    """
    platform = platform or detect_platform()
    uas: Iterable[str] = bconfig.get("user_agents", [])
    chromes = [ua for ua in uas if is_chromium_ua(ua)]
    platform_matched = [ua for ua in chromes if matches_platform(ua, platform)]
    pool = platform_matched or chromes or list(uas)
    if not pool:
        raise ValueError("No user agents configured in BROWSER_CONFIG")
    return _stable_choice(pool, stable_key)


def choose_and_apply_user_agent(options, bconfig: dict, *, stable_key: Optional[str] = None) -> str:
    """Pick a coherent UA and add it to ChromeOptions (returns chosen UA)."""
    ua = pick_user_agent(bconfig, stable_key=stable_key)
    options.add_argument(f"user-agent={ua}")
    return ua

# -----------------------------------------------------------------------------
# Sleep with jitter
# -----------------------------------------------------------------------------

def sleep_jitter(mean: float, jitter_pct: float = 0.35, min_ms: int = 120, *, dist: Literal["uniform","lognormal"] = "uniform") -> None:
    """Sleep with random jitter.

    Args:
        mean: seconds (typical time you want)
        jitter_pct: ±pct jitter (for uniform) or lognormal sigma approx
        min_ms: minimum sleep in milliseconds
        dist: 'uniform' (±jitter_pct) or 'lognormal' (right-skewed human-like)
    """
    if mean <= 0:
        return
    dur: float
    if dist == "uniform":
        low = mean * (1 - jitter_pct)
        high = mean * (1 + jitter_pct)
        dur = random.uniform(low, high)
    else:  # lognormal around mean (approximate)
        # derive mu, sigma so that E[X]≈mean (simple heuristic)
        sigma = max(0.05, min(1.0, jitter_pct))
        mu = math.log(max(1e-4, mean)) - 0.5 * sigma * sigma
        dur = random.lognormvariate(mu, sigma)
    dur = max(dur, min_ms / 1000.0)
    time.sleep(dur)

# -----------------------------------------------------------------------------
# Human-like scheduler: actions per minute + backoff
# -----------------------------------------------------------------------------

@dataclass
class BackoffPolicy:
    base_seconds: float = 30.0
    factor: float = 2.0
    max_seconds: float = 15 * 60.0  # 15 minutes


class HumanScheduler:
    """Rate-limit actions per account with exponential backoff on blocks/errors.

    Example:
        sched = HumanScheduler(actions_per_min=18)
        while tasks:
            sched.wait_turn()
            do_action()
    """
    def __init__(self, actions_per_min: int = 20, jitter_pct: float = 0.25, backoff: BackoffPolicy | None = None, min_interval: float = 0.0):
        self.interval = 60.0 / max(1, actions_per_min)
        self.jitter_pct = jitter_pct
        self.backoff = backoff or BackoffPolicy()
        self.min_interval = max(0.0, min_interval)
        self._next_ts = time.monotonic()
        self._current_backoff = 0.0

    def note_soft_block(self):
        """Call when you detect 429, unusual activity, or challenge."""
        if self._current_backoff == 0.0:
            self._current_backoff = self.backoff.base_seconds
        else:
            self._current_backoff = min(self._current_backoff * self.backoff.factor, self.backoff.max_seconds)
        self._next_ts = time.monotonic() + self._current_backoff

    def clear_backoff(self):
        self._current_backoff = 0.0

    def wait_turn(self):
        now = time.monotonic()
        # respect backoff first
        if now < self._next_ts:
            time.sleep(self._next_ts - now)
        # schedule next action with jitter and a floor interval
        jitter = random.uniform(1 - self.jitter_pct, 1 + self.jitter_pct)
        interval = max(self.min_interval, self.interval * jitter)
        self._next_ts = time.monotonic() + interval

# -----------------------------------------------------------------------------
# Mouse / Hover / Scroll / Typing with human-like patterns
# -----------------------------------------------------------------------------

_DEF_STEP_TIME = 0.018  # 18ms per tiny step ~ 55 fps


def _ease_in_out(t: float) -> float:
    """Smooth easing (t in [0,1])."""
    return 0.5 * (1 - math.cos(math.pi * t))


def hover_element_human(driver: WebDriver, element: WebElement, duration: float = 0.6, overshoot_px: int = 4) -> None:
    """Hover an element by gliding cursor with easing and a tiny overshoot+correction.
    Works best when a prior click placed the cursor near the viewport center.
    """
    actions = ActionChains(driver)
    # Move to element center smoothly via small offsets
    actions.move_to_element_with_offset(element, random.randint(-3, 3), random.randint(-2, 2)).pause(_DEF_STEP_TIME)
    actions.move_to_element(element).pause(_DEF_STEP_TIME)
    # tiny overshoot and correction
    actions.move_by_offset(overshoot_px, 0).pause(_DEF_STEP_TIME)
    actions.move_by_offset(-overshoot_px, 0).pause(_DEF_STEP_TIME)
    actions.perform()
    sleep_jitter(duration * 0.15, 0.5)


def human_scroll(driver: WebDriver, total_px: int, duration: float = 1.2, step_px: int = 120, jitter_px: int = 30) -> None:
    """Scroll in small steps over a duration, with random jitter in pixels and timing."""
    steps = max(1, int(abs(total_px) / max(1, step_px)))
    direction = 1 if total_px >= 0 else -1
    base_delay = duration / steps if steps else duration
    for _ in range(steps):
        px = direction * (step_px + random.randint(-jitter_px, jitter_px))
        driver.execute_script("window.scrollBy(0, arguments[0]);", px)
        sleep_jitter(base_delay, 0.35, min_ms=10)


def type_like_human(element: WebElement, text: str, base_delay: float = 0.085, jitter_pct: float = 0.55) -> None:
    """Type with per-char jitter and occasional short pauses after punctuation/spaces."""
    burst = random.randint(4, 8)
    c = 0
    for ch in text:
        element.send_keys(ch)
        c += 1
        pause = base_delay
        if ch in ",.;:!? ":
            pause *= 1.8
        if c % burst == 0:
            pause *= 1.5  # tiny pause after a small burst
            burst = random.randint(4, 8)
        sleep_jitter(pause, jitter_pct, min_ms=20, dist="lognormal")


def click_careful(driver: WebDriver, element: WebElement) -> None:
    """Click with a short pre-hover, tiny pause, then click; helps with hover-dependent UIs."""
    hover_element_human(driver, element, duration=0.35)
    sleep_jitter(0.06, 0.5)
    ActionChains(driver).move_to_element(element).click().perform()
    sleep_jitter(0.12, 0.5)

# -----------------------------------------------------------------------------
# Simple budget helper for reels inspection per profile
# -----------------------------------------------------------------------------

class ActionBudget:
    """Limit a number of actions for a given context (e.g., reels per profile)."""
    def __init__(self, max_actions: int):
        self.max_actions = max_actions
        self.done = 0

    def take(self) -> bool:
        if self.done >= self.max_actions:
            return False
        self.done += 1
        return True

# -----------------------------------------------------------------------------
# Small integration helpers
# -----------------------------------------------------------------------------

def choose_and_apply_user_agent(options, bconfig: dict, *, stable_key: Optional[str] = None) -> str:
    """Pick a coherent UA and add it to ChromeOptions (returns chosen UA)."""
    ua = pick_user_agent(bconfig, stable_key=stable_key)
    options.add_argument(f"user-agent={ua}")
    return ua
