from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
import threading
from queue import Queue, Empty
import os

import pymysql  # pip install PyMySQL

from scrapinsta.domain.ports.job_store import JobStorePort


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
        return _new_conn()

    def _return(self, con: pymysql.connections.Connection) -> None:
        """Devuelve la conexión al pool (o la cierra si no se puede reutilizar)."""
        try:
            if con and not con._closed and not con.get_autocommit():
                con.ping(reconnect=True)
            try:
                self._pool.put_nowait(con)
            except Exception:
                con.close()
        except Exception:
            try:
                con.close()
            except Exception:
                pass

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
    ) -> None:
        """Crea (o sobreescribe metadata) de un Job en estado 'pending'."""
        sql = """
            INSERT INTO jobs (id, kind, priority, batch_size, extra_json, total_items, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            ON DUPLICATE KEY UPDATE
              kind=VALUES(kind), priority=VALUES(priority), batch_size=VALUES(batch_size),
              extra_json=VALUES(extra_json), total_items=VALUES(total_items), updated_at=CURRENT_TIMESTAMP
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id, kind, priority, batch_size, _json(extra), total_items))
            con.commit()
        finally:
            self._return(con)

    def mark_job_running(self, job_id: str) -> None:
        """Pone un Job en estado 'running'."""
        sql = "UPDATE jobs SET status='running' WHERE id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
            con.commit()
        finally:
            self._return(con)

    def mark_job_done(self, job_id: str) -> None:
        """Marca un Job como 'done'."""
        sql = "UPDATE jobs SET status='done' WHERE id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
            con.commit()
        finally:
            self._return(con)

    def mark_job_error(self, job_id: str) -> None:
        """Marca un Job como 'error'."""
        sql = "UPDATE jobs SET status='error' WHERE id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
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
    ) -> None:
        """Agrega/actualiza una task como 'queued'."""
        sql = """
            INSERT INTO job_tasks (job_id, task_id, correlation_id, account_id, username, payload_json, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'queued')
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
                cur.execute(sql, (job_id, task_id, correlation_id, account_id, _norm(username), _json(payload)))
            con.commit()
        finally:
            self._return(con)

    def mark_task_sent(self, job_id: str, task_id: str) -> None:
        """Marca task como 'sent' y setea sent_at."""
        sql = "UPDATE job_tasks SET status='sent', sent_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id, task_id))
            con.commit()
        finally:
            self._return(con)

    def mark_task_ok(self, job_id: str, task_id: str, result: Optional[Dict[str, Any]]) -> None:
        """Marca task como 'ok' y cierra timestamps."""
        sql = "UPDATE job_tasks SET status='ok', finished_at=NOW(), updated_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id, task_id))
            con.commit()
        finally:
            self._return(con)

    def mark_task_error(self, job_id: str, task_id: str, error: str) -> None:
        """Marca task como 'error' con mensaje (recortado a 2000 chars)."""
        sql = "UPDATE job_tasks SET status='error', error_msg=%s, finished_at=NOW(), updated_at=NOW() WHERE job_id=%s AND task_id=%s"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (error[:2000], job_id, task_id))
            con.commit()
        finally:
            self._return(con)

    def all_tasks_finished(self, job_id: str) -> bool:
        """True si no quedan tasks 'queued' o 'sent' para ese job."""
        sql = "SELECT COUNT(*) AS c FROM job_tasks WHERE job_id=%s AND status IN ('queued','sent')"
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
                row = cur.fetchone()
                return (row or {}).get("c", 0) == 0
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
                cur.execute(sql)
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

    def job_summary(self, job_id: str) -> Dict[str, Any]:
        """Resumen de cantidades por estado para un job dado."""
        sql = """
          SELECT
            SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
            SUM(CASE WHEN status='sent'   THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN status='ok'     THEN 1 ELSE 0 END) AS ok,
            SUM(CASE WHEN status='error'  THEN 1 ELSE 0 END) AS error
          FROM job_tasks
          WHERE job_id=%s
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
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
    def cleanup_stale_tasks(self, older_than_days: int = 1) -> int:
        """Elimina tasks 'queued' antiguas para mantener limpia la tabla."""
        sql = """
            DELETE FROM job_tasks
            WHERE status = 'queued'
              AND created_at < (NOW() - INTERVAL %s DAY)
        """
        with self._connect() as con:
            with con.cursor() as cur:
                cur.execute(sql, (int(older_than_days),))
                affected = cur.rowcount or 0
            con.commit()
        return int(affected)

    def cleanup_finished_tasks(self, older_than_days: int = 90) -> int:
        """Elimina tasks 'ok'/'error' muy viejas para limitar el tamaño de la tabla."""
        sql = """
            DELETE FROM job_tasks
            WHERE status IN ('ok','error')
              AND finished_at IS NOT NULL
              AND finished_at < (NOW() - INTERVAL %s DAY)
        """
        with self._connect() as con:
            with con.cursor() as cur:
                cur.execute(sql, (int(older_than_days),))
                affected = cur.rowcount or 0
            con.commit()
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
                cur.execute(sql, (cu, du))
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
                cur.execute(sql, (du,))
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
    ) -> None:
        """Registra envío; idempotente gracias al UNIQUE(client_username, dest_username)."""
        sql = """
            INSERT INTO messages_sent (client_username, dest_username, job_id, task_id)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              job_id = VALUES(job_id),
              task_id = VALUES(task_id),
              last_sent_at = CURRENT_TIMESTAMP
        """
        cu = _norm(client_username)
        du = _norm(dest_username)
        if not cu or not du:
            return
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (cu, du, job_id, task_id))
            con.commit()
        finally:
            self._return(con)


    # -----------------------
    # Leasing de tareas (extensiones o workers externos)
    # -----------------------
    def lease_tasks(self, account_id: str, limit: int) -> List[Dict[str, Any]]:
        """
        Obtiene hasta `limit` tareas 'queued' para esta cuenta, las marca 'sent'
        y devuelve los datos mínimos para procesarlas. Usa SKIP LOCKED (MySQL 8+).
        """
        sql_select = """
            SELECT job_id, task_id, username, payload_json
            FROM job_tasks
            WHERE account_id = %s AND status = 'queued'
            ORDER BY created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """
        sql_update = """
            UPDATE job_tasks
            SET status = 'sent', sent_at = NOW(), updated_at = NOW()
            WHERE (job_id, task_id) IN (%s)
        """
        leased: List[Dict[str, Any]] = []

        con = self._connect()
        try:
            try:
                with con.cursor() as cur:
                    cur.execute("START TRANSACTION;")
                    cur.execute(sql_select, (account_id, limit))
                    rows = cur.fetchall() or []
                    if not rows:
                        con.commit()
                        return []

                    keys = ", ".join(["(%s, %s)"] * len(rows))
                    args: list[str] = []
                    for r in rows:
                        args += [r["job_id"], r["task_id"]]
                    cur.execute(sql_update % keys, args)
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

    def release_task(self, job_id: str, task_id: str, error: Optional[str]) -> None:
        """
        Si `error` viene con texto, marcamos la task como 'error'. Si es None,
        se devuelve a 'queued' para que vuelva a entrar en el ciclo.
        """
        if error:
            sql = """
                UPDATE job_tasks
                SET status='error', error_msg=%s, updated_at=NOW()
                WHERE job_id=%s AND task_id=%s
            """
            args = (error[:2000], job_id, task_id)
        else:
            sql = """
                UPDATE job_tasks
                SET status='queued', updated_at=NOW()
                WHERE job_id=%s AND task_id=%s
            """
            args = (job_id, task_id)
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, args)
            con.commit()
        finally:
            self._return(con)
