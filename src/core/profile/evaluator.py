import math
from typing import Dict, Any

'''
actual engagement = (avg_likes + avg_comments) / followers
engagement_benchmark = actual engagement / expected engagement

norm_engagement = min(engagement_benchmark, 1.0)
norm_views = min(views_rate / expected views rate, 1.0)
norm_post = min(post_month / 12.0, 1.0)  # 12 posts al mes es excelente
success_score = 0.5 * norm_engagement + 0.3 * norm_views + 0.2 * norm_post

'''

def get_engagement_benchmark(followers: int) -> float:
    """Benchmark de engagement (% en decimal) según rango real de Instagram."""
    if followers < 5_000:
        return 0.0608
    elif followers < 20_000:
        return 0.048  # Nano influencers
    elif followers < 100_000:
        return 0.051  # Micro influencers
    elif followers < 1_000_000:
        return 0.0378  # Macro influencers
    else:
        return 0.0266  # Mega influencers / celebridades

def get_views_benchmark(followers: int) -> float:
    """Tasa de vistas esperadas como ratio views/followers, en decimal."""
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


def calculate_engagement_score(profile: Dict[str, Any]) -> float:
    followers = profile.get('followers_count') or 0
    avg_likes = profile.get('avg_likes') or 0
    avg_comments = profile.get('avg_comments') or 0

    if followers <= 0:
        return 0.0

    actual_engagement = (avg_likes + avg_comments) / followers
    expected_engagement = get_engagement_benchmark(followers)

    score = actual_engagement / expected_engagement
    score = min(score, 1.0)
    return round(score, 6)


def calculate_success_score(profile: Dict[str, Any]) -> float:
    followers = profile.get('followers_count') or 0
    posts = profile.get('posts_count') or 0
    avg_likes = profile.get('avg_likes') or 0
    avg_comments = profile.get('avg_comments') or 0
    avg_views = profile.get('avg_views') or 0

    if followers <= 0:
        return 0.0

    engagement = (avg_likes + avg_comments) / followers
    views_rate = avg_views / followers
    post_month = posts / 30.0  # Promedio de publicaciones por mes

    norm_engagement = min(engagement / get_engagement_benchmark(followers), 1.0)
    norm_views = min(views_rate / get_views_benchmark(followers), 1.0)       # 0.04 es excelente
    norm_post = min(post_month / 12.0, 1.0)        # 12 posts al mes es excelente

    score = 0.5 * norm_engagement + 0.3 * norm_views + 0.2 * norm_post
    return round(score, 6)


def evaluate_profile(profile: Dict[str, Any]) -> Dict[str, float] | None:
    engagement_score = calculate_engagement_score(profile)
    success_score = calculate_success_score(profile)

    return {
        "username": profile.get("username"),
        "engagement_score": engagement_score,
        "success_score": success_score
    }

