from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, TypeVar, Sequence, Optional, Tuple

from scrapinsta.application.dto.profiles import AnalyzeProfileRequest, AnalyzeProfileResponse

from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)

from scrapinsta.domain.ports.browser_port import BrowserPort, BrowserPortError
from scrapinsta.domain.ports.profile_repo import ProfileRepository
from scrapinsta.infrastructure.redis import CacheService

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
    """
    Caso de uso para analizar un perfil de Instagram.
    Flujo:
        1. Obtiene snapshot del perfil.
        2. Si es público, obtiene métricas de reels y posts.
        3. Calcula estadísticas básicas y scores.
        4. Guarda (si se provee repo) el snapshot y análisis en BD.
        5. Retorna DTO con resultados.
    """
    def __init__(
        self,
        browser: BrowserPort,
        profile_repo: Optional[ProfileRepository] = None,
        *,
        cache_service: Optional[CacheService] = None,
        max_retries: int = 2,
    ) -> None:
        self.browser = browser
        self.profile_repo = profile_repo
        self.cache_service = cache_service
        self.max_retries = max_retries

    def __call__(self, req: AnalyzeProfileRequest) -> AnalyzeProfileResponse:
        username = req.username.strip().lstrip("@").lower()
        logger.info("AnalyzeProfile: start username=%s", username)

        # Intentar obtener desde caché primero
        if self.cache_service:
            cached_analysis = self.cache_service.get_profile_analysis(username)
            if cached_analysis:
                logger.info("AnalyzeProfile: cache hit username=%s", username)
                try:
                    # Reconstruir respuesta desde caché
                    # Nota: Esto requiere serialización/deserialización completa de los modelos
                    # Por ahora, si hay caché, retornamos que se saltó
                    # TODO: Implementar serialización completa de AnalyzeProfileResponse
                    return AnalyzeProfileResponse(
                        snapshot=None,
                        recent_reels=[],
                        recent_posts=[],
                        basic_stats=None,
                        skipped_recent=True
                    )
                except Exception as e:
                    logger.warning("AnalyzeProfile: error deserializando caché: %s", e)

        if self.profile_repo:
            last_analysis = self.profile_repo.get_last_analysis_date(username)
            if last_analysis:
                try:
                    last_date = datetime.fromisoformat(last_analysis.replace('Z', '+00:00'))
                    if datetime.now(last_date.tzinfo) - last_date < timedelta(days=30):
                        logger.info("AnalyzeProfile: usuario %s analizado recientemente (%s), saltando", 
                                  username, last_analysis)
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
                recent_reels, basic = reels_result
            else:
                recent_reels = list(reels_result)
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

        # Guardar en caché
        if self.cache_service:
            try:
                cache_data = {
                    "username": username,
                    "snapshot": snapshot.model_dump() if hasattr(snapshot, "model_dump") else snapshot.__dict__,
                    "basic_stats": basic.model_dump() if basic and hasattr(basic, "model_dump") else (basic.__dict__ if basic else None),
                    "recent_reels": [r.model_dump() if hasattr(r, "model_dump") else r.__dict__ for r in recent_reels] if recent_reels else [],
                    "recent_posts": [p.model_dump() if hasattr(p, "model_dump") else p.__dict__ for p in recent_posts] if recent_posts else [],
                }
                self.cache_service.set_profile_analysis(username, cache_data)
                logger.debug("AnalyzeProfile: cached analysis for username=%s", username)
            except Exception as e:
                logger.warning("AnalyzeProfile: cache save failed: %s", e)

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
