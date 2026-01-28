from __future__ import annotations
import json
import time
from typing import Any, Dict, List, Optional
import threading
from queue import Queue, Empty
import os
from urllib.parse import urlparse, unquote

import pymysql  # pip install PyMySQL

from scrapinsta.crosscutting.retry import retry, RetryError

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
        # Parse DSN con urllib.parse para mayor robustez.
        parsed = urlparse(self._dsn)
        if parsed.scheme != "mysql":
            raise ValueError("DSN inválido: esquema esperado 'mysql'")
        user = unquote(parsed.username or "")
        pwd = unquote(parsed.password or "")
        host = parsed.hostname or ""
        port = int(parsed.port or 3307)
        db = (parsed.path or "").lstrip("/")
        if not host or not db:
            raise ValueError("DSN inválido: host y db son requeridos")
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
            connect_timeout = float(os.getenv("DB_CONNECT_TIMEOUT", "5.0"))
            read_timeout = float(os.getenv("DB_READ_TIMEOUT", "10.0"))
            write_timeout = float(os.getenv("DB_WRITE_TIMEOUT", "10.0"))
            return pymysql.connect(
                host=host,
                port=int(port),
                user=user,
                password=pwd,
                database=db,
                charset="utf8mb4",
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                write_timeout=write_timeout,
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
                ssl=ssl_params,
            )

        retries = int(os.getenv("DB_CONNECT_RETRIES", "2"))

        @retry((pymysql.err.OperationalError, pymysql.err.InterfaceError), max_retries=retries)
        def _new_conn_retry() -> pymysql.connections.Connection:
            return _new_conn()

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
        try:
            con = _new_conn_retry()
        except RetryError as e:
            raise e.last_error or e
        db_connections_active.set(self._pool.qsize() + 1)
        return con

    def _return(self, con: pymysql.connections.Connection) -> None:
        """Devuelve la conexión al pool (o la cierra si no se puede reutilizar)."""
        try:
            if con and not con._closed and not con.get_autocommit():
                # Cerrar transacción abierta para evitar snapshots viejos
                try:
                    con.commit()
                except Exception:
                    pass
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
              extra_json=VALUES(extra_json), total_items=VALUES(total_items),
              client_id=VALUES(client_id), updated_at=CURRENT_TIMESTAMP
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
              -- Idempotencia real: NO pisar valores existentes si ya están seteados.
              correlation_id=COALESCE(correlation_id, VALUES(correlation_id)),
              account_id=COALESCE(account_id, VALUES(account_id)),
              username=COALESCE(username, VALUES(username)),
              payload_json=COALESCE(payload_json, VALUES(payload_json)),
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
        """
        Marca task como 'sent' y setea sent_at.

        Nota: también seteamos leased_at para habilitar recuperación automática vía
        reclaim_expired_leases() si el worker muere o se pierde el resultado.
        """
        sql = "UPDATE job_tasks SET status='sent', sent_at=NOW(), leased_at=NOW(), updated_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id, task_id), "update", "job_tasks")
            con.commit()
        finally:
            self._return(con)

    def list_usernames_by_status(self, job_id: str, statuses: list[str]) -> set[str]:
        """
        Lista usernames de tasks para un job filtrando por estados.

        Se usa para reconstruir 'pending' de forma idempotente al reiniciar:
        - queued: pendientes de despachar
        - sent: en vuelo (no redespachar)
        - ok/error: ya finalizadas
        """
        if not statuses:
            return set()
        st = [str(s).strip().lower() for s in statuses if str(s).strip()]
        if not st:
            return set()
        placeholders = ", ".join(["%s"] * len(st))
        # Cinturón y tirantes multi-tenant/consistencia:
        # Validamos que job_tasks.client_id coincida con jobs.client_id para ese job_id.
        sql = f"""
            SELECT jt.username
            FROM job_tasks jt
            INNER JOIN jobs j ON jt.job_id = j.id AND jt.client_id = j.client_id
            WHERE jt.job_id=%s AND jt.status IN ({placeholders})
              AND jt.username IS NOT NULL AND jt.username <> ''
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                params: tuple = (job_id, *st)
                self._execute_query(cur, sql, params, "select", "job_tasks")
                rows = cur.fetchall() or []
                return {str(r.get("username")).strip().lower() for r in rows if (r.get("username") or "").strip()}
        finally:
            self._return(con)

    def list_queued_usernames(self, job_id: str) -> set[str]:
        """Atajo: usernames pendientes (status='queued') para un job."""
        return self.list_usernames_by_status(job_id, ["queued"])

    def mark_task_ok(self, job_id: str, task_id: str, result: Optional[Dict[str, Any]]) -> None:
        """Marca task como 'ok' y cierra timestamps."""
        sql = (
            "UPDATE job_tasks "
            "SET status='ok', finished_at=NOW(), leased_at=NULL, lease_expires_at=NULL, leased_by=NULL, updated_at=NOW() "
            "WHERE job_id=%s AND task_id=%s"
        )
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id, task_id), "update", "job_tasks")
            con.commit()
        finally:
            self._return(con)

    def claim_task(self, job_id: str, task_id: str, account_id: str) -> bool:
        """
        Claim atómico de una task para ejecución (anti-duplicados con múltiples dispatchers).

        Solo permite el claim si la task está en status='queued'.
        Setea account_id, sent_at y leased_at (lease start) en el mismo UPDATE.
        """
        acc = _norm(account_id)
        if not acc:
            raise ValueError("account_id inválido para claim_task")
        sql = """
            UPDATE job_tasks jt
            INNER JOIN jobs j ON jt.job_id = j.id AND jt.client_id = j.client_id
            SET jt.status='sent',
                jt.account_id=%s,
                jt.sent_at=NOW(),
                jt.leased_at=NOW(),
                jt.lease_expires_at=DATE_ADD(NOW(), INTERVAL COALESCE(jt.lease_ttl, 300) SECOND),
                jt.leased_by=NULL,
                jt.attempts=COALESCE(jt.attempts, 0) + 1,
                jt.updated_at=NOW()
            WHERE jt.job_id=%s
              AND jt.task_id=%s
              AND jt.status='queued'
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (acc, job_id, task_id), "update", "job_tasks")
                claimed = int(cur.rowcount or 0)
            con.commit()
            return claimed == 1
        finally:
            self._return(con)

    def try_advisory_lock(self, name: str, timeout_s: int = 0) -> bool:
        """
        Advisory lock (MySQL GET_LOCK) para secciones críticas sin tocar schema.
        Útil para evitar doble expansión Job→Tasks entre 2 dispatchers.
        """
        lock_name = str(name)
        sql = "SELECT GET_LOCK(%s, %s) AS got"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (lock_name, int(timeout_s)), "select", "jobs")
                row = cur.fetchone() or {}
                return int(row.get("got") or 0) == 1
        finally:
            self._return(con)

    def release_advisory_lock(self, name: str) -> None:
        sql = "SELECT RELEASE_LOCK(%s) AS released"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (str(name),), "select", "jobs")
                con.commit()
        finally:
            self._return(con)

    def mark_task_error(self, job_id: str, task_id: str, error: str) -> None:
        """Marca task como 'error' con mensaje (recortado a 2000 chars)."""
        sql = (
            "UPDATE job_tasks "
            "SET status='error', error_msg=%s, finished_at=NOW(), leased_at=NULL, lease_expires_at=NULL, leased_by=NULL, updated_at=NOW() "
            "WHERE job_id=%s AND task_id=%s"
        )
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
                con.commit()
                if row:
                    return row.get("client_id")
                return None
        finally:
            self._return(con)

    def job_exists(self, job_id: str) -> bool:
        """
        Verifica si un job existe en la base de datos.
        Útil para garantizar idempotencia en operaciones como creación de jobs derivados.
        """
        sql = "SELECT 1 FROM jobs WHERE id = %s LIMIT 1"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "select", "jobs")
                row = cur.fetchone()
                return row is not None
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
                con.commit()
                return {
                    "queued": int(row.get("queued") or 0),
                    "sent": int(row.get("sent") or 0),
                    "ok": int(row.get("ok") or 0),
                    "error": int(row.get("error") or 0),
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

    def count_messages_sent_today(self, client_id: str) -> int:
        """Cuenta mensajes enviados hoy por client_id (según last_sent_at)."""
        cid = (client_id or "").strip()
        if not cid:
            return 0
        sql = """
            SELECT COUNT(*) AS total
            FROM messages_sent
            WHERE client_id=%s AND last_sent_at >= CURDATE()
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (cid,), "select", "messages_sent")
                row = cur.fetchone() or {}
                return int(row.get("total") or 0)
        finally:
            self._return(con)

    def count_tasks_sent_today(self, client_id: str) -> int:
        """Cuenta tareas en estado 'sent' hoy por client_id (en vuelo)."""
        cid = (client_id or "").strip()
        if not cid:
            return 0
        sql = """
            SELECT COUNT(*) AS total
            FROM job_tasks
            WHERE client_id=%s AND status='sent' AND sent_at >= CURDATE()
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (cid,), "select", "job_tasks")
                row = cur.fetchone() or {}
                return int(row.get("total") or 0)
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
            SET status = 'sent',
                sent_at = NOW(),
                leased_at = NOW(),
                lease_expires_at = DATE_ADD(NOW(), INTERVAL COALESCE(lease_ttl, 300) SECOND),
                leased_by = NULL,
                attempts = COALESCE(attempts, 0) + 1,
                updated_at = NOW()
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
                lease_expires_at = NULL,
                leased_by = NULL,
                updated_at = NOW()
            WHERE status = 'sent'
              AND (
                (lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
                OR (
                  lease_expires_at IS NULL
                  AND leased_at IS NOT NULL
                  AND leased_at < DATE_SUB(NOW(), INTERVAL COALESCE(lease_ttl, 300) SECOND)
                )
              )
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
                SET status='queued', leased_at=NULL, lease_expires_at=NULL, leased_by=NULL, updated_at=NOW()
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

    def requeue_task_with_attempts_cap(
        self,
        job_id: str,
        task_id: str,
        *,
        max_attempts: int,
        final_error_msg: str = "retry exhausted",
    ) -> bool:
        """
        Reencola una task retryable si todavía no alcanzó el máximo de attempts.
        - attempts se incrementa al hacer claim/lease (claim_task/lease_tasks).
        - Si attempts >= max_attempts, se marca como error definitivo (evita loop infinito).

        Returns:
            True si se reencoló (status='queued'), False si se marcó error definitivo.
        """
        max_a = int(max_attempts or 0)
        if max_a <= 0:
            max_a = 1

        sql = """
            UPDATE job_tasks jt
            INNER JOIN jobs j ON jt.job_id = j.id AND jt.client_id = j.client_id
            SET
                jt.status = CASE WHEN COALESCE(jt.attempts, 0) < %s THEN 'queued' ELSE 'error' END,
                jt.leased_at = NULL,
                jt.lease_expires_at = NULL,
                jt.leased_by = NULL,
                jt.finished_at = CASE WHEN COALESCE(jt.attempts, 0) < %s THEN NULL ELSE NOW() END,
                jt.error_msg = CASE WHEN COALESCE(jt.attempts, 0) < %s THEN jt.error_msg ELSE %s END,
                jt.updated_at = NOW()
            WHERE jt.job_id=%s
              AND jt.task_id=%s
              AND jt.status='sent'
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(
                    cur,
                    sql,
                    (max_a, max_a, max_a, str(final_error_msg or "retry exhausted"), job_id, task_id),
                    "update",
                    "job_tasks",
                )
                cur.execute(
                    "SELECT COALESCE(attempts, 0) AS attempts FROM job_tasks WHERE job_id=%s AND task_id=%s",
                    (job_id, task_id),
                )
                row = cur.fetchone() or {}
                attempts = int(row.get("attempts") or 0)
            con.commit()
            return attempts < max_a
        finally:
            self._return(con)

    def begin_task(self, job_id: str, task_id: str, account_id: str, leased_by: str) -> bool:
        """
        Idempotencia en consumer/worker ante doble delivery inevitable:
        - Solo un worker puede "comenzar" una task (leased_by NULL -> set).
        - Si ya está ok/error o ya tiene leased_by, se saltea.
        """
        acc = _norm(account_id)
        who = str(leased_by or "").strip()
        if not acc or not who:
            return False
        sql = """
            UPDATE job_tasks jt
            INNER JOIN jobs j ON jt.job_id = j.id AND jt.client_id = j.client_id
            SET jt.leased_by=%s,
                jt.updated_at=NOW()
            WHERE jt.job_id=%s
              AND jt.task_id=%s
              AND jt.status='sent'
              AND jt.account_id=%s
              AND jt.leased_by IS NULL
              AND (jt.lease_expires_at IS NULL OR jt.lease_expires_at >= NOW())
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (who, job_id, task_id, acc), "update", "job_tasks")
                started = int(cur.rowcount or 0)
            con.commit()
            return started == 1
        finally:
            self._return(con)

    def get_job_metadata(self, job_id: str) -> Dict[str, Any]:
        """
        Obtiene los metadatos de un job (kind, priority, batch_size, extra_json).
        
        Implementación pública para evitar acoplamiento a métodos privados.
        """
        sql = "SELECT kind, priority, batch_size, extra_json FROM jobs WHERE id=%s LIMIT 1"
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, (job_id,), "select", "jobs")
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(f"job {job_id!r} no existe")
                return {
                    "kind": row["kind"],
                    "priority": int(row["priority"]),
                    "batch_size": int(row["batch_size"]),
                    "extra": json.loads(row["extra_json"]) if row.get("extra_json") else None,
                }
        finally:
            self._return(con)

    def get_followings_for_owner(self, owner: str, limit: int = 500) -> List[str]:
        """
        Obtiene la lista de followings para un owner específico.
        
        Implementación pública para evitar acoplamiento a métodos privados.
        """
        follow_col, source_col = ("username_target", "username_origin")
        order_col = "created_at"
        sql = f"""
            SELECT {follow_col} AS u
            FROM followings
            WHERE {source_col}=%s
            AND {follow_col} IS NOT NULL
            AND {follow_col} <> ''
            GROUP BY {follow_col}
            ORDER BY MAX({order_col}) DESC
            LIMIT %s
        """
        params = (owner, int(limit))
        out: List[str] = []
        con = self._connect()
        try:
            with con.cursor() as cur:
                self._execute_query(cur, sql, params, "select", "followings")
                for r in (cur.fetchall() or []):
                    v = (r.get("u") or "").strip().lower()
                    if v:
                        out.append(v)
        finally:
            self._return(con)
        return out
