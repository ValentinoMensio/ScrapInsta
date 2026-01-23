"""
Tests para endpoints de autenticación.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi.testclient import TestClient

from scrapinsta.interface.api import app
from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_error_message(response) -> str:
    """Helper para obtener el mensaje de error del nuevo formato."""
    data = response.json()
    if "error" in data:
        return data["error"].get("message", "")
    # Fallback para formato antiguo
    return data.get("detail", "")


@pytest.fixture
def mock_client_repo():
    """Mock de ClientRepoSQL."""
    mock = MagicMock()
    # Configurar valores por defecto
    mock.get_by_id.return_value = None
    mock.get_by_api_key.return_value = None
    mock.get_limits.return_value = {}
    return mock


@pytest.fixture
def api_client(mock_client_repo, mock_job_store: Mock, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de FastAPI con repos mockeados."""
    monkeypatch.setenv("API_SHARED_SECRET", "test-secret-key")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    monkeypatch.setenv("REQUIRE_HTTPS", "false")
    
    # Mockear dependencias en app.state.dependencies (nuevo sistema)
    from scrapinsta.interface.dependencies import Dependencies
    from scrapinsta.config.settings import Settings
    
    mock_deps = Dependencies(
        settings=Settings(),
        job_store=mock_job_store,
        client_repo=mock_client_repo,
    )
    
    # Actualizar app.state.dependencies con el mock
    app.state.dependencies = mock_deps
    
    # Configurar mocks básicos
    mock_job_store.pending_jobs.return_value = []
    mock_job_store.job_summary.return_value = {"queued": 0, "sent": 0, "ok": 0, "error": 0}
    mock_job_store.lease_tasks.return_value = []
    mock_job_store.get_job_client_id.return_value = "default"
    
    # Mockear get_dependencies() y variables globales
    with patch('scrapinsta.interface.dependencies.get_dependencies', return_value=mock_deps):
        with patch('scrapinsta.interface.api._job_store', mock_job_store):
            with patch('scrapinsta.interface.api._client_repo', mock_client_repo):
                with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
                    with patch('scrapinsta.interface.api._CLIENTS', {}):
                        with patch('scrapinsta.interface.auth.authentication.API_SHARED_SECRET', "test-secret-key"):
                            with patch('scrapinsta.interface.auth.authentication._CLIENTS', {}):
                                yield TestClient(app)


class TestLoginEndpoint:
    """Tests para POST /api/auth/login."""
    
    def test_login_success(self, api_client: TestClient, mock_client_repo: Mock):
        """Login exitoso con API key válida."""
        api_key = "testkey123"
        
        mock_client_repo.get_by_api_key.return_value = {
            "id": "client1",
            "name": "Test Client",
            "status": "active"
        }
        
        response = api_client.post(
            "/api/auth/login",
            json={"api_key": api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600
        assert data["client_id"] == "client1"
        mock_client_repo.get_by_api_key.assert_called_once_with(api_key)
    
    def test_login_invalid_api_key(self, api_client: TestClient, mock_client_repo: Mock):
        """Login falla con API key inválida."""
        mock_client_repo.get_by_api_key.return_value = None
        
        response = api_client.post(
            "/api/auth/login",
            json={"api_key": "invalid-key"}
        )
        
        assert response.status_code == 401
        assert "API key inválida" in get_error_message(response)
    
    def test_login_suspended_client(self, api_client: TestClient, mock_client_repo: Mock):
        """Login falla con cliente suspendido."""
        api_key = "testkey123"
        
        mock_client_repo.get_by_api_key.return_value = {
            "id": "client1",
            "status": "suspended"
        }
        
        response = api_client.post(
            "/api/auth/login",
            json={"api_key": api_key}
        )
        
        assert response.status_code == 403
        assert "suspendido" in get_error_message(response).lower() or "no está activo" in get_error_message(response).lower()
    
    def test_login_deleted_client(self, api_client: TestClient, mock_client_repo: Mock):
        """Login falla con cliente eliminado."""
        api_key = "testkey123"
        
        mock_client_repo.get_by_api_key.return_value = {
            "id": "client1",
            "status": "deleted"
        }
        
        response = api_client.post(
            "/api/auth/login",
            json={"api_key": api_key}
        )
        
        assert response.status_code == 403


class TestJWTAuthentication:
    """Tests para autenticación JWT."""
    
    def test_jwt_token_valid(self, api_client: TestClient, mock_client_repo: Mock):
        """JWT token válido permite acceso."""
        api_key = "testkey123"
        
        mock_client_repo.get_by_api_key.return_value = {
            "id": "client1",
            "status": "active"
        }
        
        login_response = api_client.post(
            "/api/auth/login",
            json={"api_key": api_key}
        )
        token = login_response.json()["access_token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        response = api_client.get(
            "/health",
            headers=headers
        )
        
        assert response.status_code == 200
    
    def test_jwt_token_invalid(self, api_client: TestClient):
        """JWT token inválido rechaza acceso."""
        headers = {"Authorization": "Bearer invalid-token", "X-Account": "test-account"}
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=headers
        )
        
        assert response.status_code == 401
        error_msg = get_error_message(response)
        assert "Token inválido" in error_msg or "API key inválida" in error_msg
    
    def test_jwt_token_missing(self, api_client: TestClient):
        """Sin JWT token, cae a API key."""
        headers = {"X-Api-Key": "test-secret-key", "X-Account": "test-account"}
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=headers
        )
        
        assert response.status_code in [200, 401]


