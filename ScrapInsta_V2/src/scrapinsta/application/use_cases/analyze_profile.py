from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, TypeVar, Sequence, Optional, Tuple

# DTOs de entrada/salida del caso de uso
from scrapinsta.application.dto.profiles import AnalyzeProfileRequest, AnalyzeProfileResponse

# Modelos de dominio
from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)

# Puertos
from scrapinsta.domain.ports.browser_port import BrowserPort, BrowserPortError
from scrapinsta.domain.ports.profile_repo import ProfileRepository

# Servicio de evaluación
from scrapinsta.application.services.evaluator import evaluate_profile

T = TypeVar("T")
logger = logging.getLogger(__name__)


def _avg(nums: Sequence[float | int]) -> float:
    return float(sum(float(x) for x in nums) / len(nums)) if nums else 0.0


def _compute_basic_stats_from_reels(reels: Sequence[ReelMetrics]) -> BasicStats:
    views = [float(r.views or 0) for r in reels]
    likes = [float(r.likes or 0) for r in reels]
    comments = [float(r.comments or 0) for r in reels]
    return BasicStats(
        avg_views_last_n=_avg(views) or None,
        avg_likes_last_n=_avg(likes) or None,
        avg_comments_last_n=_avg(comments) or None,
        engagement_score=None,
        success_score=None,
    )


def _apply_success_metrics(snapshot: ProfileSnapshot, basic: Optional[BasicStats]) -> Optional[BasicStats]:
    if basic is None:
        return None
    payload = {
        "username": snapshot.username,
        "followers": int(snapshot.followers or 0),
        "followings": int(snapshot.followings or 0),
        "posts": int(snapshot.posts or 0),
        "avg_likes": float(basic.avg_likes_last_n or 0.0),
        "avg_comments": float(basic.avg_comments_last_n or 0.0),
        "avg_views": float(basic.avg_views_last_n or 0.0),
    }
    scores = evaluate_profile(payload)
    return BasicStats(
        avg_views_last_n=basic.avg_views_last_n,
        avg_likes_last_n=basic.avg_likes_last_n,
        avg_comments_last_n=basic.avg_comments_last_n,
        engagement_score=(scores["engagement_score"] if scores else None),
        success_score=(scores["success_score"] if scores else None),
    )


class AnalyzeProfileUseCase:
    def __init__(
        self,
        browser: BrowserPort,
        profile_repo: Optional[ProfileRepository] = None,
        *,
        max_retries: int = 2,
    ) -> None:
        self.browser = browser
        self.profile_repo = profile_repo
        self.max_retries = max_retries

    def __call__(self, req: AnalyzeProfileRequest) -> AnalyzeProfileResponse:
        username = req.username.strip().lstrip("@").lower()
        logger.info("AnalyzeProfile: start username=%s", username)

        # Verificar si el usuario ya fue analizado recientemente (menos de 30 días)
        if self.profile_repo:
            last_analysis = self.profile_repo.get_last_analysis_date(username)
            if last_analysis:
                try:
                    last_date = datetime.fromisoformat(last_analysis.replace('Z', '+00:00'))
                    if datetime.now(last_date.tzinfo) - last_date < timedelta(days=30):
                        logger.info("AnalyzeProfile: usuario %s analizado recientemente (%s), saltando", 
                                  username, last_analysis)
                        # Retornar respuesta vacía indicando que se saltó
                        return AnalyzeProfileResponse(
                            snapshot=None, 
                            recent_reels=[], 
                            recent_posts=[], 
                            basic_stats=None,
                            skipped_recent=True
                        )
                except Exception as e:
                    logger.warning("AnalyzeProfile: error parseando fecha de último análisis: %s", e)

        snapshot: ProfileSnapshot = self._retry(lambda: self.browser.get_profile_snapshot(username))
        # el rubro puede seguir calculándose si lo usás en otra parte; no forma parte del DTO
        _ = self._retry(lambda: self.browser.detect_rubro(username, snapshot.bio))

        recent_reels: list[ReelMetrics] = []
        recent_posts: list[PostMetrics] = []
        basic: Optional[BasicStats] = None

        if getattr(snapshot.privacy, "value", str(snapshot.privacy)) == "private":
            resp = AnalyzeProfileResponse(
                snapshot=snapshot, recent_reels=recent_reels, recent_posts=recent_posts, basic_stats=None
            )
            if self.profile_repo:
                try:
                    pid = self.profile_repo.upsert_profile(snapshot)
                    self.profile_repo.save_analysis_snapshot(pid, snapshot, None, recent_reels, recent_posts)
                except Exception as e:
                    logger.warning("AnalyzeProfile: DB save (private) failed: %s", e)
            return resp

        if req.fetch_reels:
            reels_result = self._retry(lambda: self.browser.get_reel_metrics(username, max_reels=req.max_reels))
            if isinstance(reels_result, tuple) and len(reels_result) == 2:
                recent_reels, basic = reels_result  # type: ignore[assignment]
            else:
                recent_reels = list(reels_result)  # type: ignore[assignment]
                basic = _compute_basic_stats_from_reels(recent_reels)

        if req.fetch_posts:
            recent_posts = self._retry(lambda: self.browser.get_post_metrics(username, max_posts=req.max_posts))

        basic = _apply_success_metrics(snapshot, basic)

        resp = AnalyzeProfileResponse(
            snapshot=snapshot,
            recent_reels=recent_reels,
            recent_posts=recent_posts,
            basic_stats=basic,
        )

        if self.profile_repo:
            try:
                pid = self.profile_repo.upsert_profile(snapshot)
                self.profile_repo.save_analysis_snapshot(pid, snapshot, basic, recent_reels, recent_posts)
            except Exception as e:
                logger.warning("AnalyzeProfile: DB save failed: %s", e)

        return resp

    def _retry(self, fn: Callable[[], T]) -> T:
        attempt = 0
        while True:
            try:
                return fn()
            except BrowserPortError as e:
                attempt += 1
                retryable = bool(getattr(e, "retryable", False))
                if (not retryable) or (attempt > self.max_retries):
                    raise
                import time, random
                time.sleep(max(0.3, 0.8 * attempt * (1 + random.uniform(-0.25, 0.25))))
