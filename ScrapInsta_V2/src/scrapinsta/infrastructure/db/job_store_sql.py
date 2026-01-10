from __future__ import annotations
import json
import time
from typing import Any, Dict, List, Optional
import threading
from queue import Queue, Empty
import os

import pymysql  # pip install PyMySQL

from scrapinsta.domain.ports.job_store import JobStorePort
from scrapinsta.crosscutting.metrics import (
    db_queries_total,
    db_query_duration_seconds,
    db_connections_active,
)


def _json(obj: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serializa dicts a JSON compacto; None permanece como None."""
    if obj is None:
        return None
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _norm(username: Optional[str]) -> Optional[str]:
    """Normaliza usernames: trim + lower; si queda vacío, devolvemos None."""
    if username is None:
        return None
    v = str(username).strip().lower()
    return v or None


class JobStoreSQL(JobStorePort):
    def __init__(self, dsn: str, *, pool_min: int = 2, pool_max: int = 8) -> None:
        """
        Conexión a MySQL simple con un pool liviano propio.
        dsn: mysql://user:pass@host:port/db?charset=utf8mb4
        pool_min/pool_max: cantidad mínima/máxima de conexiones en el pool.
        """
        self._dsn = dsn
        self._pool_min = int(pool_min)
        self._pool_max = int(pool_max)
        self._pool: Queue[pymysql.connections.Connection] = Queue(maxsize=self._pool_max)
        self._pool_lock = threading.Lock()

    # -----------------------
    # Conn helper
    # -----------------------
    def _connect(self):
        """Obtiene una conexión del pool o crea una nueva si hace falta."""
        # Parse DSN simple: mysql://user:pass@host:port/db?charset=utf8mb4
        assert self._dsn.startswith("mysql://")
        tail = self._dsn[len("mysql://") :]
        cred, rest = tail.split("@", 1)
        user, pwd = cred.split(":", 1)
        hostport, dbq = rest.split("/", 1)
        if ":" in hostport:
            host, port = hostport.split(":")
        else:
            host, port = hostport, "3307"
        if "?" in dbq:
            db, _q = dbq.split("?", 1)
        else:
            db = dbq
        def _new_conn() -> pymysql.connections.Connection:
            ssl_params = None
            try:
                ca = os.getenv("MYSQL_SSL_CA")
                cert = os.getenv("MYSQL_SSL_CERT")
                key = os.getenv("MYSQL_SSL_KEY")
                if ca:
                    ssl_params = {"ca": ca}
                    if cert and key:
                        ssl_params.update({"cert": cert, "key": key})
            except Exception:
                ssl_params = None
            return pymysql.connect(
                host=host,
                port=int(port),
                user=user,
                password=pwd,
                database=db,
                charset="utf8mb4",
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
                ssl=ssl_params,
            )

        # Reusar una conexión del pool si hay
        try:
            con = self._pool.get_nowait()
            try:
                con.ping(reconnect=True)
                db_connections_active.set(self._pool.qsize() + 1)
                return con
            except Exception:
                try:
                    con.close()
                except Exception:
                    pass
        except Empty:
            pass

        # Rellenar hasta el mínimo si aún falta
        with self._pool_lock:
            while self._pool.qsize() < self._pool_min:
                try:
                    self._pool.put_nowait(_new_conn())
                except Exception:
                    break

        # Devolver una conexión nueva
        con = _new_conn()
        db_connections_active.set(self._pool.qsize() + 1)
        return con

    def _return(self, con: pymysql.connections.Connection) -> None:
        """Devuelve la conexión al pool (o la cierra si no se puede reutilizar)."""
        try:
            if con and not con._closed and not con.get_autocommit():
                con.ping(reconnect=True)
            try:
                self._pool.put_nowait(con)
                db_connections_active.set(self._pool.qsize())
            except Exception:
                con.close()
                db_connections_active.set(self._pool.qsize())
        except Exception:
            try:
                con.close()
            except Exception:
                pass
            db_connections_active.set(self._pool.qsize())

    def _execute_query(self, cur, sql: str, params: tuple, operation: str, table: str) -> None:
        """Wrapper para ejecutar queries con métricas."""
        start = time.time()
        try:
            cur.execute(sql, params)
            db_queries_total.labels(operation=operation, table=table).inc()
        finally:
            duration = time.time() - start
            db_query_duration_seconds.labels(operation=operation, table=table).observe(duration)

    # -----------------------
    # Jobs
    # -----------------------
    def create_job(
        self,
        job_id: str,
        kind: str,
        priority: int,
        batch_size: int,
        extra: Optional[Dict[str, Any]],
        total_items: int,
        client_id: str,
    ) -> None:
        """
        Crea un nuevo job.
        
        IMPORTANTE: client_id es REQUERIDO y debe ser explícito.
        No se permite usar 'default' a menos que sea explícitamente pasado.
        """
        if not client_id or not client_id.strip():
            raise ValueError("client_id es requerido y no puede estar vacío")
        sql = """
            INSERT INTO jobs (id, kind, priority, batch_size, extra_json, total_items, status, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
            ON DUPLICATE KEY UPDATE
              kind=VALUES(kind), priority=VALUES(priority), batch_size=VALUES(batch_size),
              extra_json=VALUES(extra_json), total_items=VALUES(total_items), updated_at=CURRENT_TIMESTAMP
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id, kind, priority, batch_size, _json(extra), total_items, client_id), "insert", "jobs")
            con.commit()
        finally:
            self._return(con)

    def mark_job_running(self, job_id: str) -> None:
        """Pone un Job en estado 'running'."""
        sql = "UPDATE jobs SET status='running' WHERE id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "update", "jobs")
            con.commit()
        finally:
            self._return(con)

    def mark_job_done(self, job_id: str) -> None:
        """Marca un Job como 'done'."""
        sql = "UPDATE jobs SET status='done' WHERE id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "update", "jobs")
            con.commit()
        finally:
            self._return(con)

    def mark_job_error(self, job_id: str) -> None:
        """Marca un Job como 'error'."""
        sql = "UPDATE jobs SET status='error' WHERE id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "update", "jobs")
            con.commit()
        finally:
            self._return(con)

    # -----------------------
    # Tasks
    # -----------------------
    def add_task(
        self,
        job_id: str,
        task_id: str,
        correlation_id: Optional[str],
        account_id: Optional[str],
        username: Optional[str],
        payload: Optional[Dict[str, Any]],
        client_id: str,
    ) -> None:
        """
        Agrega una tarea a un job.
        
        IMPORTANTE: client_id es REQUERIDO y debe ser explícito.
        No se permite usar 'default' a menos que sea explícitamente pasado.
        """
        if not client_id or not client_id.strip():
            raise ValueError("client_id es requerido y no puede estar vacío")
        
        sql = """
            INSERT INTO job_tasks (job_id, task_id, correlation_id, account_id, username, payload_json, status, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'queued', %s)
            ON DUPLICATE KEY UPDATE
              correlation_id=VALUES(correlation_id),
              account_id=VALUES(account_id),
              username=VALUES(username),
              payload_json=VALUES(payload_json),
              updated_at=CURRENT_TIMESTAMP
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id, task_id, correlation_id, account_id, _norm(username), _json(payload), client_id), "insert", "job_tasks")
            con.commit()
        finally:
            self._return(con)

    def mark_task_sent(self, job_id: str, task_id: str) -> None:
        """Marca task como 'sent' y setea sent_at."""
        sql = "UPDATE job_tasks SET status='sent', sent_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id, task_id), "update", "job_tasks")
            con.commit()
        finally:
            self._return(con)

    def mark_task_ok(self, job_id: str, task_id: str, result: Optional[Dict[str, Any]]) -> None:
        """Marca task como 'ok' y cierra timestamps."""
        sql = "UPDATE job_tasks SET status='ok', finished_at=NOW(), leased_at=NULL, updated_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id, task_id), "update", "job_tasks")
            con.commit()
        finally:
            self._return(con)

    def mark_task_error(self, job_id: str, task_id: str, error: str) -> None:
        """Marca task como 'error' con mensaje (recortado a 2000 chars)."""
        sql = "UPDATE job_tasks SET status='error', error_msg=%s, finished_at=NOW(), leased_at=NULL, updated_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (error[:2000], job_id, task_id), "update", "job_tasks")
            con.commit()
        finally:
            self._return(con)

    def all_tasks_finished(self, job_id: str) -> bool:
        """True si no quedan tasks 'queued' o 'sent' para ese job."""
        sql = "SELECT COUNT(*) AS c FROM job_tasks WHERE job_id=%s AND status IN ('queued','sent')"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "select", "job_tasks")
                row = cur.fetchone()
                return (row or {}).get("c", 0) == 0
        finally:
            self._return(con)

    def get_job_client_id(self, job_id: str) -> Optional[str]:
        """Obtiene el client_id de un job."""
        sql = "SELECT client_id FROM jobs WHERE id = %s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "select", "jobs")
                row = cur.fetchone()
                if row:
                    return row.get("client_id")
                return None
        finally:
            self._return(con)

    # -----------------------
    # Recuperación
    # -----------------------
    def pending_jobs(self) -> List[str]:
        """Lista de job_ids con estado 'pending' o 'running' (ordenados por creación)."""
        sql = "SELECT id FROM jobs WHERE status IN ('pending','running') ORDER BY created_at ASC"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (), "select", "jobs")
                rows = cur.fetchall()
                
                # --- CORRECCIÓN ---
                # Debemos cerrar la transacción (iniciada por el SELECT 
                # porque autocommit=False) antes de devolver la conexión al pool.
                con.commit() 
                # ------------------
                
                return [r["id"] for r in rows]
        except Exception:
            # Si hay un error, también debemos limpiar
            try:
                con.rollback()
            except Exception:
                pass
            raise # Relanza la excepción original
        finally:
            self._return(con)

    def job_summary(self, job_id: str, client_id: Optional[str] = None) -> Dict[str, Any]:
        """Resumen de cantidades por estado para un job dado."""
        if client_id:
            sql = """
              SELECT
                SUM(CASE WHEN jt.status='queued' THEN 1 ELSE 0 END) AS queued,
                SUM(CASE WHEN jt.status='sent'   THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN jt.status='ok'     THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN jt.status='error'  THEN 1 ELSE 0 END) AS error
              FROM job_tasks jt
              INNER JOIN jobs j ON jt.job_id = j.id
              WHERE jt.job_id=%s AND j.client_id=%s
            """
            params = (job_id, client_id)
        else:
            sql = """
              SELECT
                SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
                SUM(CASE WHEN status='sent'   THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN status='ok'     THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN status='error'  THEN 1 ELSE 0 END) AS error
              FROM job_tasks
              WHERE job_id=%s
            """
            params = (job_id,)
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, params, "select", "job_tasks")
                row = cur.fetchone() or {}
                return {
                    "queued": int(row.get("queued", 0)),
                    "sent": int(row.get("sent", 0)),
                    "ok": int(row.get("ok", 0)),
                    "error": int(row.get("error", 0)),
                }
        finally:
            self._return(con)

    # -----------------------
    # Mantenimiento
    # -----------------------
    def cleanup_stale_tasks(self, older_than_days: int = 1, batch_size: int = 1000) -> int:
        """
        Elimina tasks 'queued' antiguas para mantener limpia la tabla.
        Procesa por lotes para evitar locks largos.
        
        Args:
            older_than_days: Días de antigüedad para considerar una tarea como "stale"
            batch_size: Número máximo de filas a eliminar por lote
            
        Returns:
            Total de tareas eliminadas
        """
        total_affected = 0
        con = self._connect()
        try:
            while True:
                sql = """
                    DELETE FROM job_tasks
                    WHERE status = 'queued'
                      AND created_at < (NOW() - INTERVAL %s DAY)
                    LIMIT %s
                """
                with con.cursor() as cur:
                    self._execute_query(cur, sql, (int(older_than_days), batch_size), "delete", "job_tasks")
                    affected = cur.rowcount or 0
                    total_affected += affected
                con.commit()
                
                if affected < batch_size:
                    break
        finally:
            self._return(con)
        return int(total_affected)

    def cleanup_finished_tasks(self, older_than_days: int = 90, batch_size: int = 1000) -> int:
        """
        Elimina tasks 'ok'/'error' muy viejas para limitar el tamaño de la tabla.
        Procesa por lotes para evitar locks largos.
        
        Args:
            older_than_days: Días de antigüedad para considerar una tarea como antigua
            batch_size: Número máximo de filas a eliminar por lote
            
        Returns:
            Total de tareas eliminadas
        """
        total_affected = 0
        con = self._connect()
        try:
            while True:
                sql = """
                    DELETE FROM job_tasks
                    WHERE status IN ('ok','error')
                      AND finished_at IS NOT NULL
                      AND finished_at < (NOW() - INTERVAL %s DAY)
                    LIMIT %s
                """
                with con.cursor() as cur:
                    self._execute_query(cur, sql, (int(older_than_days), batch_size), "delete", "job_tasks")
                    affected = cur.rowcount or 0
                    total_affected += affected
                con.commit()
                
                if affected < batch_size:
                    break
        finally:
            self._return(con)
        return int(total_affected)
    
    def cleanup_orphaned_jobs(self, older_than_days: int = 7) -> int:
        """
        Elimina jobs que no tienen tareas asociadas (huérfanos).
        
        Args:
            older_than_days: Días de antigüedad mínima para considerar un job como huérfano
            
        Returns:
            Número de jobs eliminados
        """
        sql = """
            DELETE j FROM jobs j
            LEFT JOIN job_tasks jt ON j.id = jt.job_id
            WHERE jt.job_id IS NULL
              AND j.created_at < (NOW() - INTERVAL %s DAY)
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (int(older_than_days),), "delete", "jobs")
                affected = cur.rowcount or 0
            con.commit()
        finally:
            self._return(con)
        return int(affected)

    # -----------------------
    # Ledger de deduplicación por cuenta cliente
    # -----------------------
    def was_message_sent(self, client_username: str, dest_username: str) -> bool:
        """True si esta cuenta cliente ya le envió a este destino."""
        sql = """
            SELECT 1
            FROM messages_sent
            WHERE client_username=%s AND dest_username=%s
            LIMIT 1
        """
        cu = _norm(client_username)
        du = _norm(dest_username)
        if not cu or not du:
            return False
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (cu, du), "select", "messages_sent")
                row = cur.fetchone()
                return bool(row)
        finally:
            self._return(con)

    def was_message_sent_any(self, dest_username: str) -> bool:
        """True si cualquier cuenta cliente ya le envió a este destino."""
        sql = """
            SELECT 1
            FROM messages_sent
            WHERE dest_username=%s
            LIMIT 1
        """
        du = _norm(dest_username)
        if not du:
            return False
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (du,), "select", "messages_sent")
                row = cur.fetchone()
                return bool(row)
        finally:
            self._return(con)

    def register_message_sent(
        self,
        client_username: str,
        dest_username: str,
        job_id: Optional[str] = None,
        task_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> None:
        """
        Registra envío; idempotente gracias al UNIQUE(client_username, dest_username).
        Si client_id no se provee, se obtiene del job_id.
        """
        cu = _norm(client_username)
        du = _norm(dest_username)
        if not cu or not du:
            return
        
        if not client_id and job_id:
            client_id = self.get_job_client_id(job_id)
        
        if not client_id:
            raise ValueError(
                f"client_id es requerido para register_message_sent. "
                f"Provea client_id o un job_id válido."
            )
        
        sql = """
            INSERT INTO messages_sent (client_username, dest_username, job_id, task_id, client_id)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              job_id = VALUES(job_id),
              task_id = VALUES(task_id),
              client_id = VALUES(client_id),
              last_sent_at = CURRENT_TIMESTAMP
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (cu, du, job_id, task_id, client_id), "insert", "messages_sent")
            con.commit()
        finally:
            self._return(con)


    # -----------------------
    # Leasing de tareas (extensiones o workers externos)
    # -----------------------
    def lease_tasks(self, account_id: str, limit: int, client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtiene hasta `limit` tareas 'queued' para esta cuenta, las marca 'sent'
        y devuelve los datos mínimos para procesarlas. Usa SKIP LOCKED (MySQL 8+).
        """
        if client_id:
            sql_select = """
                SELECT jt.job_id, jt.task_id, jt.username, jt.payload_json
                FROM job_tasks jt
                INNER JOIN jobs j ON jt.job_id = j.id
                WHERE jt.account_id = %s AND jt.status = 'queued' AND j.client_id = %s
                ORDER BY jt.created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            """
            select_params = (account_id, client_id, limit)
        else:
            sql_select = """
                SELECT job_id, task_id, username, payload_json
                FROM job_tasks
                WHERE account_id = %s AND status = 'queued'
                ORDER BY created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            """
            select_params = (account_id, limit)
        sql_update = """
            UPDATE job_tasks
            SET status = 'sent', sent_at = NOW(), leased_at = NOW(), updated_at = NOW()
            WHERE (job_id, task_id) IN (%s)
        """
        leased: List[Dict[str, Any]] = []

        con = self._connect()
        try:
            try:
                with con.cursor() as cur:
                    cur.execute("START TRANSACTION;")
                    self._execute_query(cur, sql_select, select_params, "select", "job_tasks")
                    rows = cur.fetchall() or []
                    if not rows:
                        con.commit()
                        return []

                    keys = ", ".join(["(%s, %s)"] * len(rows))
                    args: list[str] = []
                    for r in rows:
                        args += [r["job_id"], r["task_id"]]
                    self._execute_query(cur, sql_update % keys, args, "update", "job_tasks")
                    con.commit()
                    leased = [
                        {
                            "job_id": r["job_id"],
                            "task_id": r["task_id"],
                            "username": r["username"],
                            "payload": json.loads(r["payload_json"]) if r["payload_json"] else None,
                        }
                        for r in rows
                    ]
            except Exception:
                con.rollback()
                raise
        finally:
            self._return(con)
        return leased

    def reclaim_expired_leases(self, max_reclaimed: int = 100) -> int:
        """
        Reencola tareas con leases expirados.
        
        Busca tareas en estado 'sent' con leased_at expirado (según lease_ttl)
        y las reencola a 'queued' para que puedan ser procesadas nuevamente.
        """
        sql = """
            UPDATE job_tasks
            SET status = 'queued',
                leased_at = NULL,
                updated_at = NOW()
            WHERE status = 'sent'
              AND leased_at IS NOT NULL
              AND leased_at < DATE_SUB(NOW(), INTERVAL COALESCE(lease_ttl, 300) SECOND)
            LIMIT %s
        """
        
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (max_reclaimed,), "update", "job_tasks")
                reclaimed = cur.rowcount
            con.commit()
            return reclaimed
        finally:
            self._return(con)

    def release_task(self, job_id: str, task_id: str, error: Optional[str]) -> None:
        """
        Si `error` viene con texto, marcamos la task como 'error'. Si es None,
        se devuelve a 'queued' para que vuelva a entrar en el ciclo.
        """
        if error:
            sql = """
                UPDATE job_tasks
                SET status='error', error_msg=%s, finished_at=NOW(), leased_at=NULL, updated_at=NOW()
                WHERE job_id=%s AND task_id=%s
            """
            args = (error[:2000], job_id, task_id)
        else:
            sql = """
                UPDATE job_tasks
                SET status='queued', leased_at=NULL, updated_at=NOW()
                WHERE job_id=%s AND task_id=%s
            """
            args = (job_id, task_id)
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, args, "update", "job_tasks")
            con.commit()
        finally:
            self._return(con)
