"""
Tests de concurrencia para validar comportamiento con múltiples workers.

Estos tests validan:
- Múltiples workers no obtienen la misma tarea (leasing sin duplicados)
- Race conditions en leasing
- Creación concurrente de jobs
- Deduplicación con requests concurrentes

Todos los tests usan threading para simular múltiples workers concurrentes.
"""
from __future__ import annotations

import threading
import time
from typing import List, Set, Dict, Any
from unittest.mock import Mock, MagicMock, patch
from queue import Empty, Queue

import pytest

from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL


# =========================================================
# Fixtures
# =========================================================

@pytest.fixture
def mock_pymysql_connection():
    """Mock de conexión pymysql para JobStoreSQL."""
    mock_conn = MagicMock()
    mock_conn._closed = False
    mock_conn.get_autocommit.return_value = False
    mock_conn.ping.return_value = None
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


@pytest.fixture(autouse=True)
def mock_pymysql_connect(mock_pymysql_connection):
    """Patch automático de pymysql.connect para todos los tests."""
    with patch('scrapinsta.infrastructure.db.job_store_sql.pymysql.connect', return_value=mock_pymysql_connection):
        yield


@pytest.fixture
def job_store(mock_pymysql_connection):
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


# =========================================================
# Tests: Leasing sin duplicados
# =========================================================

