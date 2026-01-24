from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, TypeVar, Sequence, Optional, Tuple

from scrapinsta.application.dto.profiles import AnalyzeProfileRequest, AnalyzeProfileResponse
from scrapinsta.application.dto.cache_serialization import (
    serialize_analyze_profile_response,
    deserialize_analyze_profile_response,
)
from scrapinsta.crosscutting.logging_config import get_logger

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
log = get_logger("analyze_profile")


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
        log.info("analyze_profile_start", username=username)

        # Intentar obtener desde caché primero
        if self.cache_service:
            cached_analysis = self.cache_service.get_profile_analysis(username)
            if cached_analysis:
                log.info("analyze_profile_cache_hit", username=username)
                try:
                    # Deserializar respuesta completa desde caché
                    response = deserialize_analyze_profile_response(cached_analysis)
                    log.debug("analyze_profile_cache_deserialized", username=username)
                    
                    # IMPORTANTE: También guardar en BD cuando hay cache hit
                    # Esto asegura que el historial en BD esté completo, incluso si
                    # el perfil solo se consulta desde caché (sin hacer scraping)
                    if self.profile_repo and response.snapshot:
                        try:
                            pid = self.profile_repo.upsert_profile(response.snapshot)
                            self.profile_repo.save_analysis_snapshot(
                                pid,
                                response.snapshot,
                                response.basic_stats,
                                response.recent_reels or [],
                                response.recent_posts or [],
                            )
                            log.debug("analyze_profile_db_saved_from_cache", username=username)
                        except Exception as e:
                            # No crítico: el cache hit ya retornó los datos
                            # Solo logueamos el error pero no fallamos la respuesta
                            log.warning(
                                "analyze_profile_db_save_from_cache_failed",
                                username=username,
                                error=str(e),
                                message="Cache hit exitoso, pero falló guardado en BD (no crítico)",
                            )
                    
                    return response
                except Exception as e:
                    log.warning(
                        "analyze_profile_cache_deserialize_failed",
                        username=username,
                        error=str(e),
                        message="Continuando con análisis completo",
                    )
                    # Si falla la deserialización, continuar con análisis normal

        if self.profile_repo:
            last_analysis = self.profile_repo.get_last_analysis_date(username)
            if last_analysis:
                try:
                    last_date = datetime.fromisoformat(last_analysis.replace('Z', '+00:00'))
                    if datetime.now(last_date.tzinfo) - last_date < timedelta(days=30):
                        log.info("analyze_profile_skipped_recent", username=username, last_analysis=last_analysis)
                        return AnalyzeProfileResponse(
                            snapshot=None, 
                            recent_reels=[], 
                            recent_posts=[], 
                            basic_stats=None,
                            skipped_recent=True
                        )
                except Exception as e:
                    log.warning("analyze_profile_last_analysis_parse_failed", username=username, error=str(e))

        snapshot: ProfileSnapshot = self._retry(lambda: self.browser.get_profile_snapshot(username))
        rubro = self._retry(lambda: self.browser.detect_rubro(username, snapshot.bio))
        if rubro and not getattr(snapshot, "rubro", None):
            # ProfileSnapshot es inmutable (frozen=True): usamos model_copy para agregar rubro.
            try:
                snapshot = snapshot.model_copy(update={"rubro": rubro})
            except Exception:
                pass

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
                    log.warning("analyze_profile_db_save_private_failed", username=username, error=str(e))
            return resp

        if req.fetch_reels:
            reels_result = self._retry(lambda: self.browser.get_reel_metrics(username, max_reels=req.max_reels))
            if isinstance(reels_result, tuple) and len(reels_result) == 2:
                recent_reels, basic = reels_result
                # Algunos adapters devuelven BasicStats "vacío" (avg_* None). En ese caso,
                # lo computamos desde los reels para que engagement/success no queden en 0/0.2 por defecto.
                try:
                    if basic and basic.avg_views_last_n is None and basic.avg_likes_last_n is None and basic.avg_comments_last_n is None:
                        basic = _compute_basic_stats_from_reels(recent_reels)
                except Exception:
                    pass
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

        # Guardar en caché usando serialización completa
        if self.cache_service:
            try:
                cache_data = serialize_analyze_profile_response(resp)
                self.cache_service.set_profile_analysis(username, cache_data)
                log.debug("analyze_profile_cache_saved", username=username)
            except Exception as e:
                log.warning(
                    "analyze_profile_cache_save_failed",
                    username=username,
                    error=str(e),
                    message="No crítico: análisis completado exitosamente",
                )

        if self.profile_repo:
            try:
                pid = self.profile_repo.upsert_profile(snapshot)
                self.profile_repo.save_analysis_snapshot(pid, snapshot, basic, recent_reels, recent_posts)
            except Exception as e:
                log.warning("analyze_profile_db_save_failed", username=username, error=str(e))

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
