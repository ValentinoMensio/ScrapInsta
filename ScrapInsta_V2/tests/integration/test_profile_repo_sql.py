"""
Tests para ProfileRepoSQL con conexión y cursor mockeados.
"""
import pytest
from unittest.mock import Mock, call
from datetime import datetime

from scrapinsta.infrastructure.db.profile_repo_sql import ProfileRepoSQL
from scrapinsta.domain.models.profile_models import ProfileSnapshot, PrivacyStatus, BasicStats, ReelMetrics, PostMetrics
from scrapinsta.domain.ports.profile_repo import ProfilePersistenceError


class TestProfileRepoSQL:
    """Tests para ProfileRepoSQL con mocks de BD."""
    
    def test_get_profile_id_exists(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Obtener ID de perfil existente."""
        mock_db_cursor.fetchone.return_value = {"id": 123}
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_profile_id("testuser")
        
        assert result == 123
        mock_db_cursor.execute.assert_called_once_with(
            "SELECT id FROM profiles WHERE username = %s",
            ("testuser",)
        )
        mock_db_cursor.close.assert_called_once()
        mock_db_connection.close.assert_called_once()
    
    def test_get_profile_id_not_exists(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Obtener ID de perfil que no existe."""
        mock_db_cursor.fetchone.return_value = None
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_profile_id("nonexistent")
        
        assert result is None
        mock_db_cursor.execute.assert_called_once()
    
    def test_get_profile_id_normalizes_username(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Normaliza username a lowercase antes de buscar."""
        mock_db_cursor.fetchone.return_value = None
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        repo.get_profile_id("  TestUser  ")
        
        # Verificar que se normalizó a lowercase
        call_args = mock_db_cursor.execute.call_args
        assert call_args[0][1][0] == "testuser"
    
    def test_get_profile_id_empty_username(self, mock_conn_factory):
        """Retorna None si username está vacío."""
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_profile_id("")
        assert result is None
        
        result = repo.get_profile_id("   ")
        assert result is None
    
    def test_get_profile_id_tuple_result(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Soporta resultado como tuple (compatibilidad con cursores no-DictCursor)."""
        mock_db_cursor.fetchone.return_value = (456,)  # Tuple con id
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_profile_id("testuser")
        
        assert result == 456
    
    def test_get_last_analysis_date_exists(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Obtener fecha de último análisis cuando existe."""
        test_date = datetime(2024, 1, 15, 10, 30, 0)
        mock_db_cursor.fetchone.return_value = {"last_analysis": test_date}
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_last_analysis_date("testuser")
        
        assert result == test_date.isoformat()
        mock_db_cursor.execute.assert_called_once()
        # Verificar que la query incluye JOIN con profiles
        sql_called = mock_db_cursor.execute.call_args[0][0]
        assert "profile_analysis" in sql_called
        assert "profiles" in sql_called
    
    def test_get_last_analysis_date_not_exists(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Retorna None si no hay análisis previo."""
        mock_db_cursor.fetchone.return_value = None
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_last_analysis_date("testuser")
        
        assert result is None
    
    def test_get_last_analysis_date_tuple_result(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Soporta resultado como tuple."""
        test_date = datetime(2024, 1, 15)
        mock_db_cursor.fetchone.return_value = (test_date,)
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        result = repo.get_last_analysis_date("testuser")
        
        assert result == test_date.isoformat()
    
    def test_upsert_profile_insert(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Insertar nuevo perfil."""
        # upsert_profile hace:
        # 1. INSERT en una conexión
        # 2. Llama get_profile_id() que crea nueva conexión y hace SELECT + fetchone
        # get_profile_id() se llama SOLO después del INSERT, así que fetchone debe retornar el ID
        mock_db_cursor.fetchone.return_value = {"id": 789}
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        snapshot = ProfileSnapshot(
            username="newuser",
            bio="Bio test",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        
        result = repo.upsert_profile(snapshot)
        
        assert result == 789
        # Verificar que se llamó INSERT con ON DUPLICATE KEY UPDATE
        # Buscar la llamada que contiene INSERT
        insert_calls = [c for c in mock_db_cursor.execute.call_args_list 
                       if c and len(c[0]) > 0 and "INSERT INTO profiles" in str(c[0][0])]
        assert len(insert_calls) > 0, "No se encontró llamada a INSERT INTO profiles"
        sql_called = insert_calls[0][0][0]
        assert "INSERT INTO profiles" in sql_called
        assert "ON DUPLICATE KEY UPDATE" in sql_called
        mock_db_connection.commit.assert_called()
    
    def test_upsert_profile_update(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Actualizar perfil existente."""
        # get_profile_id retorna ID existente (tanto antes como después del UPDATE)
        mock_db_cursor.fetchone.return_value = {"id": 999}
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        snapshot = ProfileSnapshot(
            username="existinguser",
            bio="Updated bio",
            followers=2000,
            followings=600,
            posts=150,
            is_verified=True,
            privacy=PrivacyStatus.private,
        )
        
        result = repo.upsert_profile(snapshot)
        
        assert result == 999
        # Verificar que se pasaron los valores correctos en el INSERT/UPDATE
        # Buscar la llamada que contiene INSERT INTO profiles
        insert_calls = [call for call in mock_db_cursor.execute.call_args_list 
                       if "INSERT INTO profiles" in call[0][0]]
        assert len(insert_calls) > 0
        params = insert_calls[0][0][1]
        assert params[0] == "existinguser"  # username normalizado
        assert params[1] == "Updated bio"
        assert params[2] == 2000  # followers
        assert params[6] == "private"  # privacy.value
    
    def test_upsert_profile_invalid_username(self, mock_conn_factory):
        """Lanza ValueError si username es inválido (solo espacios)."""
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        # Usar solo espacios, que pasa validación de Pydantic pero el repo lo rechaza
        snapshot = ProfileSnapshot(
            username="   ",  # Solo espacios (pasa Pydantic pero repo lo rechaza)
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        
        with pytest.raises(ValueError, match="username inválido"):
            repo.upsert_profile(snapshot)
    
    def test_upsert_profile_db_error(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Maneja errores de BD y lanza ProfilePersistenceError."""
        mock_db_cursor.execute.side_effect = Exception("DB connection lost")
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        snapshot = ProfileSnapshot(
            username="testuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        
        with pytest.raises(ProfilePersistenceError):
            repo.upsert_profile(snapshot)
        
        mock_db_connection.rollback.assert_called_once()
    
    def test_save_analysis_snapshot(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Guardar snapshot de análisis."""
        mock_db_cursor.fetchone.return_value = {"id": 555}
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        snapshot = ProfileSnapshot(
            username="testuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        basic_stats = BasicStats(
            avg_views_last_n=5000.0,
            avg_likes_last_n=500.0,
            avg_comments_last_n=50.0,
            engagement_score=0.15,
            success_score=0.85,
        )
        
        result = repo.save_analysis_snapshot(
            profile_id=123,
            snapshot=snapshot,
            basic=basic_stats,
            reels=None,
            posts=None,
        )
        
        assert result == 555
        # Verificar que se insertó en profile_analysis
        sql_called = mock_db_cursor.execute.call_args_list[0][0][0]
        assert "INSERT INTO profile_analysis" in sql_called
        # Verificar parámetros
        params = mock_db_cursor.execute.call_args_list[0][0][1]
        assert params[0] == 123  # profile_id
        assert params[1] == "selenium"  # source
        assert params[3] == 0.15  # engagement_score
        assert params[4] == 0.85  # success_score
        
        # Verificar que se obtuvo LAST_INSERT_ID
        assert mock_db_cursor.execute.call_count == 2
        assert "LAST_INSERT_ID" in mock_db_cursor.execute.call_args_list[1][0][0]
        mock_db_connection.commit.assert_called_once()
    
    def test_save_analysis_snapshot_without_basic_stats(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Guardar snapshot sin BasicStats."""
        mock_db_cursor.fetchone.return_value = {"id": 666}
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        snapshot = ProfileSnapshot(
            username="testuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        
        result = repo.save_analysis_snapshot(
            profile_id=123,
            snapshot=snapshot,
            basic=None,
            reels=None,
            posts=None,
        )
        
        assert result == 666
        # Verificar que engagement_score y success_score son None
        params = mock_db_cursor.execute.call_args_list[0][0][1]
        assert params[3] is None  # engagement_score
        assert params[4] is None  # success_score
    
    def test_save_analysis_snapshot_db_error(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Maneja errores de BD al guardar análisis."""
        mock_db_cursor.execute.side_effect = Exception("DB error")
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = ProfileRepoSQL(conn_factory=mock_conn_factory)
        snapshot = ProfileSnapshot(
            username="testuser",
            bio="Bio",
            followers=1000,
            followings=500,
            posts=100,
            is_verified=False,
            privacy=PrivacyStatus.public,
        )
        
        with pytest.raises(ProfilePersistenceError):
            repo.save_analysis_snapshot(
                profile_id=123,
                snapshot=snapshot,
                basic=None,
                reels=None,
                posts=None,
            )
        
        mock_db_connection.rollback.assert_called_once()

