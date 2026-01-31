"""
Tests unitarios para el servicio de evaluación de perfiles.

Este servicio es puro (sin side effects), por lo que es ideal para tests.
"""
from __future__ import annotations

import pytest

from scrapinsta.application.services.evaluator import (
    evaluate_profile,
    calculate_engagement_score,
    calculate_success_score,
    get_engagement_benchmark,
    get_views_benchmark,
)


class TestEngagementBenchmark:
    """Tests para benchmarks de engagement."""
    
    def test_engagement_benchmark_small_account(self):
        """Test para cuenta pequeña (< 5K followers)."""
        assert get_engagement_benchmark(3000) == 0.0608
    
    def test_engagement_benchmark_medium_account(self):
        """Test para cuenta mediana (5K-20K followers)."""
        assert get_engagement_benchmark(10000) == 0.048
    
    def test_engagement_benchmark_large_account(self):
        """Test para cuenta grande (100K-1M followers)."""
        assert get_engagement_benchmark(500000) == 0.0378
    
    def test_engagement_benchmark_mega_account(self):
        """Test para cuenta mega (> 1M followers)."""
        assert get_engagement_benchmark(2000000) == 0.0266


class TestViewsBenchmark:
    """Tests para benchmarks de views."""
    
    def test_views_benchmark_small_account(self):
        """Test para cuenta pequeña."""
        assert get_views_benchmark(3000) == 0.20
    
    def test_views_benchmark_medium_account(self):
        """Test para cuenta mediana."""
        assert get_views_benchmark(30000) == 0.08
    
    def test_views_benchmark_large_account(self):
        """Test para cuenta grande."""
        assert get_views_benchmark(200000) == 0.04


class TestCalculateEngagementScore:
    """Tests para cálculo de engagement score."""
    
    def test_engagement_score_zero_followers(self):
        """Engagement score debe ser 0 si no hay followers."""
        profile = {
            "followers": 0,
            "avg_likes": 100,
            "avg_comments": 10,
        }
        assert calculate_engagement_score(profile) == 0.0
    
    def test_engagement_score_normal(self):
        """Engagement score normal."""
        profile = {
            "followers": 10000,
            "avg_likes": 500,
            "avg_comments": 50,
        }
        score = calculate_engagement_score(profile)
        assert 0.0 <= score <= 1.0
        assert score > 0.0
    
    def test_engagement_score_above_benchmark(self):
        """Engagement score no debe exceder 1.0."""
        profile = {
            "followers": 10000,
            "avg_likes": 100000,  # Muy alto
            "avg_comments": 10000,
        }
        score = calculate_engagement_score(profile)
        assert score == 1.0  # Debe estar capado a 1.0
    
    def test_engagement_score_legacy_keys(self):
        """Debe funcionar con claves legacy (followers_count)."""
        profile = {
            "followers_count": 10000,
            "avg_likes": 500,
            "avg_comments": 50,
        }
        score = calculate_engagement_score(profile)
        assert 0.0 <= score <= 1.0


class TestCalculateSuccessScore:
    """Tests para cálculo de success score (60% engagement + 40% views)."""
    
    def test_success_score_zero_followers(self):
        """Success score debe ser 0 si no hay followers."""
        profile = {
            "followers": 0,
            "avg_likes": 500,
            "avg_comments": 50,
            "avg_views": 5000,
        }
        assert calculate_success_score(profile) == 0.0
    
    def test_success_score_normal(self):
        """Success score normal."""
        profile = {
            "followers": 10000,
            "avg_likes": 500,
            "avg_comments": 50,
            "avg_views": 5000,
        }
        score = calculate_success_score(profile)
        assert 0.0 <= score <= 1.0
        assert score > 0.0
    
    def test_success_score_high_engagement(self):
        """Success score con engagement alto."""
        profile = {
            "followers": 10000,
            "avg_likes": 1000,
            "avg_comments": 100,
            "avg_views": 8000,
        }
        score = calculate_success_score(profile)
        assert score > 0.5  # Debe ser alto
    
    def test_success_score_ignores_posts(self):
        """Success score no usa el campo posts (fue eliminado del cálculo)."""
        profile_with_posts = {
            "followers": 10000,
            "posts": 500,  # Muchos posts
            "avg_likes": 500,
            "avg_comments": 50,
            "avg_views": 5000,
        }
        profile_without_posts = {
            "followers": 10000,
            "posts": 0,  # Sin posts
            "avg_likes": 500,
            "avg_comments": 50,
            "avg_views": 5000,
        }
        # Ambos deben dar el mismo resultado
        assert calculate_success_score(profile_with_posts) == calculate_success_score(profile_without_posts)


class TestEvaluateProfile:
    """Tests para evaluación completa de perfil."""
    
    def test_evaluate_profile_complete(self):
        """Evaluación completa de perfil."""
        profile = {
            "username": "testuser",
            "followers": 10000,
            "posts": 150,
            "avg_likes": 500,
            "avg_comments": 50,
            "avg_views": 5000,
        }
        result = evaluate_profile(profile)
        
        assert result is not None
        assert result["username"] == "testuser"
        assert "engagement_score" in result
        assert "success_score" in result
        assert 0.0 <= result["engagement_score"] <= 1.0
        assert 0.0 <= result["success_score"] <= 1.0
    
    def test_evaluate_profile_with_none_values(self):
        """Evaluación con valores None."""
        profile = {
            "username": "testuser",
            "followers": 10000,
            "posts": 150,
            "avg_likes": None,
            "avg_comments": None,
            "avg_views": None,
        }
        result = evaluate_profile(profile)
        
        assert result is not None
        # Engagement score es 0.0 porque avg_likes + avg_comments = 0
        assert result["engagement_score"] == 0.0
        # Success score es 0.0 porque engagement y views son 0
        # (posts ya no se usa en el cálculo)
        assert result["success_score"] == 0.0
    
    def test_evaluate_profile_legacy_keys(self):
        """Evaluación con claves legacy."""
        profile = {
            "username": "testuser",
            "followers_count": 10000,
            "posts_count": 150,
            "avg_likes": 500,
            "avg_comments": 50,
            "avg_views": 5000,
        }
        result = evaluate_profile(profile)
        
        assert result is not None
        assert "engagement_score" in result
        assert "success_score" in result

