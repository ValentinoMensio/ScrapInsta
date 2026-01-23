"""Servicios para el dispatcher - Separación de responsabilidades."""
from __future__ import annotations

import multiprocessing as mp
import time
from typing import Dict, List, Set, Callable, Any, Optional

from scrapinsta.config.settings import Settings
from scrapinsta.infrastructure.db.job_store_sql import JobStoreSQL
from scrapinsta.interface.workers.router import Router, Job
from scrapinsta.interface.queues import TaskQueuePort, ResultQueuePort
from scrapinsta.application.dto.tasks import ResultEnvelope
from scrapinsta.crosscutting.logging_config import get_logger
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

log = get_logger("dispatcher.services")


class WorkerManager:
    """Gestiona los procesos de workers."""
    
    def __init__(
        self,
        accounts: List[str],
        task_qs: Dict[str, TaskQueuePort],
        result_qs: Dict[str, ResultQueuePort],
        settings: Settings,
        start_worker_fn: Callable,
    ) -> None:
        """
        Inicializa el manager de workers.
        
        Args:
            accounts: Lista de cuentas
            task_qs: Diccionario de colas de tareas por cuenta
            result_qs: Diccionario de colas de resultados por cuenta
            settings: Configuración de la aplicación
            start_worker_fn: Función para iniciar un worker
        """
        self._accounts = accounts
        self._task_qs = task_qs
        self._result_qs = result_qs
        self._settings = settings
        self._start_worker_fn = start_worker_fn
        self._stop_events: Dict[str, mp.Event] = {}
        self._processes: Dict[str, mp.Process] = {}
    
    def start_all(self) -> None:
        """Inicia todos los workers."""
        for acc in self._accounts:
            sev = mp.Event()
            self._stop_events[acc] = sev
            proc = self._start_worker_fn(
                acc,
                self._task_qs[acc],
                self._result_qs[acc],
                sev,
                self._settings,
            )
            self._processes[acc] = proc
            workers_active.labels(account=acc).inc()
            log.info("worker_started", account=acc, pid=proc.pid)
    
    def stop_all(self, timeout: float = 10.0) -> None:
        """Detiene todos los workers."""
        for ev in self._stop_events.values():
            ev.set()
        
        for acc, p in self._processes.items():
            p.join(timeout=timeout)
            if p.is_alive():
                log.warning("worker_force_terminate", account=acc, pid=p.pid)
                p.terminate()
            workers_active.labels(account=acc).dec()
    
    def get_send_functions(self) -> Dict[str, Callable]:
        """Obtiene las funciones de envío por cuenta."""
        return {acc: self._task_qs[acc].send for acc in self._accounts}
    
    def get_result_queues(self) -> Dict[str, ResultQueuePort]:
        """Obtiene las colas de resultados por cuenta."""
        return self._result_qs


class JobScanner:
    """Escanea y carga jobs pendientes desde la base de datos."""
    
    def __init__(
        self,
        store: JobStoreSQL,
        router: Router,
        load_job_meta_fn: Callable,
        items_from_meta_fn: Callable,
        ensure_tasks_fn: Callable,
    ) -> None:
        """
        Inicializa el scanner de jobs.
        
        Args:
            store: Almacén de jobs
            router: Router para agregar jobs
            load_job_meta_fn: Función para cargar metadata de un job
            items_from_meta_fn: Función para extraer items de metadata
            ensure_tasks_fn: Función para asegurar que las tareas existen
        """
        self._store = store
        self._router = router
        self._load_job_meta = load_job_meta_fn
        self._items_from_meta = items_from_meta_fn
        self._ensure_tasks = ensure_tasks_fn
        self._loaded_jobs: Set[str] = set()
    
    def scan_and_load(self) -> None:
        """Escanea jobs pendientes y los carga en el router."""
        try:
            job_ids = self._store.pending_jobs()
        except Exception as e:
            log.warning("pending_jobs_failed", error=str(e))
            return
        
        for jid in job_ids:
            if jid in self._loaded_jobs:
                continue
            
            try:
                self._load_job(jid)
            except Exception as e:
                if "duplicado" in str(e).lower() or "duplicate" in str(e).lower():
                    self._loaded_jobs.add(jid)
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
    
    def _load_job(self, jid: str) -> None:
        """Carga un job específico en el router."""
        meta = self._load_job_meta(self._store, jid)
        kind = meta["kind"]
        prio = meta["priority"] if meta["priority"] > 0 else 5
        batch = meta["batch_size"] if meta["batch_size"] > 0 else 1
        extra = meta["extra"]
        
        if kind == "fetch_followings":
            items = self._items_from_meta(jid, meta, store=self._store)
        elif kind == "analyze_profile":
            items = self._items_from_meta(jid, meta, store=self._store)
        else:
            log.info(
                "job_kind_not_supported",
                job_id=jid,
                kind=kind,
                message="Job kind no soportado por dispatcher",
            )
            self._loaded_jobs.add(jid)
            return
        
        job = Job(
            job_id=jid,
            kind=kind,
            items=items,
            batch_size=batch,
            priority=prio,
            extra=extra,
            pending=self._store.list_queued_usernames(jid),
        )
        
        try:
            # Evitar doble expansión Job→Tasks entre 2 dispatchers:
            lock_name = f"scrapinsta:expand:{jid}"
            got_lock = self._store.try_advisory_lock(lock_name, timeout_s=0)
            if got_lock:
                try:
                    self._ensure_tasks(
                        self._store,
                        jid,
                        kind,
                        items,
                        extra if isinstance(extra, dict) else None,
                    )
                    self._store.mark_job_running(jid)
                finally:
                    try:
                        self._store.release_advisory_lock(lock_name)
                    except Exception:
                        pass
            
            job.pending = self._store.list_queued_usernames(jid)
            self._router.add_job(job)
            jobs_active.labels(status="running").inc()
            log.info(
                "job_loaded",
                job_id=jid,
                kind=kind,
                items_count=len(items),
            )
        finally:
            self._loaded_jobs.add(jid)


