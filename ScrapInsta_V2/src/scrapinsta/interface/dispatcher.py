from __future__ import annotations

import json
import os
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
from scrapinsta.crosscutting.logging_config import (
    configure_structured_logging,
    get_logger,
    bind_request_context,
)
from scrapinsta.crosscutting.metrics import (
    workers_active,
    jobs_active,
    cleanup_operations_total,
    cleanup_rows_deleted_total,
    cleanup_duration_seconds,
    cleanup_last_run_timestamp,
    lease_cleanup_reclaimed_total,
    lease_cleanup_duration_seconds,
)

# Configurar logging estructurado
configure_structured_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
    include_process_id=True,
)
log = get_logger("dispatcher")


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

def _items_from_meta_for_job(job_id: str, meta: Dict[str, Any], *, store: JobStoreSQL) -> List[str]:
    """
    Determina los items (usernames) de un job a partir de extra_json.
    Mantiene compatibilidad con jobs antiguos (que tenían seed task en job_tasks).
    """
    kind = str(meta.get("kind") or "").strip()
    extra = meta.get("extra") or {}

    if kind == "fetch_followings":
        target = (extra.get("target_username") or "").strip().lower()
        if target:
            return [target]
        # Compatibilidad hacia atrás: seed task persistida
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
                if row and row.get("username"):
                    v = str(row["username"]).strip().lower()
                    if v:
                        return [v]
        raise RuntimeError(f"no se encontró target_username para job {job_id}")

    if kind == "analyze_profile":
        raw = extra.get("usernames")
        if isinstance(raw, list):
            return [str(u).strip().lower() for u in raw if isinstance(u, str) and u.strip()]
        return []

    return []


def _ensure_tasks_for_job(store: JobStoreSQL, job_id: str, kind: str, items: List[str], extra: Optional[dict]) -> None:
    """
    Asegura que existan tasks en DB para los items del job.
    Idempotente: add_task hace upsert y NO pisa status si ya fue completada.
    """
    client_id = store.get_job_client_id(job_id)
    if not client_id:
        log.error("job_missing_client_id", job_id=job_id)
        raise ValueError(f"Job {job_id} no tiene client_id asignado")

    common: Dict[str, Any] = {}
    if isinstance(extra, dict):
        # Evitar payloads gigantes/duplicados por task (ej: lista completa de usernames)
        for k, v in extra.items():
            if k in {"usernames"}:
                continue
            common[k] = v

    for u in items:
        username = (u or "").strip().lower()
        if not username:
            continue
        task_id = f"{job_id}:{kind}:{username}"
        payload: Dict[str, Any] = {"username": username}
        payload.update(common)
        store.add_task(
            job_id=job_id,
            task_id=task_id,
            correlation_id=job_id,
            account_id=None,
            username=username,
            payload=payload,
            client_id=client_id,
        )