class TestOwnershipValidation:
    """Tests para validación de ownership."""
    
    def test_job_summary_own_job(self, api_client: TestClient, mock_job_store: Mock, mock_client_repo: Mock):
        """Cliente puede acceder a su propio job."""
        mock_job_store.get_job_client_id.return_value = "default"
        mock_job_store.job_summary.return_value = {
            "queued": 5,
            "sent": 3,
            "ok": 2,
            "error": 1
        }
        
        headers = {"X-Api-Key": "test-secret-key"}
        
        response = api_client.get(
            "/jobs/job:123/summary",
            headers=headers
        )
        
        assert response.status_code == 200
    
    def test_job_summary_other_client_job(self, api_client: TestClient, mock_job_store: Mock, mock_client_repo: Mock):
        """Cliente no puede acceder a job de otro cliente."""
        mock_job_store.get_job_client_id.return_value = "client2"
        mock_client_repo.get_by_id.return_value = {"id": "default", "status": "active"}
        mock_client_repo.get_limits.return_value = {"requests_per_minute": 60}
        
        headers = {"X-Api-Key": "test-secret-key"}
        
        response = api_client.get(
            "/jobs/job:123/summary",
            headers=headers
        )
        
        assert response.status_code == 403
        error_msg = get_error_message(response)
        assert "acceso" in error_msg.lower() or "pertenece" in error_msg.lower()
    
    def test_job_summary_job_not_found(self, api_client: TestClient, mock_job_store: Mock):
        """Job no encontrado retorna 404."""
        mock_job_store.get_job_client_id.return_value = None
        
        headers = {"X-Api-Key": "test-secret-key"}
        
        with patch("scrapinsta.interface.api._auth_client") as mock_auth:
            mock_auth.return_value = {"id": "client1", "scopes": ["fetch"], "rate": 60}
            
            response = api_client.get(
                "/jobs/job:123/summary",
                headers=headers
            )
        
        assert response.status_code == 404


class TestClientIdFiltering:
    """Tests para filtrado por client_id."""
    
    def test_lease_tasks_filters_by_client_id(self, api_client: TestClient, mock_job_store: Mock, mock_client_repo: Mock):
        """lease_tasks filtra tareas por client_id."""
        mock_job_store.lease_tasks.return_value = []
        
        headers = {
            "X-Api-Key": "test-secret-key",
            "X-Account": "test-account"
        }
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=headers
        )
        
        assert response.status_code == 200
        mock_job_store.lease_tasks.assert_called_once()
        call_kwargs = mock_job_store.lease_tasks.call_args[1]
        assert call_kwargs["client_id"] == "default"
    
    def test_job_summary_filters_by_client_id(self, api_client: TestClient, mock_job_store: Mock, mock_client_repo: Mock):
        """job_summary filtra por client_id."""
        mock_job_store.get_job_client_id.return_value = "default"
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 0,
            "error": 0
        }
        mock_client_repo.get_by_id.return_value = {"id": "default", "status": "active"}
        mock_client_repo.get_limits.return_value = {"requests_per_minute": 60}
        
        headers = {"X-Api-Key": "test-secret-key"}
        
        response = api_client.get(
            "/jobs/job:123/summary",
            headers=headers
        )
        
        assert response.status_code == 200
        mock_job_store.job_summary.assert_called_once()
        call_kwargs = mock_job_store.job_summary.call_args[1]
        assert call_kwargs["client_id"] == "default"