class LeaseCleaner:
    """Limpia leases expirados de tareas."""
    
    def __init__(
        self,
        store: JobStoreSQL,
        interval: float = 60.0,
        max_reclaimed: int = 100,
    ) -> None:
        """
        Inicializa el limpiador de leases.
        
        Args:
            store: Almacén de jobs
            interval: Intervalo en segundos entre limpiezas
            max_reclaimed: Máximo de leases a recuperar por ejecución
        """
        self._store = store
        self._interval = interval
        self._max_reclaimed = max_reclaimed
        self._last_cleanup = 0.0
    
    def should_run(self, now: float) -> bool:
        """Verifica si debe ejecutarse la limpieza."""
        return now - self._last_cleanup >= self._interval
    
    def run(self, now: float) -> None:
        """Ejecuta la limpieza de leases expirados."""
        if not self.should_run(now):
            return
        
        try:
            cleanup_start = time.time()
            reclaimed = self._store.reclaim_expired_leases(max_reclaimed=self._max_reclaimed)
            cleanup_duration = time.time() - cleanup_start
            
            if reclaimed > 0:
                log.info(
                    "leases_reclaimed",
                    count=reclaimed,
                    max_reclaimed=self._max_reclaimed,
                )
            
            lease_cleanup_reclaimed_total.inc(reclaimed)
            lease_cleanup_duration_seconds.observe(cleanup_duration)
        except Exception as e:
            log.warning("lease_cleanup_error", error=str(e))
        finally:
            self._last_cleanup = now


class MaintenanceCleaner:
    """Limpia tareas y jobs antiguos (mantenimiento)."""
    
    def __init__(
        self,
        store: JobStoreSQL,
        interval: float = 86400.0,  # Default: 24 horas
        stale_days: int = 1,
        finished_days: int = 90,
        batch_size: int = 1000,
    ) -> None:
        """
        Inicializa el limpiador de mantenimiento.
        
        Args:
            store: Almacén de jobs
            interval: Intervalo en segundos entre limpiezas
            stale_days: Días para considerar tareas como "stale"
            finished_days: Días para considerar tareas como "finished" (listas para eliminar)
            batch_size: Tamaño del lote para operaciones de limpieza
        """
        self._store = store
        self._interval = interval
        self._stale_days = stale_days
        self._finished_days = finished_days
        self._batch_size = batch_size
        self._last_cleanup = 0.0
    
    def should_run(self, now: float) -> bool:
        """Verifica si debe ejecutarse la limpieza."""
        return now - self._last_cleanup >= self._interval
    
    def run(self, now: float) -> None:
        """Ejecuta la limpieza de mantenimiento."""
        if not self.should_run(now):
            return
        
        try:
            cleanup_start = time.time()
            
            # Limpiar tareas stale
            stale_start = time.time()
            removed_stale = self._store.cleanup_stale_tasks(
                older_than_days=self._stale_days,
                batch_size=self._batch_size,
            )
            stale_duration = time.time() - stale_start
            if removed_stale:
                log.info(
                    "cleanup_stale_tasks",
                    removed_count=removed_stale,
                    older_than_days=self._stale_days,
                )
                cleanup_operations_total.labels(operation_type="stale_tasks").inc()
                cleanup_rows_deleted_total.labels(operation_type="stale_tasks", table="job_tasks").inc(removed_stale)
                cleanup_duration_seconds.labels(operation_type="stale_tasks").observe(stale_duration)
                cleanup_last_run_timestamp.labels(operation_type="stale_tasks").set(now)
            
            # Limpiar tareas finished
            finished_start = time.time()
            removed_finished = self._store.cleanup_finished_tasks(
                older_than_days=self._finished_days,
                batch_size=self._batch_size,
            )
            finished_duration = time.time() - finished_start
            if removed_finished:
                log.info(
                    "cleanup_finished_tasks",
                    removed_count=removed_finished,
                    older_than_days=self._finished_days,
                )
                cleanup_operations_total.labels(operation_type="finished_tasks").inc()
                cleanup_rows_deleted_total.labels(operation_type="finished_tasks", table="job_tasks").inc(removed_finished)
                cleanup_duration_seconds.labels(operation_type="finished_tasks").observe(finished_duration)
                cleanup_last_run_timestamp.labels(operation_type="finished_tasks").set(now)
            
            # Limpiar jobs huérfanos
            orphaned_start = time.time()
            removed_orphaned = self._store.cleanup_orphaned_jobs(older_than_days=7)
            orphaned_duration = time.time() - orphaned_start
            if removed_orphaned:
                log.info(
                    "cleanup_orphaned_jobs",
                    removed_count=removed_orphaned,
                )
                cleanup_operations_total.labels(operation_type="orphaned_jobs").inc()
                cleanup_rows_deleted_total.labels(operation_type="orphaned_jobs", table="jobs").inc(removed_orphaned)
                cleanup_duration_seconds.labels(operation_type="orphaned_jobs").observe(orphaned_duration)
                cleanup_last_run_timestamp.labels(operation_type="orphaned_jobs").set(now)
            
            cleanup_duration = time.time() - cleanup_start
            total_removed = removed_stale + removed_finished + removed_orphaned
            if total_removed:
                log.info(
                    "cleanup_completed",
                    total_removed=total_removed,
                    duration_ms=round(cleanup_duration * 1000, 2),
                )
        except Exception as e:
            log.warning("cleanup_error", error=str(e))
        finally:
            self._last_cleanup = now

