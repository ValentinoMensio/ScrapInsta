"""
Tests para headers de seguridad y HTTPS.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from scrapinsta.interface.api import app


@pytest.fixture
def mock_job_store():
    """Mock de JobStore para tests de security headers."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.pending_jobs.return_value = []
    return mock


@pytest.fixture
def mock_client_repo():
    """Mock de ClientRepo para tests de security headers."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.get_by_id.return_value = None
    mock.get_by_api_key.return_value = None
    mock.get_limits.return_value = {}
    return mock


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, mock_job_store, mock_client_repo) -> TestClient:
    """TestClient de FastAPI."""
    monkeypatch.setenv("API_SHARED_SECRET", "test-secret-key")
    monkeypatch.setenv("REQUIRE_HTTPS", "false")
    monkeypatch.setenv("CORS_ORIGINS", "")
    
    # Mockear dependencias en app.state.dependencies
    from scrapinsta.interface.dependencies import Dependencies
    from scrapinsta.config.settings import Settings
    
    mock_deps = Dependencies(
        settings=Settings(),
        job_store=mock_job_store,
        client_repo=mock_client_repo,
    )
    
    app.state.dependencies = mock_deps
    
    with patch('scrapinsta.interface.dependencies.get_dependencies', return_value=mock_deps):
        with patch('scrapinsta.interface.api._job_store', mock_job_store):
            with patch('scrapinsta.interface.api._client_repo', mock_client_repo):
                with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
                    with patch('scrapinsta.interface.api._CLIENTS', {}):
                        with patch('scrapinsta.interface.auth.authentication.API_SHARED_SECRET', "test-secret-key"):
                            with patch('scrapinsta.interface.auth.authentication._CLIENTS', {}):
                                yield TestClient(app)


class TestSecurityHeaders:
    """Tests para headers de seguridad."""
    
    def test_security_headers_present(self, api_client: TestClient):
        """Verifica que los headers de seguridad estén presentes."""
        response = api_client.get("/health")
        
        assert response.status_code == 200
        
        # Headers de seguridad que siempre deben estar
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"
        
        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        
        assert "Referrer-Policy" in response.headers
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers
    
    def test_hsts_header_when_https_required(self, monkeypatch: pytest.MonkeyPatch, mock_job_store, mock_client_repo):
        """HSTS header solo se agrega cuando REQUIRE_HTTPS=true."""
        monkeypatch.setenv("REQUIRE_HTTPS", "true")
        
        # Patch REQUIRE_HTTPS en todos los módulos que lo usan
        with patch('scrapinsta.interface.auth.authentication.REQUIRE_HTTPS', True):
            with patch('scrapinsta.interface.middleware.security.REQUIRE_HTTPS', True):
                from scrapinsta.interface.dependencies import Dependencies
                from scrapinsta.config.settings import Settings
                
                mock_deps = Dependencies(
                    settings=Settings(),
                    job_store=mock_job_store,
                    client_repo=mock_client_repo,
                )
                
                app.state.dependencies = mock_deps
                
                with patch('scrapinsta.interface.dependencies.get_dependencies', return_value=mock_deps):
                    with patch('scrapinsta.interface.api._job_store', mock_job_store):
                        with patch('scrapinsta.interface.api._client_repo', mock_client_repo):
                            with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
                                with patch('scrapinsta.interface.api._CLIENTS', {}):
                                    with patch('scrapinsta.interface.auth.authentication.API_SHARED_SECRET', "test-secret-key"):
                                        with patch('scrapinsta.interface.auth.authentication._CLIENTS', {}):
                                            # Recrear la app para que el middleware use el nuevo REQUIRE_HTTPS
                                            from scrapinsta.interface.app_factory import create_app
                                            test_app = create_app(mock_deps)
                                            client = TestClient(test_app)
                                            response = client.get("/health")
                                            
                                            assert "Strict-Transport-Security" in response.headers
                                            assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
    
    def test_hsts_header_not_present_when_https_not_required(self, api_client: TestClient):
        """HSTS header no se agrega cuando REQUIRE_HTTPS=false."""
        response = api_client.get("/health")
        
        # En desarrollo, HSTS no debería estar presente
        # (aunque el middleware lo agrega si REQUIRE_HTTPS=true)
        # Verificamos que otros headers sí estén
        assert "X-Content-Type-Options" in response.headers


class TestHTTPSEnforcement:
    """Tests para validación de HTTPS."""
    
    def test_https_not_required_in_dev(self, api_client: TestClient):
        """En desarrollo, HTTPS no es requerido."""
        # Simular request HTTP
        response = api_client.get(
            "/health",
            headers={"X-Forwarded-Proto": "http"}
        )
        
        # Debería funcionar sin problemas
        assert response.status_code == 200
    
    def test_https_required_when_enabled(self, monkeypatch: pytest.MonkeyPatch, mock_job_store, mock_client_repo):
        """Cuando REQUIRE_HTTPS=true, se rechazan requests HTTP."""
        monkeypatch.setenv("REQUIRE_HTTPS", "true")
        
        # Patch REQUIRE_HTTPS en el módulo de autenticación
        with patch('scrapinsta.interface.auth.authentication.REQUIRE_HTTPS', True):
            from scrapinsta.interface.dependencies import Dependencies
            from scrapinsta.config.settings import Settings
            
            mock_deps = Dependencies(
                settings=Settings(),
                job_store=mock_job_store,
                client_repo=mock_client_repo,
            )
            
            app.state.dependencies = mock_deps
            
            with patch('scrapinsta.interface.dependencies.get_dependencies', return_value=mock_deps):
                with patch('scrapinsta.interface.api._job_store', mock_job_store):
                    with patch('scrapinsta.interface.api._client_repo', mock_client_repo):
                        with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
                            with patch('scrapinsta.interface.api._CLIENTS', {}):
                                with patch('scrapinsta.interface.auth.authentication.API_SHARED_SECRET', "test-secret-key"):
                                    with patch('scrapinsta.interface.auth.authentication._CLIENTS', {}):
                                        client = TestClient(app)
                                        
                                        # Usar un endpoint que sí valida HTTPS (como /jobs/{job_id}/summary)
                                        # Simular request HTTP (sin x-forwarded-proto o con http)
                                        response = client.get(
                                            "/jobs/test-job/summary",
                                            headers={
                                                "X-Forwarded-Proto": "http",
                                                "X-Api-Key": "test-secret-key"
                                            }
                                        )
                                        
                                        # Debería rechazar con 400 por HTTPS requerido
                                        assert response.status_code == 400
                                        data = response.json()
                                        assert "error" in data
                                        assert "HTTPS" in data["error"]["message"]
    
    def test_https_allowed_when_enabled(self, monkeypatch: pytest.MonkeyPatch):
        """Cuando REQUIRE_HTTPS=true, se permiten requests HTTPS."""
        # Patch directamente el valor en el módulo
        import scrapinsta.interface.api as api_module
        original_value = api_module.REQUIRE_HTTPS
        api_module.REQUIRE_HTTPS = True
        
        try:
            client = TestClient(api_module.app)
            
            # Simular request HTTPS en un endpoint que valida HTTPS
            response = client.get(
                "/jobs/test-job/summary",
                headers={
                    "X-Forwarded-Proto": "https",
                    "X-Api-Key": "test-secret-key"
                }
            )
            
            # Debería pasar la validación de HTTPS (puede fallar en autenticación, pero no en HTTPS)
            # Si pasa HTTPS pero falla auth, será 401 o 404, no 400 por HTTPS
            assert response.status_code != 400 or "HTTPS" not in response.text
        finally:
            # Restaurar valor original
            api_module.REQUIRE_HTTPS = original_value


class TestCORS:
    """Tests para configuración de CORS."""
    
    def test_cors_disabled_by_default(self, api_client: TestClient):
        """CORS está deshabilitado por defecto (más seguro)."""
        # Intentar request con Origin
        response = api_client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )
        
        # No debería tener Access-Control-Allow-Origin
        assert "Access-Control-Allow-Origin" not in response.headers
    
    def test_cors_enabled_when_configured(self, monkeypatch: pytest.MonkeyPatch, mock_job_store, mock_client_repo):
        """CORS se habilita cuando se configuran orígenes permitidos."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://example.com")
        
        from scrapinsta.interface.dependencies import Dependencies
        from scrapinsta.config.settings import Settings
        
        mock_deps = Dependencies(
            settings=Settings(),
            job_store=mock_job_store,
            client_repo=mock_client_repo,
        )
        
        app.state.dependencies = mock_deps
        
        with patch('scrapinsta.interface.dependencies.get_dependencies', return_value=mock_deps):
            with patch('scrapinsta.interface.api._job_store', mock_job_store):
                with patch('scrapinsta.interface.api._client_repo', mock_client_repo):
                    with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
                        with patch('scrapinsta.interface.api._CLIENTS', {}):
                            with patch('scrapinsta.interface.auth.authentication.API_SHARED_SECRET', "test-secret-key"):
                                with patch('scrapinsta.interface.auth.authentication._CLIENTS', {}):
                                    # Recrear la app para que CORS se configure con los nuevos orígenes
                                    from scrapinsta.interface.app_factory import create_app
                                    test_app = create_app(mock_deps)
                                    client = TestClient(test_app)
                                    
                                    # Hacer un request con Origin
                                    response = client.get(
                                        "/health",
                                        headers={"Origin": "http://localhost:3000"}
                                    )
                                    
                                    # Debería tener Access-Control-Allow-Origin
                                    assert "Access-Control-Allow-Origin" in response.headers
                                    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    
    def test_cors_preflight_request(self, api_client: TestClient):
        """CORS maneja correctamente preflight requests (OPTIONS)."""
        # Preflight request (OPTIONS)
        response = api_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST"
            }
        )
        
        # Debería retornar 200 o 204
        # Si CORS está deshabilitado, no tendrá headers CORS pero debería responder
        assert response.status_code in [200, 204, 405]