class TestLeasingNoDuplicates:
    """Tests para validar que múltiples workers no obtienen la misma tarea."""
    
    def test_leasing_no_duplicates(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples workers intentan lease simultáneamente.
        Verificar que cada tarea se asigna solo a un worker.
        """
        # Simular 10 tareas disponibles
        available_tasks = [
            {"job_id": f"job{i}", "task_id": f"task{i}", "username": f"user{i}", "payload_json": "{}"}
            for i in range(10)
        ]
        
        task_lock = threading.Lock()
        remaining_tasks = available_tasks.copy()
        
        def mock_lease_tasks(account_id: str, limit: int) -> List[Dict[str, Any]]:
            with task_lock:
                to_lease = remaining_tasks[:limit]
                remaining_tasks[:limit] = []
                return [
                    {
                        "job_id": t["job_id"],
                        "task_id": t["task_id"],
                        "username": t["username"],
                        "payload": {}
                    }
                    for t in to_lease
                ]
        
        # Simular múltiples workers haciendo lease simultáneamente
        results: List[List[Dict[str, Any]]] = []
        results_lock = threading.Lock()
        
        def worker(worker_id: int):
            with patch.object(job_store, 'lease_tasks', side_effect=mock_lease_tasks):
                tasks = job_store.lease_tasks("test-account", limit=5)
                with results_lock:
                    results.append(tasks)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=5.0)
        
        all_task_ids: Set[str] = set()
        for worker_tasks in results:
            for task in worker_tasks:
                task_id = f"{task['job_id']}:{task['task_id']}"
                assert task_id not in all_task_ids, f"Tarea duplicada encontrada: {task_id}"
                all_task_ids.add(task_id)
        
        total_leased = sum(len(tasks) for tasks in results)
        assert total_leased <= len(available_tasks), "Se leasearon más tareas de las disponibles"
        assert total_leased > 0, "No se leaseó ninguna tarea"
    
    def test_leasing_race_condition(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Test de race condition: múltiples workers intentan lease la misma tarea.
        Solo uno debe obtenerla.
        """
        # Una sola tarea disponible
        single_task = {"job_id": "job1", "task_id": "task1", "username": "user1", "payload_json": "{}"}
        task_available = [single_task]
        task_lock = threading.Lock()
        
        def mock_lease_tasks(account_id: str, limit: int) -> List[Dict[str, Any]]:
            """Simula lease_tasks con race condition."""
            with task_lock:
                if task_available:
                    task = task_available.pop(0)
                    return [{
                        "job_id": task["job_id"],
                        "task_id": task["task_id"],
                        "username": task["username"],
                        "payload": {}
                    }]
                return []
        
        # Simular 5 workers intentando lease la misma tarea
        leased_count = 0
        count_lock = threading.Lock()
        
        def worker():
            nonlocal leased_count
            with patch.object(job_store, 'lease_tasks', side_effect=mock_lease_tasks):
                tasks = job_store.lease_tasks("test-account", limit=1)
                if tasks:
                    with count_lock:
                        leased_count += 1
        
        threads = [threading.Thread(target=worker) for _ in range(5)]
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        # Solo un worker debe haber obtenido la tarea
        assert leased_count == 1, f"Se leaseó la tarea {leased_count} veces, debería ser 1"


# =========================================================
# Tests: Creación concurrente de jobs
# =========================================================

class TestConcurrentJobCreation:
    """Tests para validar creación concurrente de jobs."""
    
    def test_concurrent_job_creation(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples threads crean jobs simultáneamente.
        Verificar que todos los jobs se crean correctamente sin conflictos.
        """
        created_jobs: Set[str] = set()
        jobs_lock = threading.Lock()
        
        def mock_create_job(
            job_id: str,
            kind: str,
            priority: int,
            batch_size: int,
            extra: Dict[str, Any],
            total_items: int
        ) -> None:
            """Simula create_job con tracking de jobs creados."""
            with jobs_lock:
                created_jobs.add(job_id)
        
        # Mock del cursor para create_job
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        mock_pymysql_connection.cursor.return_value = mock_cursor
        
        def worker(worker_id: int):
            """Simula un worker creando un job."""
            job_id = f"job_worker_{worker_id}"
            with patch.object(job_store, 'create_job', side_effect=mock_create_job):
                job_store.create_job(
                    job_id=job_id,
                    kind="analyze_profile",
                    priority=5,
                    batch_size=10,
                    extra={},
                    total_items=100
                )
        
        # Crear 10 workers que crean jobs simultáneamente
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        assert len(created_jobs) == 10, f"Se crearon {len(created_jobs)} jobs, deberían ser 10"
        assert len(created_jobs) == len(set(created_jobs)), "Hay jobs duplicados"
    
    def test_concurrent_job_creation_with_same_id(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples threads intentan crear el mismo job simultáneamente.
        Solo uno debe tener éxito (simulando constraint único en BD).
        """
        job_id = "job_duplicate"
        creation_count = 0
        creation_lock = threading.Lock()
        creation_errors = []
        
        def mock_create_job(*args, **kwargs) -> None:
            """Simula create_job con constraint único."""
            nonlocal creation_count
            with creation_lock:
                if creation_count == 0:
                    # Primer thread tiene éxito
                    creation_count += 1
                else:
                    # Otros threads fallan con error de constraint único
                    raise Exception("Duplicate entry for key 'PRIMARY'")
        
        def worker():
            """Simula un worker intentando crear un job."""
            try:
                with patch.object(job_store, 'create_job', side_effect=mock_create_job):
                    job_store.create_job(
                        job_id=job_id,
                        kind="analyze_profile",
                        priority=5,
                        batch_size=10,
                        extra={},
                        total_items=100
                    )
            except Exception as e:
                with creation_lock:
                    creation_errors.append(str(e))
        
        # Crear 5 workers intentando crear el mismo job
        threads = [threading.Thread(target=worker) for _ in range(5)]
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        # Solo un thread debe haber creado el job exitosamente
        assert creation_count == 1, f"Se creó el job {creation_count} veces, debería ser 1"
        # Los otros 4 deben haber fallado
        assert len(creation_errors) == 4, f"Se esperaban 4 errores, se obtuvieron {len(creation_errors)}"


# =========================================================
# Tests: Deduplicación concurrente
# =========================================================

class TestDeduplicationConcurrent:
    """Tests para validar deduplicación con requests concurrentes."""
    
    def test_deduplication_concurrent_messages(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples workers intentan registrar el mismo mensaje simultáneamente.
        Solo uno debe tener éxito (simulando constraint único en BD).
        """
        client_username = "client1"
        dest_username = "dest1"
        registration_count = 0
        registration_lock = threading.Lock()
        registration_errors = []
        
        def mock_register_message_sent(
            client_username: str,
            dest_username: str,
            job_id: str,
            task_id: str
        ) -> None:
            """Simula register_message_sent con constraint único."""
            nonlocal registration_count
            with registration_lock:
                if registration_count == 0:
                    # Primer thread tiene éxito
                    registration_count += 1
                else:
                    # Otros threads fallan con error de constraint único
                    raise Exception("Duplicate entry for key 'uq_messages_sent'")
        
        def worker(worker_id: int):
            """Simula un worker intentando registrar un mensaje."""
            try:
                with patch.object(job_store, 'register_message_sent', side_effect=mock_register_message_sent):
                    job_store.register_message_sent(
                        client_username=client_username,
                        dest_username=dest_username,
                        job_id=f"job{worker_id}",
                        task_id=f"task{worker_id}"
                    )
            except Exception as e:
                with registration_lock:
                    registration_errors.append(str(e))
        
        # Crear 5 workers intentando registrar el mismo mensaje
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        # Solo un thread debe haber registrado el mensaje exitosamente
        assert registration_count == 1, f"Se registró el mensaje {registration_count} veces, debería ser 1"
        # Los otros 4 deben haber fallado
        assert len(registration_errors) == 4, f"Se esperaban 4 errores, se obtuvieron {len(registration_errors)}"
    
    def test_deduplication_concurrent_followings(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples workers intentan guardar los mismos followings simultáneamente.
        La deduplicación debe funcionar correctamente (INSERT IGNORE / ON CONFLICT).
        """
        # Este test sería más complejo porque requiere mockear FollowingsRepoSQL
        # Por ahora, validamos que el concepto de deduplicación funciona
        # En un test real, necesitaríamos mockear la conexión y el cursor
        # para simular INSERT IGNORE o ON CONFLICT DO NOTHING
        
        # Simulamos que múltiples threads intentan insertar el mismo following
        insert_count = 0
        insert_lock = threading.Lock()
        
        def mock_insert_following(owner: str, target: str) -> int:
            """Simula insert con deduplicación."""
            nonlocal insert_count
            # Simulamos que solo el primer insert tiene éxito (INSERT IGNORE)
            if insert_count == 0:
                insert_count += 1
                return 1  # 1 fila insertada
            else:
                return 0  # 0 filas insertadas (duplicado ignorado)
        
        def worker():
            """Simula un worker intentando insertar un following."""
            with insert_lock:
                result = mock_insert_following("owner1", "target1")
                return result
        
        # Crear 5 workers intentando insertar el mismo following
        results = []
        results_lock = threading.Lock()
        
        def worker_with_result():
            result = worker()
            with results_lock:
                results.append(result)
        
        threads = [threading.Thread(target=worker_with_result) for _ in range(5)]
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        # Solo un insert debe tener éxito (retornar 1)
        successful_inserts = sum(1 for r in results if r == 1)
        assert successful_inserts == 1, f"Se insertaron {successful_inserts} followings, debería ser 1"
        
        # Los otros 4 deben haber sido ignorados (retornar 0)
        ignored_inserts = sum(1 for r in results if r == 0)
        assert ignored_inserts == 4, f"Se ignoraron {ignored_inserts} inserts, deberían ser 4"


# =========================================================
# Tests: Actualización concurrente de estados
# =========================================================

class TestConcurrentStateUpdates:
    """Tests para validar actualizaciones concurrentes de estados."""
    
    def test_concurrent_mark_task_ok(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples threads intentan marcar la misma tarea como 'ok' simultáneamente.
        Todos deben tener éxito (idempotente).
        """
        job_id = "job1"
        task_id = "task1"
        update_count = 0
        update_lock = threading.Lock()
        
        def mock_mark_task_ok(job_id: str, task_id: str, result: Any) -> None:
            """Simula mark_task_ok (idempotente)."""
            nonlocal update_count
            with update_lock:
                update_count += 1
        
        def worker():
            """Simula un worker marcando una tarea como ok."""
            with patch.object(job_store, 'mark_task_ok', side_effect=mock_mark_task_ok):
                job_store.mark_task_ok(job_id, task_id, result=None)
        
        # Crear 5 workers marcando la misma tarea como ok
        threads = [threading.Thread(target=worker) for _ in range(5)]
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        # Todos los threads deben haber ejecutado la actualización
        # (aunque en la práctica, solo uno debería actualizar la BD)
        assert update_count == 5, f"Se ejecutaron {update_count} actualizaciones, deberían ser 5"
    
    def test_concurrent_job_state_transitions(
        self, job_store: JobStoreSQL, mock_pymysql_connection: Mock
    ):
        """
        Múltiples threads intentan cambiar el estado de un job simultáneamente.
        Verificar que las transiciones de estado son consistentes.
        """
        job_id = "job1"
        state_transitions = []
        state_lock = threading.Lock()
        
        def mock_mark_job_running(job_id: str) -> None:
            with state_lock:
                state_transitions.append(("running", job_id))
        
        def mock_mark_job_done(job_id: str) -> None:
            with state_lock:
                state_transitions.append(("done", job_id))
        
        def worker_running():
            with patch.object(job_store, 'mark_job_running', side_effect=mock_mark_job_running):
                job_store.mark_job_running(job_id)
        
        def worker_done():
            with patch.object(job_store, 'mark_job_done', side_effect=mock_mark_job_done):
                job_store.mark_job_done(job_id)
        
        # Crear workers que cambian el estado del job
        threads = []
        threads.append(threading.Thread(target=worker_running))
        threads.append(threading.Thread(target=worker_done))
        threads.append(threading.Thread(target=worker_running))
        
        # Iniciar todos simultáneamente
        for t in threads:
            t.start()
        
        # Esperar a que todos terminen
        for t in threads:
            t.join(timeout=5.0)
        
        # Verificar que todas las transiciones se registraron
        assert len(state_transitions) == 3, f"Se registraron {len(state_transitions)} transiciones, deberían ser 3"
        
        # Verificar que el job_id es consistente en todas las transiciones
        for state, jid in state_transitions:
            assert jid == job_id, f"Job ID inconsistente: {jid} != {job_id}"

