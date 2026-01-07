"""
Tests para JobStoreSQL con conexión y cursor mockeados.
"""
import json
import pytest
from queue import Empty
from unittest.mock import Mock, MagicMock, patch

from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL


class TestJobStoreSQL:
    """Tests para JobStoreSQL con mocks de BD."""
    
    @pytest.fixture(autouse=True)
    def mock_pymysql_connect(self, mock_pymysql_connection):
        """Patch automático de pymysql.connect para todos los tests de esta clase."""
        # Patch pymysql.connect en el módulo donde se usa
        # _new_conn() usa pymysql.connect directamente, así que necesitamos patchear donde se importa
        with patch('scrapinsta.infrastructure.db.job_store_sql.pymysql.connect', return_value=mock_pymysql_connection):
            yield
    
    @pytest.fixture
    def mock_pymysql_connection(self):
        """Mock de conexión pymysql para JobStoreSQL."""
        mock_conn = MagicMock()
        mock_conn._closed = False
        mock_conn.get_autocommit.return_value = False
        mock_conn.ping.return_value = None
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn
    
    @pytest.fixture
    def mock_cursor(self, mock_pymysql_connection):
        """Mock de cursor para JobStoreSQL."""
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchone.return_value = None
        mock_cur.fetchall.return_value = []
        mock_cur.rowcount = 0
        mock_pymysql_connection.cursor.return_value = mock_cur
        return mock_cur
    
    @pytest.fixture
    def job_store(self, mock_pymysql_connection):
        """JobStoreSQL con conexión mockeada."""
        store = JobStoreSQL(
            dsn="mysql://user:pass@localhost:3307/testdb",
            pool_min=1,
            pool_max=2
        )
        store._pool = MagicMock()
        store._pool.get_nowait.side_effect = Empty
        store._pool.put_nowait.side_effect = Exception("Pool full")
        store._pool.qsize.return_value = 0
        return store
    
    def test_create_job(self, job_store, mock_pymysql_connection, mock_cursor):
        """Crear un nuevo job."""
        job_store.create_job(
            job_id="job123",
            kind="analyze",
            priority=1,
            batch_size=10,
            extra={"key": "value"},
            total_items=100,
            client_id="default"
        )
        
        # Verificar que se llamó INSERT con ON DUPLICATE KEY UPDATE
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO jobs" in sql_called
        assert "ON DUPLICATE KEY UPDATE" in sql_called
        
        # Verificar parámetros
        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "job123"
        assert params[1] == "analyze"
        assert params[2] == 1
        assert params[3] == 10
        assert json.loads(params[4]) == {"key": "value"}  # extra_json
        assert params[5] == 100
        assert params[6] == "default"  # client_id
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_create_job_without_extra(self, job_store, mock_pymysql_connection, mock_cursor):
        """Crear job sin extra."""
        job_store.create_job(
            job_id="job456",
            kind="fetch_followings",
            priority=2,
            batch_size=20,
            extra=None,
            total_items=50,
            client_id="default"
        )
        
        params = mock_cursor.execute.call_args[0][1]
        assert params[4] is None  # extra_json
        assert params[6] == "default"  # client_id
    
    def test_mark_job_running(self, job_store, mock_pymysql_connection, mock_cursor):
        """Marcar job como running."""
        job_store.mark_job_running("job123")
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "UPDATE jobs" in sql_called
        assert "status='running'" in sql_called
        assert mock_cursor.execute.call_args[0][1][0] == "job123"
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_mark_job_done(self, job_store, mock_pymysql_connection, mock_cursor):
        """Marcar job como done."""
        job_store.mark_job_done("job123")
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "UPDATE jobs" in sql_called
        assert "status='done'" in sql_called
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_mark_job_error(self, job_store, mock_pymysql_connection, mock_cursor):
        """Marcar job como error."""
        job_store.mark_job_error("job123")
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "UPDATE jobs" in sql_called
        assert "status='error'" in sql_called
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_add_task(self, job_store, mock_pymysql_connection, mock_cursor):
        """Agregar tarea a un job."""
        job_store.add_task(
            job_id="job123",
            task_id="task456",
            correlation_id="corr789",
            account_id="account1",
            username="targetuser",
            payload={"action": "send_message"},
            client_id="default"
        )
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO job_tasks" in sql_called
        assert "ON DUPLICATE KEY UPDATE" in sql_called
        
        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "job123"
        assert params[1] == "task456"
        assert params[2] == "corr789"
        assert params[3] == "account1"
        assert params[4] == "targetuser"  # Normalizado
        assert json.loads(params[5]) == {"action": "send_message"}
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_add_task_normalizes_username(self, job_store, mock_pymysql_connection, mock_cursor):
        """Normaliza username antes de guardar."""
        job_store.add_task(
            job_id="job123",
            task_id="task456",
            correlation_id=None,
            account_id=None,
            username="  TargetUser  ",
            payload=None,
            client_id="default"
        )
        
        params = mock_cursor.execute.call_args[0][1]
        assert params[4] == "targetuser"  # Normalizado a lowercase
        assert params[6] == "default"  # client_id
    
    def test_mark_task_sent(self, job_store, mock_pymysql_connection, mock_cursor):
        """Marcar tarea como sent."""
        job_store.mark_task_sent("job123", "task456")
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "UPDATE job_tasks" in sql_called
        assert "status='sent'" in sql_called
        assert "sent_at=NOW()" in sql_called
        
        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "job123"
        assert params[1] == "task456"
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_mark_task_ok(self, job_store, mock_pymysql_connection, mock_cursor):
        """Marcar tarea como ok."""
        job_store.mark_task_ok("job123", "task456", result={"success": True})
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "UPDATE job_tasks" in sql_called
        assert "status='ok'" in sql_called
        assert "finished_at=NOW()" in sql_called
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_mark_task_error(self, job_store, mock_pymysql_connection, mock_cursor):
        """Marcar tarea como error con mensaje."""
        error_msg = "Error message" * 100  # Mensaje largo
        job_store.mark_task_error("job123", "task456", error_msg)
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "UPDATE job_tasks" in sql_called
        assert "status='error'" in sql_called
        
        # Verificar que el mensaje se recortó a 2000 caracteres
        params = mock_cursor.execute.call_args[0][1]
        assert len(params[0]) <= 2000
        assert params[1] == "job123"
        assert params[2] == "task456"
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_all_tasks_finished_true(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna True si no hay tareas queued o sent."""
        mock_cursor.fetchone.return_value = {"c": 0}
        
        result = job_store.all_tasks_finished("job123")
        
        assert result is True
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "SELECT COUNT(*)" in sql_called
        assert "status IN ('queued','sent')" in sql_called
    
    def test_all_tasks_finished_false(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna False si hay tareas pendientes."""
        mock_cursor.fetchone.return_value = {"c": 5}
        
        result = job_store.all_tasks_finished("job123")
        
        assert result is False
    
    def test_pending_jobs(self, job_store, mock_pymysql_connection, mock_cursor):
        """Obtener lista de jobs pendientes."""
        mock_cursor.fetchall.return_value = [
            {"id": "job1"},
            {"id": "job2"},
            {"id": "job3"},
        ]
        
        result = job_store.pending_jobs()
        
        assert result == ["job1", "job2", "job3"]
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "SELECT id FROM jobs" in sql_called
        assert "status IN ('pending','running')" in sql_called
        assert "ORDER BY created_at ASC" in sql_called
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_pending_jobs_empty(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna lista vacía si no hay jobs pendientes."""
        mock_cursor.fetchall.return_value = []
        
        result = job_store.pending_jobs()
        
        assert result == []
    
    def test_job_summary(self, job_store, mock_pymysql_connection, mock_cursor):
        """Obtener resumen de un job."""
        mock_cursor.fetchone.return_value = {
            "queued": 5,
            "sent": 10,
            "ok": 20,
            "error": 2
        }
        
        result = job_store.job_summary("job123")
        
        assert result == {
            "queued": 5,
            "sent": 10,
            "ok": 20,
            "error": 2
        }
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "SUM(CASE WHEN status='queued'" in sql_called
        assert "SUM(CASE WHEN status='sent'" in sql_called
        assert "SUM(CASE WHEN status='ok'" in sql_called
        assert "SUM(CASE WHEN status='error'" in sql_called
    
    def test_job_summary_empty(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna ceros si no hay tareas."""
        mock_cursor.fetchone.return_value = {}
        
        result = job_store.job_summary("job123")
        
        assert result == {
            "queued": 0,
            "sent": 0,
            "ok": 0,
            "error": 0
        }
    
    def test_lease_tasks(self, job_store, mock_pymysql_connection, mock_cursor):
        """Leasing de tareas (crítico para concurrencia)."""
        # Simular que hay 3 tareas disponibles
        mock_cursor.fetchall.return_value = [
            {
                "job_id": "job1",
                "task_id": "task1",
                "username": "user1",
                "payload_json": '{"action": "send"}'
            },
            {
                "job_id": "job1",
                "task_id": "task2",
                "username": "user2",
                "payload_json": '{"action": "send"}'
            },
            {
                "job_id": "job1",
                "task_id": "task3",
                "username": "user3",
                "payload_json": None
            },
        ]
        
        result = job_store.lease_tasks("account1", limit=5)
        
        assert len(result) == 3
        assert result[0]["job_id"] == "job1"
        assert result[0]["task_id"] == "task1"
        assert result[0]["username"] == "user1"
        assert result[0]["payload"] == {"action": "send"}
        assert result[2]["payload"] is None
        
        assert mock_cursor.execute.call_count >= 3
        assert "START TRANSACTION" in mock_cursor.execute.call_args_list[0][0][0]
        sql_select = mock_cursor.execute.call_args_list[1][0][0]
        assert "FOR UPDATE SKIP LOCKED" in sql_select
        
        sql_update = mock_cursor.execute.call_args_list[2][0][0]
        assert "UPDATE job_tasks" in sql_update
        assert "status = 'sent'" in sql_update
        
        mock_pymysql_connection.commit.assert_called()
    
    def test_lease_tasks_empty(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna lista vacía si no hay tareas disponibles."""
        mock_cursor.fetchall.return_value = []
        
        result = job_store.lease_tasks("account1", limit=5)
        
        assert result == []
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_lease_tasks_rollback_on_error(self, job_store, mock_pymysql_connection, mock_cursor):
        """Hace rollback si hay error durante el leasing."""
        # START TRANSACTION exitoso, luego error en SELECT
        # Necesitamos simular que START TRANSACTION funciona pero SELECT falla
        call_count = [0]
        def mock_execute(*args, **kwargs):
            call_count[0] += 1
            sql = args[0] if args else ""
            if "START TRANSACTION" in sql:
                # START TRANSACTION - OK
                return None
            elif "SELECT" in sql and "job_tasks" in sql:
                # SELECT - Error
                raise Exception("DB error")
            return None
        
        mock_cursor.execute.side_effect = mock_execute
        
        with pytest.raises(Exception, match="DB error"):
            job_store.lease_tasks("account1", limit=5)
        
        mock_pymysql_connection.rollback.assert_called_once()
    
    def test_was_message_sent_true(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna True si el mensaje ya fue enviado."""
        mock_cursor.fetchone.return_value = {"1": 1}  # Existe registro
        
        result = job_store.was_message_sent("client1", "target1")
        
        assert result is True
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "SELECT 1" in sql_called
        assert "FROM messages_sent" in sql_called
        assert "client_username=%s" in sql_called
        assert "dest_username=%s" in sql_called
    
    def test_was_message_sent_false(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna False si el mensaje no fue enviado."""
        mock_cursor.fetchone.return_value = None
        
        result = job_store.was_message_sent("client1", "target1")
        
        assert result is False
    
    def test_was_message_sent_normalizes_usernames(self, job_store, mock_pymysql_connection, mock_cursor):
        """Normaliza usernames antes de buscar."""
        mock_cursor.fetchone.return_value = None
        
        job_store.was_message_sent("  Client1  ", "  Target1  ")
        
        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "client1"  # Normalizado
        assert params[1] == "target1"  # Normalizado
    
    def test_was_message_sent_empty_usernames(self, job_store):
        """Retorna False si algún username está vacío."""
        assert job_store.was_message_sent("", "target1") is False
        assert job_store.was_message_sent("client1", "") is False
        assert job_store.was_message_sent("", "") is False
    
    def test_was_message_sent_any(self, job_store, mock_pymysql_connection, mock_cursor):
        """Verificar si cualquier cliente envió a un destino."""
        mock_cursor.fetchone.return_value = {"1": 1}
        
        result = job_store.was_message_sent_any("target1")
        
        assert result is True
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "FROM messages_sent" in sql_called
        assert "WHERE dest_username=%s" in sql_called
    
    def test_register_message_sent(self, job_store, mock_pymysql_connection, mock_cursor):
        """Registrar envío de mensaje."""
        job_store.get_job_client_id = lambda job_id: "default" if job_id == "job123" else None
        
        job_store.register_message_sent(
            client_username="client1",
            dest_username="target1",
            job_id="job123",
            task_id="task456"
        )
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO messages_sent" in sql_called
        assert "ON DUPLICATE KEY UPDATE" in sql_called
        assert "client_id" in sql_called
        
        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "client1"  # Normalizado
        assert params[1] == "target1"  # Normalizado
        assert params[2] == "job123"
        assert params[3] == "task456"
        assert params[4] == "default"  # client_id
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_cleanup_stale_tasks(self, job_store, mock_pymysql_connection, mock_cursor):
        """Limpiar tareas antiguas en estado queued."""
        # cleanup_stale_tasks ahora procesa por lotes
        cleanup_cursor = Mock()
        cleanup_cursor.__enter__ = Mock(return_value=cleanup_cursor)
        cleanup_cursor.__exit__ = Mock(return_value=False)
        cleanup_cursor.execute = Mock(return_value=None)
        cleanup_cursor.rowcount = 10  # Primera pasada elimina 10, segunda elimina 0 (termina loop)
        mock_pymysql_connection.cursor.return_value = cleanup_cursor
        
        result = job_store.cleanup_stale_tasks(older_than_days=1, batch_size=1000)
        
        assert result == 10
        sql_called = cleanup_cursor.execute.call_args[0][0]
        assert "DELETE FROM job_tasks" in sql_called
        assert "status = 'queued'" in sql_called
        assert "INTERVAL" in sql_called
        assert "LIMIT" in sql_called
        
        params = cleanup_cursor.execute.call_args[0][1]
        assert params[0] == 1  # older_than_days
        assert params[1] == 1000  # batch_size
        
        mock_pymysql_connection.commit.assert_called()
    
    def test_cleanup_finished_tasks(self, job_store, mock_pymysql_connection, mock_cursor):
        """Limpiar tareas finalizadas antiguas."""
        cleanup_cursor = Mock()
        cleanup_cursor.__enter__ = Mock(return_value=cleanup_cursor)
        cleanup_cursor.__exit__ = Mock(return_value=False)
        cleanup_cursor.execute = Mock(return_value=None)
        cleanup_cursor.rowcount = 50  # Primera pasada elimina 50, segunda elimina 0 (termina loop)
        mock_pymysql_connection.cursor.return_value = cleanup_cursor
        
        result = job_store.cleanup_finished_tasks(older_than_days=90, batch_size=1000)
        
        assert result == 50
        sql_called = cleanup_cursor.execute.call_args[0][0]
        assert "DELETE FROM job_tasks" in sql_called
        assert "status IN ('ok','error')" in sql_called
        assert "finished_at" in sql_called
        assert "LIMIT" in sql_called
        
        params = cleanup_cursor.execute.call_args[0][1]
        assert params[0] == 90
        assert params[1] == 1000  # batch_size
        
        mock_pymysql_connection.commit.assert_called()
    
    def test_lease_tasks_sets_leased_at(self, job_store, mock_pymysql_connection, mock_cursor):
        """Verificar que lease_tasks guarda leased_at al leasear."""
        mock_cursor.fetchall.return_value = [
            {
                "job_id": "job1",
                "task_id": "task1",
                "username": "user1",
                "payload_json": '{"action": "send"}'
            },
        ]
        
        job_store.lease_tasks("account1", limit=5, client_id="default")
        
        # Verificar que el UPDATE incluye leased_at
        sql_update = None
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0] if call[0] else ""
            if "UPDATE job_tasks" in sql and "status = 'sent'" in sql:
                sql_update = sql
                break
        
        assert sql_update is not None
        assert "leased_at = NOW()" in sql_update
    
    def test_reclaim_expired_leases(self, job_store, mock_pymysql_connection, mock_cursor):
        """Reencolar tareas con leases expirados."""
        cleanup_cursor = Mock()
        cleanup_cursor.__enter__ = Mock(return_value=cleanup_cursor)
        cleanup_cursor.__exit__ = Mock(return_value=False)
        cleanup_cursor.execute = Mock(return_value=None)
        cleanup_cursor.rowcount = 5
        mock_pymysql_connection.cursor.return_value = cleanup_cursor
        
        result = job_store.reclaim_expired_leases(max_reclaimed=100)
        
        assert result == 5
        sql_called = cleanup_cursor.execute.call_args[0][0]
        assert "UPDATE job_tasks" in sql_called
        assert "status = 'queued'" in sql_called
        assert "leased_at = NULL" in sql_called
        assert "status = 'sent'" in sql_called
        assert "leased_at IS NOT NULL" in sql_called
        assert "DATE_SUB(NOW(), INTERVAL COALESCE(lease_ttl, 300) SECOND)" in sql_called
        
        params = cleanup_cursor.execute.call_args[0][1]
        assert params[0] == 100  # max_reclaimed
        
        mock_pymysql_connection.commit.assert_called_once()
    
    def test_reclaim_expired_leases_empty(self, job_store, mock_pymysql_connection, mock_cursor):
        """Retorna 0 si no hay leases expirados."""
        cleanup_cursor = Mock()
        cleanup_cursor.__enter__ = Mock(return_value=cleanup_cursor)
        cleanup_cursor.__exit__ = Mock(return_value=False)
        cleanup_cursor.execute = Mock(return_value=None)
        cleanup_cursor.rowcount = 0
        mock_pymysql_connection.cursor.return_value = cleanup_cursor
        
        result = job_store.reclaim_expired_leases(max_reclaimed=100)
        
        assert result == 0
    
    def test_mark_task_ok_clears_leased_at(self, job_store, mock_pymysql_connection, mock_cursor):
        """Verificar que mark_task_ok limpia leased_at."""
        job_store.mark_task_ok("job123", "task456", result={"success": True})
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "leased_at=NULL" in sql_called
    
    def test_mark_task_error_clears_leased_at(self, job_store, mock_pymysql_connection, mock_cursor):
        """Verificar que mark_task_error limpia leased_at."""
        job_store.mark_task_error("job123", "task456", "Error message")
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "leased_at=NULL" in sql_called
    
    def test_release_task_clears_leased_at(self, job_store, mock_pymysql_connection, mock_cursor):
        """Verificar que release_task limpia leased_at cuando se libera sin error."""
        job_store.release_task("job123", "task456", error=None)
        
        sql_called = mock_cursor.execute.call_args[0][0]
        assert "status='queued'" in sql_called
        assert "leased_at=NULL" in sql_called

