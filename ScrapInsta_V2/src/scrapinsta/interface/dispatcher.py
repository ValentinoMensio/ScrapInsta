# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import signal
import sys
import time
import multiprocessing as mp
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from scrapinsta.config.settings import Settings
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL
from scrapinsta.interface.workers.instagram_worker import InstagramWorker
from scrapinsta.interface.workers.router import Router, Job
from scrapinsta.interface.workers.deps_factory import get_factory
from scrapinsta.interface.queues import build_queues, TaskQueuePort, ResultQueuePort
from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope


def _configure_logging(level: str = "INFO") -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s [%(levelname)s] pid=%(process)d %(name)s: %(message)s",
    )
    for noisy in ("selenium", "seleniumwire", "undetected_chromedriver", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("dispatcher")


def _start_worker_process(
    account: str,
    task_q: TaskQueuePort,
    result_q: ResultQueuePort,
    stop_ev: mp.Event,
    settings: Settings,
) -> mp.Process:
    def _receive(timeout_s: float) -> Optional[TaskEnvelope]:
        return task_q.receive(timeout_s)

    def _send(res: ResultEnvelope) -> None:
        result_q.send(res)

    def _stop_cb() -> bool:
        return stop_ev.is_set()

    def _run() -> None:
        factory = get_factory(account, settings=settings)
        worker = InstagramWorker(
            name=f"worker:{account}",
            factory=factory,
            receive=_receive,
            send=_send,
            stop_event=_stop_cb,
            poll_interval_s=0.1,
            heartbeat_s=10.0,
        )
        worker.run()

    proc = mp.Process(target=_run, name=f"WorkerProc:{account}", daemon=True)
    proc.start()
    return proc


def _load_job_meta(store: JobStoreSQL, job_id: str) -> Dict[str, Any]:
    sql = "SELECT kind, priority, batch_size, extra_json FROM jobs WHERE id=%s LIMIT 1"
    with store._connect() as con:
        with con.cursor() as cur:
            cur.execute(sql, (job_id,))
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"job {job_id!r} no existe")
            return {
                "kind": row["kind"],
                "priority": int(row["priority"]),
                "batch_size": int(row["batch_size"]),
                "extra": json.loads(row["extra_json"]) if row.get("extra_json") else None,
            }


def _derive_items_for_fetch(store: JobStoreSQL, job_id: str) -> List[str]:
    sql = """
        SELECT username
        FROM job_tasks
        WHERE job_id=%s AND username IS NOT NULL
        ORDER BY created_at ASC
        LIMIT 1
    """
    with store._connect() as con:
        with con.cursor() as cur:
            cur.execute(sql, (job_id,))
            row = cur.fetchone()
            if not row or not row.get("username"):
                raise RuntimeError(f"no se encontró username semilla para job {job_id}")
            target = str(row["username"]).strip().lower()
            if not target:
                raise RuntimeError(f"username vacío en semilla de job {job_id}")
            return [target]


