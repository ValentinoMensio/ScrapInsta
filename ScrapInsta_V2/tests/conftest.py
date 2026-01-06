"""
Configuración global de pytest con fixtures compartidas.

Este archivo proporciona:
- Mocks para repositorios (sin BD real)
- Mocks para Browser/Selenium (sin ejecución real)
- Mocks para OpenAI (sin llamadas reales)
- Configuración de test settings
"""
from __future__ import annotations

from typing import Generator
from unittest.mock import Mock, MagicMock, patch

import pytest

from scrapinsta.config.settings import Settings
from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    PrivacyStatus,
    ReelMetrics,
    PostMetrics,
    BasicStats,
)
from scrapinsta.domain.ports.browser_port import BrowserPort


# =========================================================
# Fixture: Mocks de Repositorios (para tests unitarios)
# =========================================================

@pytest.fixture
def mock_profile_repo() -> Mock:
    """
    Mock de ProfileRepository para tests unitarios.
    
    No usa base de datos real, retorna datos predefinidos.
    """
    from scrapinsta.domain.ports.profile_repo import ProfileRepository
    
    mock = Mock(spec=ProfileRepository)
    
    # get_profile_id
    mock.get_profile_id.return_value = None  # Por defecto no existe
    
    # get_last_analysis_date
    mock.get_last_analysis_date.return_value = None  # Por defecto no hay análisis previo
    
    # upsert_profile
    def mock_upsert_profile(snap: ProfileSnapshot) -> int:
        # Retorna un ID ficticio
        return 1
    
    mock.upsert_profile.side_effect = mock_upsert_profile
    
    # save_analysis_snapshot
    mock.save_analysis_snapshot.return_value = 1
    
    return mock


@pytest.fixture
def mock_followings_repo() -> Mock:
    """
    Mock de FollowingsRepo para tests unitarios.
    
    No usa base de datos real, retorna datos predefinidos.
    """
    from scrapinsta.domain.ports.followings_repo import FollowingsRepo
    
    mock = Mock(spec=FollowingsRepo)
    
    # save_for_owner
    def mock_save_for_owner(owner, followings):
        # Retorna la cantidad de followings (simula que todos son nuevos)
        return len(list(followings))
    
    mock.save_for_owner.side_effect = mock_save_for_owner
    
    # get_for_owner
    mock.get_for_owner.return_value = []
    
    return mock


# =========================================================
# Fixture: Configuración de Test
# =========================================================

@pytest.fixture
def test_settings() -> Settings:
    """
    Configuración de test con valores por defecto.
    
    No se conecta a servicios reales.
    """
    return Settings(
        db_host="127.0.0.1",
        db_port=3307,
        db_user="test",
        db_pass="test",
        db_name="test_db",
        headless=True,
        openai_api_key=None,  # No usar OpenAI real en tests
        accounts=[],  # Sin cuentas reales
    )


# =========================================================
# Fixture: Mock de BrowserPort (sin Selenium real)
# =========================================================

