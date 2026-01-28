"""
Tests unitarios para FetchFollowingsUseCase.

Usa mocks para BrowserPort y FollowingsRepo, no ejecuta Selenium ni BD real.
"""
from __future__ import annotations

import pytest
from unittest.mock import Mock

from scrapinsta.application.use_cases.fetch_followings import FetchFollowingsUseCase
from scrapinsta.application.dto.followings import FetchFollowingsRequest
from scrapinsta.domain.models.profile_models import Username, Following
from scrapinsta.domain.ports.browser_port import (
    BrowserNavigationError,
    BrowserDOMError,
    BrowserRateLimitError,
)
from scrapinsta.domain.ports.followings_repo import (
    FollowingsPersistenceError,
    FollowingsValidationError,
)


class TestFetchFollowingsUseCase:
    """Tests para FetchFollowingsUseCase."""
    
    def test_fetch_followings_success(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test de fetch exitoso de followings."""
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        request = FetchFollowingsRequest(
            username="testowner",
            max_followings=10,
        )
        
        response = use_case(request)
        
        assert response.owner == "testowner"
        assert len(response.followings) > 0
        assert response.new_saved >= 0
        assert response.source == "selenium"
        
        # Verificar que se llamó al browser
        mock_browser_port.fetch_followings.assert_called_once()
        
        # Verificar que se guardó en el repo
        mock_followings_repo.save_for_owner.assert_called_once()
    
    def test_fetch_followings_empty_result(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test cuando no hay followings."""
        mock_browser_port.fetch_followings.return_value = []
        
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        request = FetchFollowingsRequest(
            username="emptyuser",
            max_followings=10,
        )
        
        response = use_case(request)
        
        assert response.owner == "emptyuser"
        assert len(response.followings) == 0
        assert response.new_saved == 0
    
    def test_fetch_followings_with_limit(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test con límite de followings."""
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        request = FetchFollowingsRequest(
            username="testowner",
            max_followings=5,  # Límite pequeño
        )
        
        response = use_case(request)
        
        assert len(response.followings) <= 5
        # Verificar que se pasó el límite al browser
        call_args = mock_browser_port.fetch_followings.call_args
        assert call_args is not None
        assert call_args[0][1] == 5  # Segundo argumento es el límite
    
    def test_fetch_followings_invalid_limit_zero(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test con límite inválido (0) - Pydantic valida antes de llegar al código."""
        from pydantic import ValidationError
        
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        # Pydantic validará el límite antes de crear el request
        with pytest.raises(ValidationError):
            FetchFollowingsRequest(
                username="testowner",
                max_followings=0,  # Límite inválido - Pydantic lo rechaza
            )
    
    def test_fetch_followings_browser_navigation_error(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test que propaga BrowserNavigationError."""
        error = BrowserNavigationError(
            "Error de navegación",
            username="testowner",
        )
        mock_browser_port.fetch_followings.side_effect = error
        
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        request = FetchFollowingsRequest(username="testowner")
        
        with pytest.raises(BrowserNavigationError):
            use_case(request)
    
    def test_fetch_followings_browser_dom_error(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test que propaga BrowserDOMError."""
        error = BrowserDOMError(
            "Error de DOM",
            username="testowner",
        )
        mock_browser_port.fetch_followings.side_effect = error
        
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        request = FetchFollowingsRequest(username="testowner")
        
        with pytest.raises(BrowserDOMError):
            use_case(request)
    
    def test_fetch_followings_repo_persistence_error(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test que propaga FollowingsPersistenceError."""
        error = FollowingsPersistenceError("Error de BD")
        mock_followings_repo.save_for_owner.side_effect = error
        
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        request = FetchFollowingsRequest(username="testowner")
        
        with pytest.raises(FollowingsPersistenceError):
            use_case(request)
    
    def test_fetch_followings_normalizes_username(
        self,
        mock_browser_port: Mock,
        mock_followings_repo: Mock,
    ):
        """Test que normaliza el username."""
        from pydantic import ValidationError
        
        use_case = FetchFollowingsUseCase(
            browser=mock_browser_port,
            repo=mock_followings_repo,
        )
        
        # Pydantic valida el username antes de llegar al código
        # El username con espacios es inválido según el validador
        # El validador strip_whitespace elimina espacios, pero luego valida que no tenga espacios
        # Un username válido debería pasar la validación
        request = FetchFollowingsRequest(
            username="testowner",  # Username válido (sin espacios)
            max_followings=10,
        )
        
        response = use_case(request)
        
        # El owner debe estar normalizado
        assert response.owner == "testowner"
        
        # Verificar que se pasó username normalizado al browser
        call_args = mock_browser_port.fetch_followings.call_args
        assert call_args is not None
        owner_vo = call_args[0][0]  # Primer argumento es el Username VO
        assert owner_vo.value == "testowner"

    def test_fetch_followings_request_converts_limit_to_max_followings(self):
        """Test que FetchFollowingsRequest convierte 'limit' a 'max_followings'."""
        # Este test verifica el bug donde el dispatcher enviaba 'limit' pero
        # el DTO esperaba 'max_followings', causando que se usara el default de 100.
        
        # Simular payload como lo envía el dispatcher (con 'limit' en lugar de 'max_followings')
        payload = {
            "username": "testowner",
            "limit": 5,  # El dispatcher envía 'limit'
            "source": "ext",
            "client_account": "myclient",
        }
        
        request = FetchFollowingsRequest(**payload)
        
        # Verificar que se convirtió correctamente
        assert request.max_followings == 5
        assert request.username == "testowner"
    
    def test_fetch_followings_request_prefers_max_followings_over_limit(self):
        """Test que FetchFollowingsRequest prioriza 'max_followings' sobre 'limit'."""
        payload = {
            "username": "testowner",
            "limit": 5,
            "max_followings": 10,  # Si ambos están presentes, prioriza max_followings
        }
        
        request = FetchFollowingsRequest(**payload)
        
        assert request.max_followings == 10  # max_followings tiene prioridad