class FetchToAnalyzeOrchestrator:
    """Encadena fetch_followings → analyze_profile, de forma idempotente (una sola vez por fetch)."""

    def __init__(self, store: JobStoreSQL, router: Router) -> None:
        self._store = store
        self._router = router
        self._created_once: Set[str] = set()

    def _seed_owner(self, job_id: str) -> Optional[str]:
        sql = """
            SELECT username
            FROM job_tasks
            WHERE job_id=%s AND username IS NOT NULL
            ORDER BY created_at ASC
            LIMIT 1
        """
        with self._store._connect() as con:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
                row = cur.fetchone()
                if row and row.get("username"):
                    owner = (row["username"] or "").strip().lower()
                    return owner or None
        return None

    def _find_follow_cols(self) -> tuple[str, str]:
        return ("username_target", "username_origin")

    def _parse_fetch_limit(self, job_id: str) -> int | None:
        """
        Obtiene el límite pedido para el fetch desde la metadata del job
        (extra_json.limit). Deja de depender del formato del id.
        """
        try:
            meta = _load_job_meta(self._store, job_id)
            extra = meta.get("extra") or {}
            val = int(extra.get("limit")) if "limit" in extra else None
            if val and val > 0:
                return val
        except Exception:
            return None
        return None

    def _db_followings_for_owner(self, owner: str, limit: int = 500) -> list[str]:
        follow_col, source_col = self._find_follow_cols()
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
        out: list[str] = []
        with self._store._connect() as con:
            with con.cursor() as cur:
                cur.execute(sql, params)
                for r in (cur.fetchall() or []):
                    v = (r.get("u") or "").strip().lower()
                    if v:
                        out.append(v)

        logging.getLogger("dispatcher").info(
            "fetch→analyze: follow_col=%s, source_col=%s, order=%s, owner=%s, items=%d",
            follow_col, source_col, order_col, owner, len(out)
        )
        return out

    def on_result(self, res: ResultEnvelope, all_tasks_finished_fn) -> None:
        task_id = getattr(res, "task_id", None)
        corr = getattr(res, "correlation_id", None)
        if not task_id or not corr:
            return
        try:
            _job, kind, _user = str(task_id).rsplit(":", 2)
        except Exception:
            return
        logging.getLogger("dispatcher").info(
            "on_result: job_id=%s kind=%s user=%s", _job, kind, _user
        )
        if kind != "fetch_followings":
            return

        try:
            if not all_tasks_finished_fn(corr):
                return
        except Exception:
            return

        if corr in self._created_once:
            return

        owner = self._seed_owner(corr)
        if not owner:
            logging.getLogger("dispatcher").warning("fetch→analyze: no owner seed for job %s", corr)
            return

        limit_req = self._parse_fetch_limit(corr) or 500

        items: list[str] = []
        try:
            res_payload = getattr(res, "result", None) or {}
            fetched = res_payload.get("followings") if isinstance(res_payload, dict) else None
            if isinstance(fetched, list):
                items = [str(u).strip().lower() for u in fetched if isinstance(u, str) and u.strip()]
                if limit_req:
                    items = items[: int(limit_req)]
                logging.getLogger("dispatcher").info(
                    "fetch→analyze: usando %d followings del resultado (limit_req=%d)",
                    len(items), limit_req
                )
        except Exception as e:
            logging.getLogger("dispatcher").warning(
                "fetch→analyze: error extrayendo followings del resultado: %s", e
            )
            items = []

        if not items:
            items = self._db_followings_for_owner(owner, limit=limit_req)
            logging.getLogger("dispatcher").info(
                "fetch→analyze: fallback a DB, obtenidos %d followings (limit_req=%d)",
                len(items), limit_req
            )

        try:
            meta = _load_job_meta(self._store, corr)
            client_acc = None
            if meta and isinstance(meta.get("extra"), dict):
                client_acc = (meta["extra"] or {}).get("client_account")
            if client_acc and self._store:
                items = [u for u in items if not self._store.was_message_sent(client_acc, u)]
        except Exception:
            pass
        
        if limit_req and len(items) > limit_req:
            logging.getLogger("dispatcher").warning(
                "fetch→analyze: items exceden límite (%d > %d), recortando", len(items), limit_req
            )
            items = items[: int(limit_req)]
        
        if not items:
            logging.getLogger("dispatcher").info(
                "fetch→analyze: no followings disponibles para %s (fetch=%s)", owner, corr
            )
            return

        analyze_job_id = f"analyze:{corr}"
        try:
            self._store.create_job(
                job_id=analyze_job_id,
                kind="analyze_profile",
                priority=5,
                batch_size=25,
                extra={},
                total_items=len(items),
            )
            self._store.mark_job_running(analyze_job_id)

            for u in items:
                task_id2 = f"{analyze_job_id}:analyze_profile:{u}"
                self._store.add_task(
                    job_id=analyze_job_id,
                    task_id=task_id2,
                    correlation_id=analyze_job_id,
                    account_id=None,
                    username=u,
                    payload={"username": u},
                )

            analyze_job = Job(
                job_id=analyze_job_id,
                kind="analyze_profile",
                items=items,
                batch_size=25,
                priority=5,
                extra=None,
            )
            self._router.add_job(analyze_job)
            logging.getLogger("dispatcher").info(
                "Creado Job analyze_profile %s (items=%d) desde fetch=%s",
                analyze_job_id, len(items), corr
            )
        except Exception as e:
            logging.getLogger("dispatcher").warning(
                "No se pudo crear job analyze_profile para %s: %s", corr, e
            )
        finally:
            self._created_once.add(corr)


