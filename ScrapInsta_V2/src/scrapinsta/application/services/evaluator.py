from __future__ import annotations
from typing import Dict, Any

# ---------- Benchmarks ----------
def get_engagement_benchmark(followers: int) -> float:
    if followers < 5_000:
        return 0.0608
    elif followers < 20_000:
        return 0.048
    elif followers < 100_000:
        return 0.051
    elif followers < 1_000_000:
        return 0.0378
    else:
        return 0.0266

def get_views_benchmark(followers: int) -> float:
    if followers < 5_000:
        return 0.20
    elif followers < 10_000:
        return 0.102
    elif followers < 50_000:
        return 0.08
    elif followers < 100_000:
        return 0.05
    else:
        return 0.04

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
    score = min(actual_engagement / expected_engagement, 1.0)
    return round(score, 6)

def calculate_success_score(profile: Dict[str, Any]) -> float:
    followers = int(profile.get("followers") or 0)
    posts = int(profile.get("posts") or 0)
    avg_likes = float(profile.get("avg_likes") or 0)
    avg_comments = float(profile.get("avg_comments") or 0)
    avg_views = float(profile.get("avg_views") or 0)
    if followers <= 0:
        return 0.0

    engagement = (avg_likes + avg_comments) / followers
    views_rate = avg_views / followers
    post_month = posts / 30.0

    norm_engagement = min(engagement / get_engagement_benchmark(followers), 1.0)
    norm_views = min(views_rate / get_views_benchmark(followers), 1.0)
    norm_post = min(post_month / 12.0, 1.0)

    score = 0.5 * norm_engagement + 0.3 * norm_views + 0.2 * norm_post
    return round(score, 6)

def evaluate_profile(profile: Dict[str, Any]) -> Dict[str, float] | None:
    # <-- ACEPTA legacy y new; siempre evalúa con claves normalizadas
    p = _normalize_payload(profile)
    engagement_score = calculate_engagement_score(p)
    success_score = calculate_success_score(p)
    return {
        "username": p.get("username"),
        "engagement_score": engagement_score,
        "success_score": success_score,
    }
