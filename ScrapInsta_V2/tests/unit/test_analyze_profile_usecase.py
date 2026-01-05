"""
Tests unitarios para AnalyzeProfileUseCase.

Usa mocks para BrowserPort y ProfileRepository, no ejecuta Selenium ni BD real.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from scrapinsta.application.use_cases.analyze_profile import AnalyzeProfileUseCase
from scrapinsta.application.dto.profiles import AnalyzeProfileRequest, AnalyzeProfileResponse
from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    PrivacyStatus,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)
from scrapinsta.domain.ports.browser_port import BrowserPortError


class TestAnalyzeProfileUseCase:
    """Tests para AnalyzeProfileUseCase."""
    
    def test_analyze_profile_public_success(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test de análisis exitoso de perfil público."""
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(
            username="testuser",
            fetch_reels=True,
            fetch_posts=False,
            max_reels=5,
        )
        
        response = use_case(request)
        
        assert isinstance(response, AnalyzeProfileResponse)
        assert response.snapshot is not None
        assert response.snapshot.username == "testuser"
        assert response.recent_reels is not None
        assert len(response.recent_reels) > 0
        assert response.basic_stats is not None
        
        # Verificar que se llamó al browser
        mock_browser_port.get_profile_snapshot.assert_called_once_with("testuser")
        mock_browser_port.detect_rubro.assert_called_once()
        mock_browser_port.get_reel_metrics.assert_called_once_with("testuser", max_reels=5)
        
        # Verificar que se guardó en el repo
        mock_profile_repo.upsert_profile.assert_called_once()
        mock_profile_repo.save_analysis_snapshot.assert_called_once()
    
    def test_analyze_profile_private(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test de análisis de perfil privado (sin reels)."""
        # Configurar browser para retornar perfil privado
        private_snapshot = ProfileSnapshot(
            username="privateuser",
            bio="Bio privada",
            followers=5000,
            followings=200,
            posts=50,
            is_verified=False,
            privacy=PrivacyStatus.private,
        )
        def mock_get_private_snapshot(username: str) -> ProfileSnapshot:
            return private_snapshot
        mock_browser_port.get_profile_snapshot.side_effect = mock_get_private_snapshot
        
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(
            username="privateuser",
            fetch_reels=True,
        )
        
        response = use_case(request)
        
        assert response.snapshot is not None
        assert response.snapshot.privacy == PrivacyStatus.private
        assert response.recent_reels == []
        assert response.basic_stats is None
        
        # Verificar que NO se llamó get_reel_metrics para privado
        mock_browser_port.get_reel_metrics.assert_not_called()
        
        # Verificar que se guardó igual
        mock_profile_repo.upsert_profile.assert_called_once()
    
    def test_analyze_profile_without_repo(
        self,
        mock_browser_port: Mock,
    ):
        """Test de análisis sin repositorio (solo retorna datos)."""
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=None,  # Sin repo
        )
        
        request = AnalyzeProfileRequest(
            username="testuser",
            fetch_reels=True,
        )
        
        response = use_case(request)
        
        assert response.snapshot is not None
        assert response.recent_reels is not None
        
        # No debe haber errores aunque no haya repo
    
    def test_analyze_profile_recently_analyzed(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test que salta análisis si fue analizado recientemente (< 30 días)."""
        # Configurar repo para retornar fecha reciente
        recent_date = (datetime.now() - timedelta(days=5)).isoformat()
        mock_profile_repo.get_last_analysis_date.return_value = recent_date
        
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(
            username="testuser",
            fetch_reels=True,
        )
        
        response = use_case(request)
        
        assert response.skipped_recent is True
        assert response.snapshot is None
        
        # No debe llamar al browser
        mock_browser_port.get_profile_snapshot.assert_not_called()
    
    def test_analyze_profile_old_analysis(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test que analiza si el último análisis fue hace > 30 días."""
        # Configurar repo para retornar fecha antigua
        old_date = (datetime.now() - timedelta(days=35)).isoformat()
        mock_profile_repo.get_last_analysis_date.return_value = old_date
        
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(
            username="testuser",
            fetch_reels=True,
        )
        
        response = use_case(request)
        
        assert response.skipped_recent is False
        assert response.snapshot is not None
        
        # Debe llamar al browser
        mock_browser_port.get_profile_snapshot.assert_called_once()
    
    def test_analyze_profile_with_posts(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test de análisis incluyendo posts."""
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(
            username="testuser",
            fetch_reels=True,
            fetch_posts=True,
            max_posts=10,
        )
        
        response = use_case(request)
        
        assert response.recent_posts is not None
        assert len(response.recent_posts) > 0
        
        # Verificar que se llamó get_post_metrics
        mock_browser_port.get_post_metrics.assert_called_once_with("testuser", max_posts=10)
    
    def test_analyze_profile_browser_error(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test que propaga errores del browser."""
        from scrapinsta.domain.ports.browser_port import BrowserNavigationError
        
        error = BrowserNavigationError(
            "Error de navegación",
            username="testuser",
        )
        mock_browser_port.get_profile_snapshot.side_effect = error
        
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(username="testuser")
        
        with pytest.raises(BrowserNavigationError):
            use_case(request)
    
    def test_analyze_profile_normalizes_username(
        self,
        mock_browser_port: Mock,
        mock_profile_repo: Mock,
    ):
        """Test que normaliza el username (quita @, lowercase)."""
        use_case = AnalyzeProfileUseCase(
            browser=mock_browser_port,
            profile_repo=mock_profile_repo,
        )
        
        request = AnalyzeProfileRequest(
            username="@TestUser",  # Con @ y mayúsculas
            fetch_reels=False,
        )
        
        response = use_case(request)
        
        mock_browser_port.get_profile_snapshot.assert_called_once_with("testuser")

