"""
Tests para FollowingsRepoSQL con conexión y cursor mockeados.
"""
import pytest
from unittest.mock import Mock

from scrapinsta.infrastructure.db.followings_repo_sql import FollowingsRepoSQL
from scrapinsta.domain.models.profile_models import Following, Username
from scrapinsta.domain.ports.followings_repo import FollowingsPersistenceError


class TestFollowingsRepoSQL:
    """Tests para FollowingsRepoSQL con mocks de BD."""
    
    def test_save_for_owner_mysql_insert_ignore(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Guardar followings con MySQL (INSERT IGNORE)."""
        mock_db_cursor.rowcount = 5  # 5 filas insertadas
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory, dialect="mysql")
        owner = Username(value="owner_user")
        followings = [
            Following(owner=owner, target=Username(value="target1")),
            Following(owner=owner, target=Username(value="target2")),
            Following(owner=owner, target=Username(value="target3")),
            Following(owner=owner, target=Username(value="target4")),
            Following(owner=owner, target=Username(value="target5")),
        ]
        
        result = repo.save_for_owner(owner, followings)
        
        assert result == 5
        sql_called = mock_db_cursor.executemany.call_args[0][0]
        assert "INSERT IGNORE" in sql_called
        assert "followings" in sql_called
        mock_db_connection.commit.assert_called_once()
    
    def test_save_for_owner_postgres_on_conflict(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Guardar followings con Postgres (ON CONFLICT DO NOTHING)."""
        mock_db_cursor.rowcount = 3
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory, dialect="postgres")
        owner = Username(value="owner_user")
        followings = [
            Following(owner=owner, target=Username(value="target1")),
            Following(owner=owner, target=Username(value="target2")),
            Following(owner=owner, target=Username(value="target3")),
        ]
        
        result = repo.save_for_owner(owner, followings)
        
        assert result == 3
        # Verificar que se usó ON CONFLICT
        sql_called = mock_db_cursor.executemany.call_args[0][0]
        assert "ON CONFLICT" in sql_called
        assert "DO NOTHING" in sql_called
    
    def test_save_for_owner_empty_list(self, mock_conn_factory):
        """Retorna 0 si la lista está vacía."""
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        
        result = repo.save_for_owner(owner, [])
        
        assert result == 0
    
    def test_save_for_owner_idempotent(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """INSERT IGNORE/ON CONFLICT hace que sea idempotente (duplicados no se insertan)."""
        mock_db_cursor.rowcount = 2
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory, dialect="mysql")
        owner = Username(value="owner_user")
        followings = [
            Following(owner=owner, target=Username(value="target1")),
            Following(owner=owner, target=Username(value="target2")),
            Following(owner=owner, target=Username(value="target3")),
            Following(owner=owner, target=Username(value="target4")),
            Following(owner=owner, target=Username(value="target5")),
        ]
        
        result = repo.save_for_owner(owner, followings)
        
        assert result == 2  # Solo 2 nuevos, 3 ya existían
    
    def test_save_for_owner_db_error(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Maneja errores de BD y lanza FollowingsPersistenceError."""
        mock_db_cursor.executemany.side_effect = Exception("DB connection lost")
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        followings = [
            Following(owner=owner, target=Username(value="target1")),
        ]
        
        with pytest.raises(FollowingsPersistenceError):
            repo.save_for_owner(owner, followings)
        
        mock_db_connection.rollback.assert_called_once()
    
    def test_save_for_owner_invalid_dialect(self, mock_conn_factory):
        """Lanza ValueError si dialect no es válido."""
        with pytest.raises(ValueError, match="dialect must be 'mysql' or 'postgres'"):
            FollowingsRepoSQL(conn_factory=mock_conn_factory, dialect="invalid")
    
    def test_get_for_owner(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Obtener followings de un owner."""
        mock_db_cursor.fetchall.return_value = [
            ("owner_user", "target1"),
            ("owner_user", "target2"),
            ("owner_user", "target3"),
        ]
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        
        result = repo.get_for_owner(owner)
        
        assert len(result) == 3
        assert all(isinstance(f, Following) for f in result)
        assert result[0].owner.value == "owner_user"
        assert result[0].target.value == "target1"
        assert result[1].target.value == "target2"
        assert result[2].target.value == "target3"
        
        # Verificar query
        sql_called = mock_db_cursor.execute.call_args[0][0]
        assert "SELECT username_origin, username_target" in sql_called
        assert "FROM followings" in sql_called
        assert "WHERE username_origin = %s" in sql_called
    
    def test_get_for_owner_with_limit(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Obtener followings con límite."""
        mock_db_cursor.fetchall.return_value = [
            ("owner_user", "target1"),
            ("owner_user", "target2"),
        ]
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        
        result = repo.get_for_owner(owner, limit=2)
        
        assert len(result) == 2
        # Verificar que se agregó LIMIT
        sql_called = mock_db_cursor.execute.call_args[0][0]
        assert "LIMIT" in sql_called
        # Verificar parámetros
        params = mock_db_cursor.execute.call_args[0][1]
        assert params[0] == "owner_user"
        assert params[1] == 2
    
    def test_get_for_owner_empty(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Retorna lista vacía si no hay followings."""
        mock_db_cursor.fetchall.return_value = []
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        
        result = repo.get_for_owner(owner)
        
        assert result == []
    
    def test_get_for_owner_limit_zero(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """No aplica LIMIT si es 0 o None."""
        mock_db_cursor.fetchall.return_value = []
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        
        repo.get_for_owner(owner, limit=0)
        sql_called = mock_db_cursor.execute.call_args[0][0]
        assert "LIMIT" not in sql_called
        
        repo.get_for_owner(owner, limit=None)
        sql_called = mock_db_cursor.execute.call_args[0][0]
        assert "LIMIT" not in sql_called
    
    def test_get_for_owner_db_error(self, mock_conn_factory, mock_db_cursor, mock_db_connection):
        """Maneja errores de BD al leer followings."""
        mock_db_cursor.execute.side_effect = Exception("DB error")
        mock_db_connection.cursor.return_value = mock_db_cursor
        
        repo = FollowingsRepoSQL(conn_factory=mock_conn_factory)
        owner = Username(value="owner_user")
        
        with pytest.raises(FollowingsPersistenceError):
            repo.get_for_owner(owner)

