"""
Tests para ClientRepoSQL con conexión y cursor mockeados.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from passlib.context import CryptContext

from scrapinsta.infrastructure.db.client_repo_sql import ClientRepoSQL

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
def mock_pymysql_connection():
    """Mock de conexión pymysql."""
    mock = MagicMock()
    mock.cursor.return_value.__enter__ = lambda self: self
    mock.cursor.return_value.__exit__ = lambda *args: None
    return mock


@pytest.fixture
def mock_cursor(mock_pymysql_connection):
    """Mock de cursor."""
    mock_cur = MagicMock()
    mock_cur.__enter__ = lambda self: self
    mock_cur.__exit__ = lambda *args: None
    mock_pymysql_connection.cursor.return_value = mock_cur
    return mock_cur


@pytest.fixture
def client_repo(mock_pymysql_connection):
    """ClientRepoSQL con conexión mockeada."""
    repo = ClientRepoSQL(dsn="mysql://user:pass@localhost:3307/testdb")
    original_connect = repo._connect
    repo._connect = lambda: mock_pymysql_connection
    return repo


class TestClientRepoSQL:
    """Tests para ClientRepoSQL con mocks de BD."""
    
    def test_get_by_id_exists(self, client_repo, mock_cursor):
        """Obtener cliente por ID existente."""
        mock_cursor.fetchone.return_value = {
            "id": "client1",
            "name": "Test Client",
            "email": "test@example.com",
            "api_key_hash": "hash123",
            "status": "active",
            "created_at": None,
            "updated_at": None,
            "metadata": None
        }
        
        result = client_repo.get_by_id("client1")
        
        assert result is not None
        assert result["id"] == "client1"
        assert result["name"] == "Test Client"
        assert result["status"] == "active"
        mock_cursor.execute.assert_called_once()
    
    def test_get_by_id_not_exists(self, client_repo, mock_cursor):
        """Obtener cliente por ID que no existe."""
        mock_cursor.fetchone.return_value = None
        
        result = client_repo.get_by_id("nonexistent")
        
        assert result is None
    
    def test_get_by_id_deleted(self, client_repo, mock_cursor):
        """No retorna clientes eliminados."""
        mock_cursor.fetchone.return_value = None
        
        result = client_repo.get_by_id("deleted_client")
        
        assert result is None
    
    def test_get_by_api_key_valid(self, client_repo, mock_cursor):
        """Obtener cliente por API key válida."""
        api_key = "testkey123"
        hashed = "$2b$12$testhash1234567890123456789012345678901234567890123456789012"
        
        mock_cursor.fetchall.return_value = [
            {
                "id": "client1",
                "name": "Test Client",
                "email": "test@example.com",
                "api_key_hash": hashed,
                "status": "active"
            }
        ]
        
        with patch("scrapinsta.infrastructure.db.client_repo_sql.pwd_context.verify") as mock_verify:
            mock_verify.return_value = True
            result = client_repo.get_by_api_key(api_key)
        
        assert result is not None
        assert result["id"] == "client1"
        mock_verify.assert_called_once_with(api_key, hashed)
    
    def test_get_by_api_key_invalid(self, client_repo, mock_cursor):
        """Obtener cliente con API key inválida."""
        hashed = "$2b$12$testhash1234567890123456789012345678901234567890123456789012"
        mock_cursor.fetchall.return_value = [
            {
                "id": "client1",
                "api_key_hash": hashed,
                "status": "active"
            }
        ]
        
        with patch("scrapinsta.infrastructure.db.client_repo_sql.pwd_context.verify") as mock_verify:
            mock_verify.return_value = False
            result = client_repo.get_by_api_key("wrong-key")
        
        assert result is None
        mock_verify.assert_called_once_with("wrong-key", hashed)
    
    def test_get_by_api_key_no_active_clients(self, client_repo, mock_cursor):
        """No retorna clientes inactivos."""
        mock_cursor.fetchall.return_value = []
        
        result = client_repo.get_by_api_key("any-key")
        
        assert result is None
    
    def test_create_client(self, client_repo, mock_cursor, mock_pymysql_connection):
        """Crear nuevo cliente."""
        hashed = "$2b$12$testhash1234567890123456789012345678901234567890123456789012"
        
        client_repo.create(
            client_id="new_client",
            name="New Client",
            email="new@example.com",
            api_key_hash=hashed,
            metadata={"key": "value"}
        )
        
        mock_cursor.execute.assert_called_once()
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_update_status(self, client_repo, mock_cursor, mock_pymysql_connection):
        """Actualizar estado de cliente."""
        client_repo.update_status("client1", "suspended")
        
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE clients" in sql
        assert "status" in sql
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_get_limits_exists(self, client_repo, mock_cursor):
        """Obtener límites de cliente existente."""
        mock_cursor.fetchone.return_value = {
            "client_id": "client1",
            "requests_per_minute": 100,
            "requests_per_hour": 5000,
            "requests_per_day": 50000,
            "messages_per_day": 1000
        }
        
        result = client_repo.get_limits("client1")
        
        assert result is not None
        assert result["requests_per_minute"] == 100
        assert result["messages_per_day"] == 1000
    
    def test_get_limits_not_exists(self, client_repo, mock_cursor):
        """Obtener límites de cliente que no tiene límites."""
        mock_cursor.fetchone.return_value = None
        
        result = client_repo.get_limits("client1")
        
        assert result is None
    
    def test_update_limits(self, client_repo, mock_cursor, mock_pymysql_connection):
        """Actualizar límites de cliente."""
        client_repo.update_limits("client1", {
            "requests_per_minute": 200,
            "requests_per_hour": 10000,
            "requests_per_day": 100000,
            "messages_per_day": 2000
        })
        
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO client_limits" in sql
        assert "ON DUPLICATE KEY UPDATE" in sql
        mock_pymysql_connection.commit.assert_called_once()

