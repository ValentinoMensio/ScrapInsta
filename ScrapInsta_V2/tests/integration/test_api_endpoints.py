"""
Tests de integración para endpoints de la API FastAPI.
"""
from __future__ import annotations

import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

import pytest
from fastapi.testclient import TestClient

from scrapinsta.interface.api import app


# =========================================================
# Fixtures
# =========================================================

@pytest.fixture
def mock_job_store() -> Mock:
    """Mock de JobStoreSQL para todos los tests de API."""
    mock = MagicMock()
    
    # Métodos básicos
    mock.pending_jobs.return_value = []
    mock.job_summary.return_value = {"queued": 0, "sent": 0, "ok": 0, "error": 0}
    mock.lease_tasks.return_value = []
    mock.create_job.return_value = None
    mock.add_task.return_value = None
    mock.mark_task_ok.return_value = None
    mock.mark_task_error.return_value = None
    mock.mark_job_done.return_value = None
    mock.all_tasks_finished.return_value = False
    mock.register_message_sent.return_value = None
    
    return mock


@pytest.fixture
def api_client(mock_job_store: Mock, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de FastAPI con JobStore mockeado."""
    monkeypatch.setenv("API_SHARED_SECRET", "test-secret-key")
    monkeypatch.setenv("REQUIRE_HTTPS", "false")
    
    with patch('scrapinsta.interface.api._job_store', mock_job_store):
        with patch('scrapinsta.interface.api.API_SHARED_SECRET', "test-secret-key"):
            with patch('scrapinsta.interface.api._CLIENTS', {}):
                yield TestClient(app)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Headers de autenticación para requests autenticados."""
    return {
        "X-Api-Key": "test-secret-key",
        "X-Account": "test-account"
    }


@pytest.fixture
def auth_headers_bearer() -> Dict[str, str]:
    """Headers de autenticación usando Authorization Bearer."""
    return {
        "Authorization": "Bearer test-secret-key",
        "X-Account": "test-account"
    }


# =========================================================
# Tests: GET /health
# =========================================================

class TestHealthEndpoint:
    """Tests para el endpoint GET /health."""
    
    def test_health_success(self, api_client: TestClient, mock_job_store: Mock):
        """Health check exitoso cuando la BD responde."""
        mock_job_store.pending_jobs.return_value = []
        
        response = api_client.get("/health")
        
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_job_store.pending_jobs.assert_called_once()
    
    def test_health_db_error(self, api_client: TestClient, mock_job_store: Mock):
        """Health check falla cuando la BD tiene error."""
        mock_job_store.pending_jobs.side_effect = Exception("DB connection failed")
        
        response = api_client.get("/health")
        
        assert response.status_code == 200  # Health siempre retorna 200
        assert response.json() == {"ok": False, "error": "DB connection failed"}
    
    def test_health_no_auth_required(self, api_client: TestClient):
        """Health check no requiere autenticación."""
        response = api_client.get("/health")
        assert response.status_code == 200


# =========================================================
# Tests: POST /ext/followings/enqueue
# =========================================================

class TestEnqueueFollowings:
    """Tests para POST /ext/followings/enqueue."""
    
    def test_enqueue_followings_success(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Crear job de followings exitosamente."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].startswith("job:")
        
        mock_job_store.create_job.assert_called_once()
        call_kwargs = mock_job_store.create_job.call_args[1]
        assert call_kwargs["kind"] == "fetch_followings"
        assert call_kwargs["extra"]["limit"] == 10
        assert call_kwargs["extra"]["client_account"] == "test-account"
        
        mock_job_store.add_task.assert_called_once()
        task_call = mock_job_store.add_task.call_args[1]
        assert task_call["username"] == "testuser"
        assert task_call["payload"]["username"] == "testuser"
        assert task_call["payload"]["limit"] == 10
    
    def test_enqueue_followings_without_auth(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla sin autenticación."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Api-Key"}
        
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=headers
        )
        
        assert response.status_code == 401
        assert "API key inválida" in response.json()["detail"]
    
    def test_enqueue_followings_invalid_key(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla con API key inválida."""
        headers = {**auth_headers, "X-Api-Key": "invalid-key"}
        
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=headers
        )
        
        assert response.status_code == 401
    
    def test_enqueue_followings_empty_username(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla con username vacío."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "target_username vacío" in response.json()["detail"]
    
    def test_enqueue_followings_invalid_limit_too_low(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla con limit < 1."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 0},
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error de Pydantic
    
    def test_enqueue_followings_invalid_limit_too_high(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla con limit > 100."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 101},
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error de Pydantic
    
    def test_enqueue_followings_db_error(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Enqueue falla cuando create_job lanza excepción."""
        mock_job_store.create_job.side_effect = Exception("DB error")
        
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 500
        assert "create_job failed" in response.json()["detail"]
    
    def test_enqueue_followings_normalizes_username(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Enqueue normaliza el username a lowercase."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "TestUser", "limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        task_call = mock_job_store.add_task.call_args[1]
        assert task_call["username"] == "testuser"
        assert task_call["payload"]["username"] == "testuser"
    
    def test_enqueue_followings_bearer_auth(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers_bearer: Dict[str, str]
    ):
        """Enqueue funciona con Authorization Bearer."""
        response = api_client.post(
            "/ext/followings/enqueue",
            json={"target_username": "testuser", "limit": 10},
            headers=auth_headers_bearer
        )
        
        assert response.status_code == 200
        assert "job_id" in response.json()


# =========================================================
# Tests: POST /ext/analyze/enqueue
# =========================================================

class TestEnqueueAnalyze:
    """Tests para POST /ext/analyze/enqueue."""
    
    def test_enqueue_analyze_success(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Crear job de análisis exitosamente."""
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
        data = response.json()
        assert "job_id" in data
        assert data["total_items"] == 3
        
        mock_job_store.create_job.assert_called_once()
        call_kwargs = mock_job_store.create_job.call_args[1]
        assert call_kwargs["kind"] == "analyze_profile"
        assert call_kwargs["priority"] == 5
        assert call_kwargs["batch_size"] == 25
        assert call_kwargs["total_items"] == 3
        
        assert mock_job_store.add_task.call_count == 3
    
    def test_enqueue_analyze_empty_usernames(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla con lista de usernames vacía."""
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": []},
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "usernames vacío" in response.json()["detail"]
    
    def test_enqueue_analyze_without_auth(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla sin autenticación."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Api-Key"}
        
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": ["user1"]},
            headers=headers
        )
        
        assert response.status_code == 401
    
    def test_enqueue_analyze_invalid_batch_size(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Enqueue falla con batch_size inválido."""
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": ["user1"], "batch_size": 0},
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_enqueue_analyze_db_error(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Enqueue falla cuando create_job lanza excepción."""
        mock_job_store.create_job.side_effect = Exception("DB error")
        
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": ["user1"]},
            headers=auth_headers
        )
        
        assert response.status_code == 500
        assert "create_job failed" in response.json()["detail"]
    
    def test_enqueue_analyze_normalizes_usernames(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Enqueue normaliza todos los usernames a lowercase."""
        response = api_client.post(
            "/ext/analyze/enqueue",
            json={"usernames": ["User1", "  User2  ", "USER3"]},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        calls = mock_job_store.add_task.call_args_list
        assert len(calls) == 3
        assert calls[0][1]["username"] == "user1"
        assert calls[1][1]["username"] == "user2"
        assert calls[2][1]["username"] == "user3"


# =========================================================
# Tests: GET /jobs/{job_id}/summary
# =========================================================

class TestJobSummary:
    """Tests para GET /jobs/{job_id}/summary."""
    
    def test_job_summary_success(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Obtener resumen de job exitosamente."""
        mock_job_store.job_summary.return_value = {
            "queued": 5,
            "sent": 3,
            "ok": 2,
            "error": 1
        }
        
        response = api_client.get(
            "/jobs/job:123/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] == 5
        assert data["sent"] == 3
        assert data["ok"] == 2
        assert data["error"] == 1
        
        mock_job_store.job_summary.assert_called_once_with("job:123")
    
    def test_job_summary_without_auth(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Job summary falla sin autenticación."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Api-Key"}
        
        response = api_client.get(
            "/jobs/job:123/summary",
            headers=headers
        )
        
        assert response.status_code == 401
    
    def test_job_summary_db_error(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Job summary falla cuando job_summary lanza excepción."""
        mock_job_store.job_summary.side_effect = Exception("DB error")
        
        response = api_client.get(
            "/jobs/job:123/summary",
            headers=auth_headers
        )
        
        assert response.status_code == 500
        assert "job_summary failed" in response.json()["detail"]
    
    def test_job_summary_empty_job_id(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Job summary falla con job_id vacío."""
        response = api_client.get(
            "/jobs//summary",
            headers=auth_headers
        )
        
        assert response.status_code == 404  # FastAPI route not found


# =========================================================
# Tests: POST /api/send/pull
# =========================================================

class TestSendPull:
    """Tests para POST /api/send/pull."""
    
    def test_send_pull_success(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Pull de tareas exitoso."""
        mock_job_store.lease_tasks.return_value = [
            {
                "job_id": "job:123",
                "task_id": "task:456",
                "username": "targetuser",
                "payload": {"message": "Hello"}
            }
        ]
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["job_id"] == "job:123"
        assert data["items"][0]["task_id"] == "task:456"
        assert data["items"][0]["dest_username"] == "targetuser"
        assert data["items"][0]["payload"] == {"message": "Hello"}
        
        mock_job_store.lease_tasks.assert_called_once_with(
            account_id="test-account",
            limit=10
        )
    
    def test_send_pull_empty_result(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Pull retorna lista vacía cuando no hay tareas."""
        mock_job_store.lease_tasks.return_value = []
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["items"] == []
    
    def test_send_pull_without_auth(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Pull falla sin autenticación."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Api-Key"}
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=headers
        )
        
        assert response.status_code == 401
    
    def test_send_pull_without_account(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Pull falla sin X-Account header."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Account"}
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Falta X-Account" in response.json()["detail"]
    
    def test_send_pull_invalid_limit(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Pull falla con limit inválido."""
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 0},
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_send_pull_db_error(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Pull falla cuando lease_tasks lanza excepción."""
        mock_job_store.lease_tasks.side_effect = Exception("DB error")
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=auth_headers
        )
        
        assert response.status_code == 500
        assert "lease_tasks failed" in response.json()["detail"]
    
    def test_send_pull_normalizes_account(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Pull normaliza el X-Account a lowercase."""
        headers = {**auth_headers, "X-Account": "  TestAccount  "}
        
        response = api_client.post(
            "/api/send/pull",
            json={"limit": 10},
            headers=headers
        )
        
        assert response.status_code == 200
        # Verificar que se normalizó el account
        mock_job_store.lease_tasks.assert_called_once()
        call_kwargs = mock_job_store.lease_tasks.call_args[1]
        assert call_kwargs["account_id"] == "testaccount"


# =========================================================
# Tests: POST /api/send/result
# =========================================================

class TestSendResult:
    """Tests para POST /api/send/result."""
    
    def test_send_result_success_ok(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Reporte de resultado exitoso (ok=True)."""
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
            "task:456"
        )
    
    def test_send_result_success_error(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Reporte de resultado con error (ok=False)."""
        mock_job_store.all_tasks_finished.return_value = False
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:123",
                "task_id": "task:456",
                "ok": False,
                "error": "Failed to send"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        
        mock_job_store.mark_task_error.assert_called_once_with(
            "job:123",
            "task:456",
            error="Failed to send"
        )
        
        # No debe registrar en ledger cuando ok=False
        mock_job_store.register_message_sent.assert_not_called()
    
    def test_send_result_closes_job_when_finished(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Result cierra el job cuando todas las tareas están terminadas."""
        mock_job_store.all_tasks_finished.return_value = True
        
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
        mock_job_store.mark_job_done.assert_called_once_with("job:123")
    
    def test_send_result_without_auth(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Result falla sin autenticación."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Api-Key"}
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:123",
                "task_id": "task:456",
                "ok": True
            },
            headers=headers
        )
        
        assert response.status_code == 401
    
    def test_send_result_without_account(
        self, api_client: TestClient, auth_headers: Dict[str, str]
    ):
        """Result falla sin X-Account header."""
        headers = {k: v for k, v in auth_headers.items() if k != "X-Account"}
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:123",
                "task_id": "task:456",
                "ok": True
            },
            headers=headers
        )
        
        assert response.status_code == 400
        assert "Falta X-Account" in response.json()["detail"]
    
    def test_send_result_db_error_mark_task(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Result falla cuando mark_task_ok lanza excepción."""
        mock_job_store.mark_task_ok.side_effect = Exception("DB error")
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:123",
                "task_id": "task:456",
                "ok": True
            },
            headers=auth_headers
        )
        
        assert response.status_code == 500
        assert "mark_task_* failed" in response.json()["detail"]
    
    def test_send_result_ledger_error_does_not_fail(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Result no falla si el ledger tiene error (solo marca la tarea)."""
        mock_job_store.register_message_sent.side_effect = Exception("Ledger error")
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
        
        # Debe retornar 200 aunque el ledger falle
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_send_result_without_dest_username(
        self, api_client: TestClient, mock_job_store: Mock, auth_headers: Dict[str, str]
    ):
        """Result no registra en ledger si no hay dest_username."""
        mock_job_store.all_tasks_finished.return_value = False
        
        response = api_client.post(
            "/api/send/result",
            json={
                "job_id": "job:123",
                "task_id": "task:456",
                "ok": True
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        # No debe registrar en ledger sin dest_username
        mock_job_store.register_message_sent.assert_not_called()

