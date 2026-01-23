"""
Tests end-to-end para flujos completos desde API hasta persistencia.
"""
from __future__ import annotations

from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

import pytest
from fastapi.testclient import TestClient

from scrapinsta.interface.api import app
from scrapinsta.domain.models.profile_models import ProfileSnapshot, PrivacyStatus, Username, Following


# =========================================================
# Fixtures
# =========================================================

@pytest.fixture
def mock_job_store() -> Mock:
    """Mock de JobStoreSQL para tests E2E."""
    mock = MagicMock()
    
    mock.pending_jobs.return_value = []
    mock.job_summary.return_value = {"queued": 0, "sent": 0, "ok": 0, "error": 0}
    mock.lease_tasks.return_value = []
    mock.create_job.return_value = None
    mock.add_task.return_value = None
    mock.mark_task_ok.return_value = None
    mock.mark_task_error.return_value = None
    mock.mark_job_done.return_value = None
    mock.mark_job_running.return_value = None
    mock.all_tasks_finished.return_value = False
    mock.register_message_sent.return_value = None
    mock.was_message_sent.return_value = False
    mock.get_job_client_id.return_value = "default"
    
    return mock


@pytest.fixture
def mock_profile_repo() -> Mock:
    """Mock de ProfileRepository para tests E2E."""
    mock = Mock()
    mock.get_profile_id.return_value = None
    mock.get_last_analysis_date.return_value = None
    mock.upsert_profile.return_value = 1
    mock.save_analysis_snapshot.return_value = 1
    return mock


@pytest.fixture
def mock_followings_repo() -> Mock:
    """Mock de FollowingsRepo para tests E2E."""
    mock = Mock()
    mock.save_for_owner.return_value = 5  # 5 followings guardados
    mock.get_for_owner.return_value = []
    return mock


@pytest.fixture
def mock_browser_port() -> Mock:
    """Mock de BrowserPort para tests E2E."""
    mock = Mock()
    
    # Mock de ProfileSnapshot
    mock_snapshot = ProfileSnapshot(
        username="testuser",
        bio="Test bio",
        followers=1000,
        followings=500,
        posts=100,
        is_verified=False,
        privacy=PrivacyStatus.public
    )
    mock.get_profile_snapshot.return_value = mock_snapshot
    
    # Mock de followings
    mock_followings = [
        Following(owner=Username(value="testuser"), target=Username(value="user1")),
        Following(owner=Username(value="testuser"), target=Username(value="user2")),
        Following(owner=Username(value="testuser"), target=Username(value="user3")),
    ]
    mock.get_followings.return_value = mock_followings
    
    return mock


@pytest.fixture
def mock_message_sender() -> Mock:
    """Mock de MessageSenderPort para tests E2E."""
    mock = Mock()
    mock.send_direct_message.return_value = None
    return mock


@pytest.fixture
def mock_message_composer() -> Mock:
    """Mock de MessageComposerPort para tests E2E."""
    mock = Mock()
    mock.compose_message.return_value = "Mensaje generado por IA"
    return mock


@pytest.fixture
def mock_client_repo() -> Mock:
    """Mock de ClientRepo para tests E2E."""
    mock = MagicMock()
    mock.get_by_id.return_value = None
    mock.get_by_api_key.return_value = None
    mock.get_limits.return_value = {}
    return mock


