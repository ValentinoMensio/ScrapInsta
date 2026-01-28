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
    """
    Carga metadatos de un job usando el método público del port.
    Evita acoplamiento a métodos privados del repositorio.
    """
    return store.get_job_metadata(job_id)

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
        # Nota: Esto requiere acceso directo a job_tasks, pero es solo para compatibilidad
        # con jobs antiguos. En el futuro, todos los jobs deberían tener target_username en extra_json.
        sql = """
            SELECT username
            FROM job_tasks
            WHERE job_id=%s AND username IS NOT NULL
            ORDER BY created_at ASC
            LIMIT 1
        """
        # TODO: Agregar método público get_seed_username() al JobStorePort si se necesita
        # Por ahora, mantenemos este acceso directo solo para compatibilidad con jobs antiguos
        con = store._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (job_id,))
                row = cur.fetchone()
                if row and row.get("username"):
                    v = str(row["username"]).strip().lower()
                    if v:
                        return [v]
        finally:
            store._return(con)
        raise RuntimeError(f"no se encontró target_username para job {job_id}")

    if kind == "analyze_profile":
        raw = extra.get("usernames")
        if isinstance(raw, list):
            return [str(u).strip().lower() for u in raw if isinstance(u, str) and u.strip()]
        return []

    return []


def _ensure_tasks_for_job(store: JobStoreSQL, job_id: str, kind: str, items: List[str], extra: Optional[dict], client_id: Optional[str] = None) -> None:
    """
    Asegura que existan tasks en DB para los items del job.
    Idempotente: add_task hace upsert y NO pisa status si ya fue completada.
    """
    if not client_id:
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
    """
    Encadena fetch_followings → analyze_profile, de forma idempotente (una sola vez por fetch).
    
    NOTA: Usa persistencia en BD en lugar de estado in-memory para garantizar idempotencia
    en entornos multi-dispatcher. El estado se verifica consultando si el job de análisis
    ya existe en la base de datos.
    """

    def __init__(self, store: JobStoreSQL, router: Router) -> None:
        self._store = store
        self._router = router
        # Removido: self._created_once: Set[str] = set()
        # Ahora usamos persistencia en BD para garantizar idempotencia multi-dispatcher

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
        """
        Obtiene followings para un owner usando el método público del port.
        Evita acoplamiento a métodos privados del repositorio.
        """
        out = self._store.get_followings_for_owner(owner, limit=limit)
        log.info(
            "fetch_to_analyze_db_followings",
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

        # Verificar idempotencia usando BD en lugar de estado in-memory
        # Esto garantiza que múltiples dispatchers no creen jobs duplicados
        analyze_job_id = f"analyze:{corr}"
        if self._store.job_exists(analyze_job_id):
            log.debug(
                "fetch_to_analyze_job_already_exists",
                fetch_job_id=corr,
                analyze_job_id=analyze_job_id,
                message="Job de análisis ya fue creado, saltando creación"
            )
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

        # Cargar metadata una sola vez y reutilizarla
        meta = None
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

        # analyze_job_id ya fue definido arriba para verificar idempotencia
        # Obtener client_id: primero desde la tabla, luego desde metadata extra como fallback
        client_id = self._store.get_job_client_id(corr)
        if not client_id:
            # Fallback 1: intentar obtener client_id desde metadata extra
            # (para compatibilidad con jobs antiguos que pueden no tener client_id en la tabla)
            if meta and isinstance(meta.get("extra"), dict):
                client_id = (meta["extra"] or {}).get("client_id")
            
            # Fallback 2: intentar obtener desde el job directamente si meta no está disponible
            if not client_id:
                try:
                    job_meta = _load_job_meta(self._store, corr)
                    if job_meta and isinstance(job_meta.get("extra"), dict):
                        client_id = (job_meta["extra"] or {}).get("client_id")
                except Exception:
                    pass
            
            if not client_id:
                log.warning(
                    "job_missing_client_id",
                    job_id=corr,
                    analyze_job_id=analyze_job_id,
                    message="Job no tiene client_id asignado. Saltando creación de job de análisis. "
                            "Esto puede ocurrir con jobs antiguos creados antes de implementar multi-tenancy. "
                            "El dispatcher continuará funcionando normalmente."
                )
                # No lanzar excepción: simplemente saltar la creación del job de análisis
                # El dispatcher debe continuar funcionando normalmente
                return
        
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
            _ensure_tasks_for_job(self._store, analyze_job_id, "analyze_profile", items, {"usernames": items}, client_id=client_id)

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
            log.warning("fetch_to_analyze_create_failed", fetch_job_id=corr, analyze_job_id=analyze_job_id, error=str(e))
            # No agregamos a _created_once porque ya no existe
            # La idempotencia se garantiza consultando BD en la próxima ejecución


def run(log_level: str = "INFO", scan_every_s: float = 2.0, tick_sleep: float = 0.05) -> None:
    """
    Función principal del dispatcher - orquesta todos los servicios.
    
    Refactorizado para usar servicios separados (WorkerManager, JobScanner,
    LeaseCleaner, MaintenanceCleaner) mejorando separación de responsabilidades.
    """
    # Logging ya está configurado al importar el módulo
    if log_level != os.getenv("LOG_LEVEL", "INFO"):
        configure_structured_logging(
            level=log_level,
            json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
            include_process_id=True,
        )

    # Inicialización
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

    # Inicializar servicios
    from scrapinsta.interface.dispatcher.services import (
        WorkerManager,
        JobScanner,
        LeaseCleaner,
        MaintenanceCleaner,
    )
    
    worker_manager = WorkerManager(
        accounts=accounts,
        task_qs=task_qs,
        result_qs=result_qs,
        settings=settings,
        start_worker_fn=_start_worker_process,
    )
    worker_manager.start_all()

    router = Router(
        accounts=accounts,
        send_fn_by_account=worker_manager.get_send_functions(),
        job_store=store,
        config=settings.get_router_config(),
    )

    job_scanner = JobScanner(
        store=store,
        router=router,
        load_job_meta_fn=_load_job_meta,
        items_from_meta_fn=_items_from_meta_for_job,
        ensure_tasks_fn=_ensure_tasks_for_job,
    )

    lease_cleaner = LeaseCleaner(
        store=store,
        interval=float(os.getenv("LEASE_CLEANUP_INTERVAL", "60")),
        max_reclaimed=int(os.getenv("LEASE_CLEANUP_MAX_RECLAIMED", "100")),
    )

    maintenance_cleaner = MaintenanceCleaner(
        store=store,
        interval=float(os.getenv("CLEANUP_INTERVAL", "86400")),
        stale_days=int(os.getenv("CLEANUP_STALE_DAYS", "1")),
        finished_days=int(os.getenv("CLEANUP_FINISHED_DAYS", "90")),
        batch_size=int(os.getenv("CLEANUP_BATCH_SIZE", "1000")),
    )

    f2a = FetchToAnalyzeOrchestrator(store, router)

    # Control de shutdown
    stop = {"flag": False}
    last_scan = 0.0

    def _sigterm(*_a):
        log.warning("shutdown_signal_received", signal="SIGTERM/SIGINT")
        stop["flag"] = True
        router.stop_accepting()

    signal.signal(signal.SIGINT, _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)

    log.info("dispatcher_ready", scan_interval_s=scan_every_s, accounts=accounts)

    # Loop principal
    try:
        while not stop["flag"]:
            now = time.time()

            # Escanear y cargar jobs pendientes
            if now - last_scan >= scan_every_s:
                last_scan = now
                job_scanner.scan_and_load()

            # Dispatch de tareas
            router.dispatch_tick()

            # Limpieza de leases expirados
            lease_cleaner.run(now)

            # Limpieza de mantenimiento
            maintenance_cleaner.run(now)

            # Procesar resultados
            result_queues = worker_manager.get_result_queues()
            for rq in result_queues.values():
                while True:
                    res = rq.try_get_nowait()
                    if res is None:
                        break
                    router.on_result(res)
                    f2a.on_result(res, all_tasks_finished_fn=lambda jid: store.all_tasks_finished(jid))

            time.sleep(tick_sleep)

        log.info("dispatcher_stopping")

    finally:
        worker_manager.stop_all()
        log.info("dispatcher_stopped")


if __name__ == "__main__":
    run()
