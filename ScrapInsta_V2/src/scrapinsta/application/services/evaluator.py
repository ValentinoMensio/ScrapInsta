from __future__ import annotations
from typing import Dict, Any

ENGAGEMENT_FOLLOWER_BUCKETS = (
    (5_000, 0.0608),
    (20_000, 0.048),
    (100_000, 0.051),
    (1_000_000, 0.0378),
)
ENGAGEMENT_BENCHMARK_DEFAULT = 0.0266

VIEWS_FOLLOWER_BUCKETS = (
    (5_000, 0.20),
    (10_000, 0.102),
    (50_000, 0.08),
    (100_000, 0.05),
)
VIEWS_BENCHMARK_DEFAULT = 0.04

ENGAGEMENT_SCORE_MAX = 1.0
SUCCESS_WEIGHT_ENGAGEMENT = 0.6
SUCCESS_WEIGHT_VIEWS = 0.4
SCORE_ROUND_DIGITS = 6

# ---------- Benchmarks ----------
def get_engagement_benchmark(followers: int) -> float:
    for limit, value in ENGAGEMENT_FOLLOWER_BUCKETS:
        if followers < limit:
            return value
    return ENGAGEMENT_BENCHMARK_DEFAULT

def get_views_benchmark(followers: int) -> float:
    for limit, value in VIEWS_FOLLOWER_BUCKETS:
        if followers < limit:
            return value
    return VIEWS_BENCHMARK_DEFAULT

# ---------- Normalización/compat ----------
def _normalize_payload(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Acepta payloads 'nuevos' y 'legados', devolviendo SIEMPRE claves normalizadas.
      legacy: followers_count/posts_count
      new:    followers/posts
    """
    followers = p.get("followers")
    posts = p.get("posts")
    if followers is None and "followers_count" in p:
        followers = p.get("followers_count")
    if posts is None and "posts_count" in p:
        posts = p.get("posts_count")

    return {
        "username": p.get("username"),
        "followers": int(followers or 0),
        "posts": int(posts or 0),
        "avg_likes": float(p.get("avg_likes") or 0.0),
        "avg_comments": float(p.get("avg_comments") or 0.0),
        "avg_views": float(p.get("avg_views") or 0.0),
    }

# ---------- Scores ----------
def calculate_engagement_score(profile: Dict[str, Any]) -> float:
    followers = int(profile.get("followers") or 0)
    avg_likes = float(profile.get("avg_likes") or 0)
    avg_comments = float(profile.get("avg_comments") or 0)
    if followers <= 0:
        return 0.0
    actual_engagement = (avg_likes + avg_comments) / followers
    expected_engagement = get_engagement_benchmark(followers)
    score = min(actual_engagement / expected_engagement, ENGAGEMENT_SCORE_MAX)
    return round(score, SCORE_ROUND_DIGITS)

def calculate_success_score(profile: Dict[str, Any]) -> float:
    """
    Calcula un score de éxito combinando engagement y views normalizadas.
    
    Pesos: 60% engagement + 40% views
    
    Nota: Se eliminó el componente de frecuencia de posts porque no tenemos
    la fecha de creación de la cuenta ni las fechas de publicación de los posts,
    lo cual hacía imposible calcular la frecuencia real de publicación.
    """
    followers = int(profile.get("followers") or 0)
    avg_likes = float(profile.get("avg_likes") or 0)
    avg_comments = float(profile.get("avg_comments") or 0)
    avg_views = float(profile.get("avg_views") or 0)
    
    if followers <= 0:
        return 0.0

    engagement = (avg_likes + avg_comments) / followers
    views_rate = avg_views / followers

    norm_engagement = min(engagement / get_engagement_benchmark(followers), ENGAGEMENT_SCORE_MAX)
    norm_views = min(views_rate / get_views_benchmark(followers), ENGAGEMENT_SCORE_MAX)

    score = (
        SUCCESS_WEIGHT_ENGAGEMENT * norm_engagement
        + SUCCESS_WEIGHT_VIEWS * norm_views
    )
    return round(score, SCORE_ROUND_DIGITS)

def evaluate_profile(profile: Dict[str, Any]) -> Dict[str, float] | None:
    p = _normalize_payload(profile)
    engagement_score = calculate_engagement_score(p)
    success_score = calculate_success_score(p)
    return {
        "username": p.get("username"),
        "engagement_score": engagement_score,
        "success_score": success_score,
    }
