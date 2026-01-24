"""Serialización y deserialización de DTOs para caché."""
from __future__ import annotations

from typing import Any, Dict, Optional, List
from datetime import datetime

from scrapinsta.application.dto.profiles import AnalyzeProfileResponse
from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)
from scrapinsta.crosscutting.logging_config import get_logger

logger = get_logger("cache_serialization")


def serialize_analyze_profile_response(response: AnalyzeProfileResponse) -> Dict[str, Any]:
    """
    Serializa AnalyzeProfileResponse a un diccionario para almacenar en caché.
    
    Args:
        response: Respuesta a serializar
        
    Returns:
        Diccionario serializado compatible con JSON
    """
    data: Dict[str, Any] = {
        "snapshot": None,
        "recent_reels": [],
        "recent_posts": [],
        "basic_stats": None,
        "skipped_recent": response.skipped_recent,
    }
    
    if response.snapshot:
        data["snapshot"] = response.snapshot.model_dump(mode="json")
    
    if response.recent_reels:
        data["recent_reels"] = [
            reel.model_dump(mode="json") for reel in response.recent_reels
        ]
    
    if response.recent_posts:
        data["recent_posts"] = [
            post.model_dump(mode="json") for post in response.recent_posts
        ]
    
    if response.basic_stats:
        data["basic_stats"] = response.basic_stats.model_dump(mode="json")
    
    return data


def deserialize_analyze_profile_response(cached_data: Dict[str, Any]) -> AnalyzeProfileResponse:
    """
    Deserializa un diccionario del caché a AnalyzeProfileResponse.
    
    Args:
        cached_data: Datos del caché (dict)
        
    Returns:
        AnalyzeProfileResponse reconstruida
        
    Raises:
        ValueError: Si los datos no pueden ser deserializados
    """
    try:
        # Deserializar snapshot
        snapshot: Optional[ProfileSnapshot] = None
        if cached_data.get("snapshot"):
            snapshot_data = cached_data["snapshot"]
            # Convertir strings de datetime a objetos datetime si es necesario
            snapshot = ProfileSnapshot.model_validate(snapshot_data)
        
        # Deserializar recent_reels
        recent_reels: List[ReelMetrics] = []
        if cached_data.get("recent_reels"):
            for reel_data in cached_data["recent_reels"]:
                # Convertir strings de datetime a objetos datetime si es necesario
                if isinstance(reel_data.get("published_at"), str):
                    try:
                        reel_data["published_at"] = datetime.fromisoformat(
                            reel_data["published_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        reel_data["published_at"] = None
                recent_reels.append(ReelMetrics.model_validate(reel_data))
        
        # Deserializar recent_posts
        recent_posts: List[PostMetrics] = []
        if cached_data.get("recent_posts"):
            for post_data in cached_data["recent_posts"]:
                # Convertir strings de datetime a objetos datetime si es necesario
                if isinstance(post_data.get("published_at"), str):
                    try:
                        post_data["published_at"] = datetime.fromisoformat(
                            post_data["published_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        post_data["published_at"] = None
                recent_posts.append(PostMetrics.model_validate(post_data))
        
        # Deserializar basic_stats
        basic_stats: Optional[BasicStats] = None
        if cached_data.get("basic_stats"):
            basic_stats = BasicStats.model_validate(cached_data["basic_stats"])
        
        # Construir respuesta
        return AnalyzeProfileResponse(
            snapshot=snapshot,
            recent_reels=recent_reels if recent_reels else None,
            recent_posts=recent_posts if recent_posts else None,
            basic_stats=basic_stats,
            skipped_recent=cached_data.get("skipped_recent", False),
        )
    
    except Exception as e:
        logger.warning(
            "cache_deserialize_error",
            error=str(e),
            error_type=type(e).__name__,
            message="Error al deserializar datos del caché",
        )
        raise ValueError(f"Error al deserializar datos del caché: {str(e)}") from e