@pytest.fixture
def mock_browser_port() -> Mock:
    """
    Mock completo de BrowserPort que NO ejecuta Selenium.
    
    Retorna datos de prueba predefinidos.
    
    Nota: Usamos spec=BrowserPort pero agregamos detect_rubro manualmente
    porque detect_rubro no está en el protocolo, solo en la implementación.
    """
    # No usamos spec para permitir métodos adicionales como detect_rubro
    mock = Mock()
    
    # get_profile_snapshot
    def mock_get_profile_snapshot(username: str) -> ProfileSnapshot:
        return ProfileSnapshot(
            username=username.lower().strip().lstrip("@"),
            bio=f"Bio de prueba para {username}",
            followers=10000,
            followings=500,
            posts=150,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
    
    mock.get_profile_snapshot.side_effect = mock_get_profile_snapshot
    
    # detect_rubro (no está en el protocolo pero se usa en el código)
    mock.detect_rubro.return_value = "tech"
    
    # get_followings
    mock.get_followings.return_value = [
        "user1", "user2", "user3", "user4", "user5"
    ]
    
    # fetch_followings
    from scrapinsta.domain.models.profile_models import Username
    mock.fetch_followings.return_value = [
        Username(value="user1"),
        Username(value="user2"),
        Username(value="user3"),
    ]
    
    # get_reel_metrics
    def mock_get_reel_metrics(username: str, *, max_reels: int = 12) -> tuple[list[ReelMetrics], BasicStats]:
        reels = [
            ReelMetrics(
                code=f"reel_{i}",
                views=1000 * (i + 1),
                likes=100 * (i + 1),
                comments=10 * (i + 1),
            )
            for i in range(min(max_reels, 5))
        ]
        stats = BasicStats(
            avg_views_last_n=3000.0,
            avg_likes_last_n=300.0,
            avg_comments_last_n=30.0,
        )
        return (reels, stats)
    
    mock.get_reel_metrics.side_effect = mock_get_reel_metrics
    
    # get_post_metrics
    def mock_get_post_metrics(username: str, *, max_posts: int = 30) -> list[PostMetrics]:
        from datetime import datetime, timedelta
        return [
            PostMetrics(
                code=f"post_{i}",
                likes=200 * (i + 1),
                comments=20 * (i + 1),
                published_at=datetime.now() - timedelta(days=i),
            )
            for i in range(min(max_posts, 10))
        ]
    
    mock.get_post_metrics.side_effect = mock_get_post_metrics
    
    # source attribute (usado por fetch_followings)
    mock.source = "selenium"
    
    return mock


# =========================================================
# Fixture: Mock de OpenAI (sin llamadas reales)
# =========================================================

@pytest.fixture
def mock_openai_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """
    Mock de cliente OpenAI que NO hace llamadas reales.
    
    Usa monkeypatch para reemplazar el cliente OpenAI.
    """
    mock_client = Mock()
    
    # Mock de chat.completions.create
    mock_completion = Mock()
    mock_completion.choices = [Mock()]
    mock_completion.choices[0].message = Mock()
    mock_completion.choices[0].message.content = "Mensaje generado por IA para el perfil"
    
    mock_client.chat.completions.create.return_value = mock_completion
    
    # Patch del módulo de OpenAI
    with patch('scrapinsta.infrastructure.ai.chatgpt_openai.OpenAI', return_value=mock_client):
        yield mock_client
    
    return mock_client


# =========================================================
# Fixture: Mock de JobStore (sin BD real)
# =========================================================

@pytest.fixture
def mock_job_store() -> Mock:
    """
    Mock de JobStore para tests que no requieren BD.
    """
    mock = MagicMock()
    mock.create_job.return_value = None
    mock.add_task.return_value = None
    mock.lease_tasks.return_value = []
    mock.mark_task_ok.return_value = None
    mock.mark_task_error.return_value = None
    mock.register_message_sent.return_value = None
    mock.was_message_sent.return_value = False
    mock.was_message_sent_any.return_value = False
    mock.all_tasks_finished.return_value = False
    mock.mark_job_done.return_value = None
    mock.mark_job_running.return_value = None
    mock.job_summary.return_value = {
        "queued": 0,
        "sent": 0,
        "ok": 0,
        "error": 0,
    }
    mock.get_job_client_id.return_value = "default"
    mock.pending_jobs.return_value = []
    mock.pending_jobs.return_value = []
    
    return mock


# =========================================================
# Fixture: Mock de MessageSenderPort
# =========================================================

@pytest.fixture
def mock_message_sender() -> Mock:
    """
    Mock de MessageSenderPort que NO envía mensajes reales.
    """
    from scrapinsta.domain.ports.message_port import MessageSenderPort
    
    mock = Mock(spec=MessageSenderPort)
    mock.send_direct_message.return_value = True  # Simula éxito
    
    return mock


# =========================================================
# Fixture: Mock de MessageComposerPort
# =========================================================

@pytest.fixture
def mock_message_composer() -> Mock:
    """
    Mock de MessageComposerPort que NO usa OpenAI real.
    """
    from scrapinsta.domain.ports.message_port import MessageComposerPort
    
    mock = Mock(spec=MessageComposerPort)
    mock.compose_message.return_value = "Mensaje personalizado de prueba"
    
    return mock


# =========================================================
# Utilidades para tests
# =========================================================

@pytest.fixture(autouse=True)
def disable_external_calls(monkeypatch: pytest.MonkeyPatch):
    """
    Desactiva automáticamente llamadas a servicios externos en todos los tests.
    
    Esto previene que los tests hagan llamadas reales por error.
    """
    # Desactivar requests HTTP reales
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("INSTAGRAM_ACCOUNTS_JSON", "[]")
    
    # NO patch de Selenium aquí - causa problemas con autouse
    # Los tests que necesiten prevenir Selenium deben hacerlo explícitamente
    
    yield
    
    # Cleanup (si es necesario)


# =========================================================
# Helpers para tests (no son fixtures)
# =========================================================

def create_test_profile_snapshot(username: str = "testuser") -> ProfileSnapshot:
    """Helper para crear ProfileSnapshot de prueba."""
    return ProfileSnapshot(
        username=username.lower().strip().lstrip("@"),
        bio="Bio de prueba",
        followers=10000,
        followings=500,
        posts=150,
        is_verified=False,
        privacy=PrivacyStatus.public,
    )


def create_test_reel_metrics(count: int = 3) -> list[ReelMetrics]:
    """Helper para crear ReelMetrics de prueba."""
    return [
        ReelMetrics(
            code=f"reel_{i}",
            views=1000 * (i + 1),
            likes=100 * (i + 1),
            comments=10 * (i + 1),
        )
        for i in range(count)
    ]


# =========================================================
# Fixtures para Tests de Repositorios SQL (Mockeados)
# =========================================================

@pytest.fixture
def mock_db_cursor() -> Mock:
    """
    Mock de cursor de base de datos para tests de repositorios SQL.
    
    Permite configurar:
    - fetchone() retorna un dict o tuple
    - fetchall() retorna lista de dicts o tuples
    - rowcount para INSERT/UPDATE/DELETE
    - execute() y executemany() para validar queries
    """
    mock = Mock()
    mock.fetchone.return_value = None
    mock.fetchall.return_value = []
    mock.rowcount = 0
    mock.execute.return_value = None
    mock.executemany.return_value = None
    return mock


@pytest.fixture
def mock_db_connection(mock_db_cursor: Mock) -> Mock:
    """
    Mock de conexión de base de datos para tests de repositorios SQL.
    
    Retorna una conexión mockeada con:
    - cursor() que retorna el mock_db_cursor
    - commit() y rollback() para transacciones
    - close() para cleanup
    """
    mock = Mock()
    mock.cursor.return_value = mock_db_cursor
    mock.commit.return_value = None
    mock.rollback.return_value = None
    mock.close.return_value = None
    mock._closed = False
    mock.get_autocommit.return_value = False
    mock.ping.return_value = None
    return mock


@pytest.fixture
def mock_conn_factory(mock_db_connection: Mock):
    """
    Factory mockeada que retorna conexiones de BD.
    
    Usado por repositorios que esperan conn_factory: Callable[[], Connection]
    Siempre retorna la misma conexión mockeada (para que los tests puedan configurarla).
    """
    def factory():
        return mock_db_connection
    
    return factory