def run(log_level: str = "INFO", scan_every_s: float = 2.0, tick_sleep: float = 0.05) -> None:
    _configure_logging(log_level)

    settings = Settings()
    log.info("[dispatcher] DB_DSN=%s", settings.db_dsn)
    store = JobStoreSQL(settings.db_dsn)

    cfg_accounts = settings.get_accounts()
    if not cfg_accounts:
        log.error("No hay cuentas bot configuradas en Settings.")
        sys.exit(1)

    accounts = [a.username for a in cfg_accounts]
    task_qs, result_qs, backend_name = build_queues(settings=settings, accounts=accounts)
    log.info("Backend de colas: %s", backend_name)

    send_by_acc: Dict[str, callable] = {}
    stop_events: Dict[str, mp.Event] = {}
    procs: Dict[str, mp.Process] = {}
    for acc in accounts:
        sev = mp.Event()
        stop_events[acc] = sev
        send_by_acc[acc] = task_qs[acc].send
        proc = _start_worker_process(acc, task_qs[acc], result_qs[acc], sev, settings)
        procs[acc] = proc
        log.info("Worker lanzado para %s (pid=%s)", acc, proc.pid)

    router = Router(
        accounts=accounts, 
        send_fn_by_account=send_by_acc, 
        job_store=store,
        config=settings.get_router_config(),
    )

    f2a = FetchToAnalyzeOrchestrator(store, router)

    loaded_jobs: Set[str] = set()
    stop = {"flag": False}

    def _sigterm(*_a):
        log.warning("SIGTERM/SIGINT recibido. Parando…")
        stop["flag"] = True
        router.stop_accepting()

    signal.signal(signal.SIGINT, _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)

    log.info("Dispatcher iniciado; escaneando DB cada %.1fs…", scan_every_s)

    last_scan = 0.0
    last_cleanup = 0.0
    try:
        while not stop["flag"]:
            now = time.time()

            if now - last_scan >= scan_every_s:
                last_scan = now
                try:
                    job_ids = store.pending_jobs()
                except Exception as e:
                    log.warning("pending_jobs() falló: %s", e)
                    job_ids = []

                for jid in job_ids:
                    if jid in loaded_jobs:
                        continue
                    try:
                        meta = _load_job_meta(store, jid)
                        kind = meta["kind"]
                        prio = meta["priority"] if meta["priority"] > 0 else 5
                        batch = meta["batch_size"] if meta["batch_size"] > 0 else 1
                        extra = meta["extra"]

                        if kind == "fetch_followings":
                            items = _derive_items_for_fetch(store, jid)
                        elif kind == "analyze_profile":
                            items = []
                        else:
                            log.info("Job %s con kind %r aún no soportado por dispatcher; lo omito.", jid, kind)
                            loaded_jobs.add(jid)
                            continue

                        job = Job(
                            job_id=jid,
                            kind=kind,
                            items=items,
                            batch_size=batch,
                            priority=prio,
                            extra=extra,
                        )

                        try:
                            router.add_job(job)
                            log.info("Job %s cargado en router (%s, items=%s).", jid, kind, items)
                        finally:
                            loaded_jobs.add(jid)

                    except Exception as e:
                        if "duplicado" in str(e).lower() or "duplicate" in str(e).lower():
                            loaded_jobs.add(jid)
                            log.warning("Job %s ya estaba en router: lo marco como cargado.", jid)
                        else:
                            log.error("Error cargando job %s: %s", jid, e)

            router.dispatch_tick()

            if now - last_cleanup >= 3600.0:
                try:
                    removed = store.cleanup_stale_tasks(older_than_days=1)
                    if removed:
                        log.info("Limpieza de job_tasks obsoletas: %d eliminadas", removed)
                    removed2 = store.cleanup_finished_tasks(older_than_days=90)
                    if removed2:
                        log.info("Limpieza de job_tasks finalizadas: %d eliminadas", removed2)
                except Exception:
                    pass
                last_cleanup = now

            for rq in result_qs.values():
                while True:
                    res = rq.try_get_nowait()
                    if res is None:
                        break
                    router.on_result(res)
                    f2a.on_result(res, all_tasks_finished_fn=lambda jid: store.all_tasks_finished(jid))

            time.sleep(tick_sleep)

        log.info("Parando…")

    finally:
        for ev in stop_events.values():
            ev.set()
        for acc, p in procs.items():
            p.join(timeout=10)
            if p.is_alive():
                log.warning("Forzando cierre de %s (pid=%s)", acc, p.pid)
                p.terminate()
        log.info("Dispatcher detenido.")


if __name__ == "__main__":
    run()