@pytest.fixture
def api_client(mock_job_store: Mock, mock_client_repo: Mock, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    TestClient de FastAPI con JobStore y ClientRepo mockeados.
    
    Usa el nuevo sistema de dependencias con app.state.dependencies.
    """
    # Configurar variables de entorno para autenticación
    monkeypatch.setenv("API_SHARED_SECRET", "test-secret-key")
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
    
    # Mockear get_dependencies() y variables globales
    with patch('scrapinsta.interface.dependencies.get_dependencies', return_value=mock_deps):
        with patch('scrapinsta.interface.api._job_store', mock_job_store):
            with patch('scrapinsta.interface.api._client_repo', mock_client_repo):
                with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
                    with patch('scrapinsta.interface.api._CLIENTS', {}):
                        with patch('scrapinsta.interface.auth.authentication.API_SHARED_SECRET', "test-secret-key"):
                            with patch('scrapinsta.interface.auth.authentication._CLIENTS', {}):
                                yield TestClient(app)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Headers de autenticación."""
    return {
        "X-Api-Key": "test-secret-key",
        "X-Account": "test-account"
    }


# =========================================================
# Tests: Flujo completo de Fetch Followings
# =========================================================

class TestCompleteFetchFlow:
    """Tests E2E para flujo completo de fetch followings."""
    
    def test_complete_fetch_flow(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        mock_followings_repo: Mock,
        mock_browser_port: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo: crear job → procesar → consultar resultado."""
        # Crear job de fetch followings vía API
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        job_data = response.json()
        job_id = job_data["job_id"]
        assert job_id.startswith("job:")
        
        mock_job_store.create_job.assert_called_once()
        create_job_call = mock_job_store.create_job.call_args[1]
        assert create_job_call["kind"] == "fetch_followings"
        assert create_job_call["extra"]["limit"] == 10
        assert create_job_call["extra"]["client_account"] == "test-account"
        assert create_job_call["extra"]["target_username"] == "testuser"
        
        # Arquitectura: la API no crea tasks; el dispatcher/router lo hace.
        mock_job_store.add_task.assert_not_called()
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 1,
            "ok": 0,
            "error": 0
        }
        
        # 3. Consultar estado del job
        response = api_client.get(
            f"/jobs/{job_id}/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        summary = response.json()
        assert summary["sent"] == 1
        assert summary["queued"] == 0
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 1,
            "error": 0
        }
        
        response = api_client.get(
            f"/jobs/{job_id}/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        summary = response.json()
        assert summary["ok"] == 1
        assert summary["sent"] == 0
        assert summary["queued"] == 0
    
    def test_complete_fetch_flow_with_error(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo con error en el procesamiento."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 0,
            "error": 1
        }
        
        response = api_client.get(
            f"/jobs/{job_id}/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        summary = response.json()
        assert summary["error"] == 1
        assert summary["ok"] == 0


# =========================================================
# Tests: Flujo completo de Análisis
# =========================================================

class TestCompleteAnalyzeFlow:
    """Tests E2E para flujo completo de análisis de perfiles."""
    
    def test_complete_analyze_flow(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        mock_profile_repo: Mock,
        mock_browser_port: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo de análisis: crear job → procesar → consultar resultado."""
        # Crear job de análisis vía API
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={
                "usernames": ["user1", "user2", "user3"],
                "batch_size": 25,
                "priority": 5
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        job_data = response.json()
        job_id = job_data["job_id"]
        assert job_data["total_items"] == 3
        
        mock_job_store.create_job.assert_called_once()
        create_job_call = mock_job_store.create_job.call_args[1]
        assert create_job_call["kind"] == "analyze_profile"
        assert create_job_call["priority"] == 5
        assert create_job_call["batch_size"] == 25
        assert create_job_call["total_items"] == 3
        assert create_job_call["extra"]["usernames"] == ["user1", "user2", "user3"]
        mock_job_store.add_task.assert_not_called()
        
        mock_job_store.job_summary.return_value = {
            "queued": 1,
            "sent": 1,
            "ok": 1,
            "error": 0
        }
        
        # 3. Consultar estado del job
        response = api_client.get(
            f"/jobs/{job_id}/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        summary = response.json()
        assert summary["queued"] == 1
        assert summary["sent"] == 1
        assert summary["ok"] == 1
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 3,
            "error": 0
        }
        
        response = api_client.get(
            f"/jobs/{job_id}/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        summary = response.json()
        assert summary["ok"] == 3
        assert summary["queued"] == 0
        assert summary["sent"] == 0
    
    def test_complete_analyze_flow_partial_success(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo con éxito parcial."""
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": ["user1", "user2", "user3"]},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 2,
            "error": 1
        }
        
        response = api_client.get(
            f"/jobs/{job_id}/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        summary = response.json()
        assert summary["ok"] == 2
        assert summary["error"] == 1


# =========================================================
# Tests: Flujo completo de Envío de Mensajes
# =========================================================

class TestCompleteSendMessageFlow:
    """Tests E2E para flujo completo de envío de mensajes."""
    
    def test_complete_send_message_flow(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        mock_message_sender: Mock,
        mock_message_composer: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo de envío de mensajes: pull → procesar → result."""
        mock_job_store.lease_tasks.return_value = [
            {
                "job_id": "job:123",
                "task_id": "task:456",
                "username": "targetuser",
                "payload": {"username": "targetuser", "message_text": "Hello"}
            }
        ]
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        pull_data = response.json()
        assert len(pull_data["items"]) == 1
        assert pull_data["items"][0]["job_id"] == "job:123"
        assert pull_data["items"][0]["task_id"] == "task:456"
        assert pull_data["items"][0]["dest_username"] == "targetuser"
        
        mock_job_store.lease_tasks.assert_called_once_with(
            account_id="test-account",
            limit=10,
            client_id="default"
        )
        
        mock_job_store.all_tasks_finished.return_value = False
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:123",
                "task_id": "task:456",
                "ok": True,
                "dest_username": "targetuser"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        
        mock_job_store.mark_task_ok.assert_called_once_with(
            "job:123",
            "task:456",
            result=None
        )
        
        mock_job_store.register_message_sent.assert_called_once_with(
            "test-account",
            "targetuser",
            "job:123",
            "task:456",
            client_id="default"
        )
    
    def test_complete_send_message_flow_with_error(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo con error en el envío."""
        mock_job_store.lease_tasks.return_value = [
            {
                "job_id": "job:123",
                "task_id": "task:456",
                "username": "targetuser",
                "payload": {"username": "targetuser"}
            }
        ]
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        task = response.json()["items"][0]
        
        mock_job_store.all_tasks_finished.return_value = False
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": task["job_id"],
                "task_id": task["task_id"],
                "ok": False,
                "error": "Failed to send message"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        
        mock_job_store.mark_task_error.assert_called_once_with(
            task["job_id"],
            task["task_id"],
            error="Failed to send message"
        )
        
        mock_job_store.register_message_sent.assert_not_called()
    
    def test_complete_send_message_flow_job_completion(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo que cierra el job cuando todas las tareas están completadas."""
        mock_job_store.lease_tasks.return_value = [
            {
                "job_id": "job:123",
                "task_id": "task:456",
                "username": "targetuser",
                "payload": {"username": "targetuser"}
            }
        ]
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        task = response.json()["items"][0]
        
        mock_job_store.all_tasks_finished.return_value = True
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": task["job_id"],
                "task_id": task["task_id"],
                "ok": True,
                "dest_username": "targetuser"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        
        mock_job_store.mark_job_done.assert_called_once_with(task["job_id"])
    
    def test_complete_send_message_flow_empty_pull(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo completo cuando no hay tareas disponibles."""
        mock_job_store.lease_tasks.return_value = []
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        pull_data = response.json()
        assert pull_data["items"] == []
        
        mock_job_store.lease_tasks.assert_called_once_with(
            account_id="test-account",
            limit=10,
            client_id="default"
        )


# =========================================================
# Tests: Flujo completo integrado (múltiples pasos)
# =========================================================

class TestCompleteIntegratedFlow:
    """Tests E2E para flujos integrados que combinan múltiples operaciones."""
    
    def test_fetch_then_analyze_flow(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo integrado: fetch followings → analyze profiles."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        fetch_job_id = response.json()["job_id"]
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 1,
            "error": 0
        }
        
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={
                "usernames": ["user1", "user2", "user3"],
                "batch_size": 25,
                "priority": 5
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        analyze_job_id = response.json()["job_id"]
        
        assert mock_job_store.create_job.call_count == 2
        
        mock_job_store.get_job_client_id.return_value = "default"
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 1,
            "error": 0
        }
        response = api_client.get(
            f"/jobs/{fetch_job_id}/summary",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["ok"] == 1
        
        response = api_client.get(
            f"/jobs/{analyze_job_id}/summary",
            headers=auth_headers
        )
        assert response.status_code == 200
        summary = response.json()
        assert "queued" in summary or "ok" in summary or "sent" in summary
    
    def test_analyze_then_send_flow(
        self,
        api_client: TestClient,
        mock_job_store: Mock,
        auth_headers: Dict[str, str]
    ):
        """Flujo integrado: analyze → send messages."""
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": ["user1", "user2"]},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        analyze_job_id = response.json()["job_id"]
        
        mock_job_store.job_summary.return_value = {
            "queued": 0,
            "sent": 0,
            "ok": 2,
            "error": 0
        }
        
        mock_job_store.lease_tasks.return_value = [
            {
                "job_id": "job:send123",
                "task_id": "task:send456",
                "username": "user1",
                "payload": {"username": "user1", "message_text": "Hello"}
            }
        ]
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        
        mock_job_store.all_tasks_finished.return_value = False
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:send123",
                "task_id": "task:send456",
                "ok": True,
                "dest_username": "user1"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