class FetchToAnalyzeOrchestrator:
    """Encadena fetch_followings → analyze_profile, de forma idempotente (una sola vez por fetch)."""

    def __init__(self, store: JobStoreSQL, router: Router) -> None:
        self._store = store
        self._router = router
        self._created_once: Set[str] = set()

    def _seed_owner(self, job_id: str) -> Optional[str]:
        try:
            meta = _load_job_meta(self._store, job_id)
            extra = meta.get("extra") or {}
            owner = (extra.get("target_username") or "").strip().lower()
            return owner or None
        except Exception:
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

        log.info(
            "fetch_to_analyze_db_followings",
            follow_col=follow_col,
            source_col=source_col,
            order_col=order_col,
            owner=owner,
            items=len(out),
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
        log.info("on_result_received", job_id=_job, kind=kind, user=_user)
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
            log.warning("fetch_to_analyze_no_owner_seed", job_id=corr)
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
                log.info("fetch_to_analyze_from_result", items=len(items), limit_req=limit_req)
        except Exception as e:
            log.warning("fetch_to_analyze_extract_error", error=str(e))
            items = []

        if not items:
            items = self._db_followings_for_owner(owner, limit=limit_req)
            log.info("fetch_to_analyze_db_fallback", items=len(items), limit_req=limit_req)

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
            log.warning("fetch_to_analyze_limit_trim", items=len(items), limit_req=limit_req)
            items = items[: int(limit_req)]
        
        if not items:
            log.info("fetch_to_analyze_no_items", owner=owner, fetch_job_id=corr)
            return

        analyze_job_id = f"analyze:{corr}"
        client_id = self._store.get_job_client_id(corr)
        if not client_id:
            log.error(
                "job_missing_client_id",
                job_id=corr,
                message="Job no tiene client_id asignado. Esto no debería ocurrir."
            )
            raise ValueError(f"Job {corr} no tiene client_id asignado. Esto indica un error de datos.")
        try:
            self._store.create_job(
                job_id=analyze_job_id,
                kind="analyze_profile",
                priority=5,
                batch_size=25,
                extra={"usernames": items},
                total_items=len(items),
                client_id=client_id,
            )
            self._store.mark_job_running(analyze_job_id)
            _ensure_tasks_for_job(self._store, analyze_job_id, "analyze_profile", items, {"usernames": items})

            analyze_job = Job(
                job_id=analyze_job_id,
                kind="analyze_profile",
                items=items,
                batch_size=25,
                priority=5,
                extra={"usernames": items},
                pending=self._store.list_queued_usernames(analyze_job_id),
            )
            self._router.add_job(analyze_job)
            log.info("fetch_to_analyze_created_analyze_job", analyze_job_id=analyze_job_id, items=len(items), fetch_job_id=corr)
        except Exception as e:
            log.warning("fetch_to_analyze_create_failed", fetch_job_id=corr, error=str(e))
        finally:
            self._created_once.add(corr)


def run(log_level: str = "INFO", scan_every_s: float = 2.0, tick_sleep: float = 0.05) -> None:
    # Logging ya está configurado al importar el módulo
    # Si se necesita cambiar el nivel, se puede hacer aquí
    if log_level != os.getenv("LOG_LEVEL", "INFO"):
        configure_structured_logging(
            level=log_level,
            json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
            include_process_id=True,
        )

    settings = Settings()
    log.info("dispatcher_starting", db_dsn=settings.db_dsn)
    store = JobStoreSQL(settings.db_dsn)

    cfg_accounts = settings.get_accounts()
    if not cfg_accounts:
        log.error("no_accounts_configured", message="No hay cuentas bot configuradas en Settings")
        sys.exit(1)

    accounts = [a.username for a in cfg_accounts]
    task_qs, result_qs, backend_name = build_queues(settings=settings, accounts=accounts)
    log.info("queues_initialized", backend=backend_name, account_count=len(accounts))

    send_by_acc: Dict[str, callable] = {}
    stop_events: Dict[str, mp.Event] = {}
    procs: Dict[str, mp.Process] = {}
    for acc in accounts:
        sev = mp.Event()
        stop_events[acc] = sev
        send_by_acc[acc] = task_qs[acc].send
        proc = _start_worker_process(acc, task_qs[acc], result_qs[acc], sev, settings)
        procs[acc] = proc
        workers_active.labels(account=acc).inc()
        log.info("worker_started", account=acc, pid=proc.pid)

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
        log.warning("shutdown_signal_received", signal="SIGTERM/SIGINT")
        stop["flag"] = True
        router.stop_accepting()

    signal.signal(signal.SIGINT, _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)

    log.info("dispatcher_ready", scan_interval_s=scan_every_s, accounts=accounts)

    last_scan = 0.0
    last_cleanup = 0.0
    last_lease_cleanup = 0.0
    lease_cleanup_interval = float(os.getenv("LEASE_CLEANUP_INTERVAL", "60"))
    max_reclaimed_per_run = int(os.getenv("LEASE_CLEANUP_MAX_RECLAIMED", "100"))
    cleanup_interval = float(os.getenv("CLEANUP_INTERVAL", "86400"))  # Default: 24 horas
    cleanup_stale_days = int(os.getenv("CLEANUP_STALE_DAYS", "1"))  # Default: 1 día
    cleanup_finished_days = int(os.getenv("CLEANUP_FINISHED_DAYS", "90"))  # Default: 90 días
    cleanup_batch_size = int(os.getenv("CLEANUP_BATCH_SIZE", "1000"))  # Default: 1000 filas por lote
    try:
        while not stop["flag"]:
            now = time.time()

            if now - last_scan >= scan_every_s:
                last_scan = now
                try:
                    job_ids = store.pending_jobs()
                except Exception as e:
                    log.warning("pending_jobs_failed", error=str(e))
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
                            items = _items_from_meta_for_job(jid, meta, store=store)
                        elif kind == "analyze_profile":
                            items = _items_from_meta_for_job(jid, meta, store=store)
                        else:
                            log.info(
                                "job_kind_not_supported",
                                job_id=jid,
                                kind=kind,
                                message="Job kind no soportado por dispatcher",
                            )
                            loaded_jobs.add(jid)
                            continue

                        job = Job(
                            job_id=jid,
                            kind=kind,
                            items=items,
                            batch_size=batch,
                            priority=prio,
                            extra=extra,
                            pending=store.list_queued_usernames(jid),
                        )

                        try:
                            # Evitar doble expansión Job→Tasks entre 2 dispatchers:
                            lock_name = f"scrapinsta:expand:{jid}"
                            got_lock = store.try_advisory_lock(lock_name, timeout_s=0)
                            if got_lock:
                                try:
                                    _ensure_tasks_for_job(store, jid, kind, items, extra if isinstance(extra, dict) else None)
                                    store.mark_job_running(jid)
                                finally:
                                    try:
                                        store.release_advisory_lock(lock_name)
                                    except Exception:
                                        pass
                            job.pending = store.list_queued_usernames(jid)
                            router.add_job(job)
                            jobs_active.labels(status="running").inc()
                            log.info(
                                "job_loaded",
                                job_id=jid,
                                kind=kind,
                                items_count=len(items),
                            )
                        finally:
                            loaded_jobs.add(jid)

                    except Exception as e:
                        if "duplicado" in str(e).lower() or "duplicate" in str(e).lower():
                            loaded_jobs.add(jid)
                            log.warning(
                                "job_already_loaded",
                                job_id=jid,
                                message="Job ya estaba en router",
                            )
                        else:
                            log.error(
                                "job_load_error",
                                job_id=jid,
                                error=str(e),
                            )

            router.dispatch_tick()

            if now - last_lease_cleanup >= lease_cleanup_interval:
                try:
                    lease_cleanup_start = time.time()
                    reclaimed = store.reclaim_expired_leases(max_reclaimed=max_reclaimed_per_run)
                    lease_cleanup_duration = time.time() - lease_cleanup_start
                    
                    if reclaimed > 0:
                        log.info(
                            "leases_reclaimed",
                            count=reclaimed,
                            max_reclaimed=max_reclaimed_per_run,
                        )
                    
                    lease_cleanup_reclaimed_total.inc(reclaimed)
                    lease_cleanup_duration_seconds.observe(lease_cleanup_duration)
                except Exception as e:
                    log.warning("lease_cleanup_error", error=str(e))
                last_lease_cleanup = now

            if now - last_cleanup >= cleanup_interval:
                try:
                    cleanup_start = time.time()
                    
                    stale_start = time.time()
                    removed = store.cleanup_stale_tasks(older_than_days=cleanup_stale_days, batch_size=cleanup_batch_size)
                    stale_duration = time.time() - stale_start
                    if removed:
                        log.info(
                            "cleanup_stale_tasks",
                            removed_count=removed,
                            older_than_days=cleanup_stale_days,
                        )
                        cleanup_operations_total.labels(operation_type="stale_tasks").inc()
                        cleanup_rows_deleted_total.labels(operation_type="stale_tasks", table="job_tasks").inc(removed)
                        cleanup_duration_seconds.labels(operation_type="stale_tasks").observe(stale_duration)
                        cleanup_last_run_timestamp.labels(operation_type="stale_tasks").set(now)
                    
                    finished_start = time.time()
                    removed2 = store.cleanup_finished_tasks(older_than_days=cleanup_finished_days, batch_size=cleanup_batch_size)
                    finished_duration = time.time() - finished_start
                    if removed2:
                        log.info(
                            "cleanup_finished_tasks",
                            removed_count=removed2,
                            older_than_days=cleanup_finished_days,
                        )
                        cleanup_operations_total.labels(operation_type="finished_tasks").inc()
                        cleanup_rows_deleted_total.labels(operation_type="finished_tasks", table="job_tasks").inc(removed2)
                        cleanup_duration_seconds.labels(operation_type="finished_tasks").observe(finished_duration)
                        cleanup_last_run_timestamp.labels(operation_type="finished_tasks").set(now)
                    
                    orphaned_start = time.time()
                    removed3 = store.cleanup_orphaned_jobs(older_than_days=7)
                    orphaned_duration = time.time() - orphaned_start
                    if removed3:
                        log.info(
                            "cleanup_orphaned_jobs",
                            removed_count=removed3,
                        )
                        cleanup_operations_total.labels(operation_type="orphaned_jobs").inc()
                        cleanup_rows_deleted_total.labels(operation_type="orphaned_jobs", table="jobs").inc(removed3)
                        cleanup_duration_seconds.labels(operation_type="orphaned_jobs").observe(orphaned_duration)
                        cleanup_last_run_timestamp.labels(operation_type="orphaned_jobs").set(now)
                    
                    cleanup_duration = time.time() - cleanup_start
                    if removed or removed2 or removed3:
                        log.info(
                            "cleanup_completed",
                            total_removed=removed + removed2 + removed3,
                            duration_ms=round(cleanup_duration * 1000, 2),
                        )
                except Exception as e:
                    log.warning("cleanup_error", error=str(e))
                last_cleanup = now

            for rq in result_qs.values():
                while True:
                    res = rq.try_get_nowait()
                    if res is None:
                        break
                    router.on_result(res)
                    f2a.on_result(res, all_tasks_finished_fn=lambda jid: store.all_tasks_finished(jid))

            time.sleep(tick_sleep)

        log.info("dispatcher_stopping")

    finally:
        for ev in stop_events.values():
            ev.set()
        for acc, p in procs.items():
            p.join(timeout=10)
            if p.is_alive():
                log.warning("worker_force_terminate", account=acc, pid=p.pid)
                p.terminate()
            workers_active.labels(account=acc).dec()
        log.info("dispatcher_stopped")


if __name__ == "__main__":
    run()
