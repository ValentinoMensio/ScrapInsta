import time
import logging
from logging.config import dictConfig
from queue import Empty
from multiprocessing import Process, Queue as MPQueue
from config.account_utils import load_accounts
from config.settings import INSTAGRAM_CONFIG, LOGGING_CONFIG
from db.connection import get_db_connection_context

from core.worker.instagram_worker import InstagramWorker
from core.worker.messages import (
    TASK_FETCH_FOLLOWINGS,
    TASK_ANALYZE,
    RES_FOLLOWINGS_FETCHED,
    RES_PROFILE_ANALYZED,
    RES_ERROR,
)
from core.worker.router import Router, Job

# Configurar logging
dictConfig(LOGGING_CONFIG)
logging.getLogger('seleniumwire').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)



def start_workers(accounts, worker_queues, result_queue, workers_ready):
    """Arranca un worker por cuenta. Devuelve lista de procesos."""
    processes = []
    for idx, account in enumerate(accounts, start=1):
        logger.info(f"Iniciando worker {idx} para cuenta {account['username']}")
        worker = InstagramWorker(
            account=account,
            task_queue=worker_queues[account['username'].strip().lower()],
            result_queue=result_queue,
            workers_ready=workers_ready
        )
        p = Process(target=worker.run, args=(idx,))
        p.start()
        processes.append(p)
        logger.info(f"Worker {idx} (PID: {p.pid}) iniciado")
    return processes


def wait_workers_ready(workers_ready, expected, timeout=600):
    """Espera a que todos los workers anuncien ready (una vez cada uno)."""
    ready = 0
    deadline = time.time() + timeout
    while ready < expected and time.time() < deadline:
        try:
            _ = workers_ready.get(timeout=1)
            ready += 1
            logger.info(f"Workers listos: {ready}/{expected}")
        except Empty:
            continue
    return ready == expected


def safe_db_read_followings(origin_username, limit):
    """Lee followings desde DB usando connection pooling."""
    try:
        with get_db_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username_target FROM followings WHERE username_origin = %s LIMIT %s",
                (origin_username, limit)
            )
            rows = cursor.fetchall()
            followings = [r[0] for r in rows] if rows else []
            if followings:
                logger.info(f"Se usaron {len(followings)} seguidores de la base de datos")
            return followings
    except Exception as e:
        logger.error(f"Error al leer base de datos para {origin_username}: {e}")
        return []


def shutdown(processes, worker_queues, timeout=10):
    """Apagado amable y, si hace falta, forzoso."""
    logger.info("Enviando señal de terminación a los workers…")
    for q in worker_queues.values():
        q.put(None)

    for p in processes:
        p.join(timeout)
    still_alive = [p for p in processes if p.is_alive()]

    if still_alive:
        logger.warning(f"Workers aún vivos tras {timeout}s: {[p.pid for p in still_alive]}. Terminando…")
        for p in still_alive:
            p.terminate()
        for p in still_alive:
            p.join(5)

    logger.info("Workers finalizados.")


def main():
    processes = []
    worker_queues = {}

    try:
        accounts = load_accounts()
        if not accounts:
            logger.error("No se encontraron cuentas en el archivo de configuración")
            return

        # Validar configuración crítica
        if not INSTAGRAM_CONFIG.get('target_profile'):
            logger.error("target_profile no configurado en INSTAGRAM_CONFIG")
            return
        
        if not isinstance(INSTAGRAM_CONFIG.get('max_followings'), int) or INSTAGRAM_CONFIG['max_followings'] <= 0:
            logger.error("max_followings debe ser un entero positivo")
            return

        logger.info(f"Iniciando {len(accounts)} workers...")
        # **Una cola por cuenta** (cada worker consume solo su cola; el Router reparte)
        worker_queues = {acc['username'].strip().lower(): MPQueue() for acc in accounts}
        result_queue = MPQueue()
        workers_ready = MPQueue()

        processes = start_workers(accounts, worker_queues, result_queue, workers_ready)
        if not wait_workers_ready(workers_ready, expected=len(accounts), timeout=600):
            logger.error("No todos los workers anunciaron readiness a tiempo")
            shutdown(processes, worker_queues)
            return

        # -------------------------------
        # Router + Jobs dinámicos
        # -------------------------------
        norm_accounts = []
        for a in accounts:
            a = dict(a)
            a['username'] = a['username'].strip().lower()
            norm_accounts.append(a)

        router = Router(norm_accounts, worker_queues)

        origin = INSTAGRAM_CONFIG['target_profile']
        max_followings = INSTAGRAM_CONFIG['max_followings']

        # Job 1: traer followings del perfil origen (un solo ítem)
        fetch_job_id = "fetch_followings"
        router.add_job(Job(
            job_id=fetch_job_id,
            kind="fetch_followings",
            items=[origin],
            batch_size=1,
            extra={"max_followings": max_followings}
        ))

        logger.info(f"[MAIN] Job creado: fetch_followings para origin={origin}")

        analyze_job_id = None  # lo creamos cuando recibimos followings
        analyze_created = False

        start_time = time.time()

        # Loop principal: despacha según tokens y procesa resultados
        while True:
            # 1) Intentar despachar lo que haya
            router.dispatch()

            # 2) Consumir resultados
            result = None
            try:
                result = result_queue.get(timeout=2)
                logger.info(f"[GOT RESULT] {result.get('type')} task_id={result.get('task_id')}")
            except Empty:
                result = None

            if result:
                # avisar al router para liberar inflights y marcar jobs
                router.on_result(result)

                rtype = result.get("type")

                if rtype == RES_FOLLOWINGS_FETCHED:
                    data = result.get("data") or {}
                    fetched_origin = data.get("origin")
                    followings = data.get("followings") or []
                    logger.info(f"FOLLOWINGS ({fetched_origin}): {len(followings)}")

                    # Si vino vacío, fallback a DB
                    if not followings:
                        logger.info("Followings vacíos desde worker; probando DB…")
                        followings = safe_db_read_followings(origin, max_followings)

                    # Crear job de análisis una sola vez cuando tengamos followings
                    if followings and not analyze_created:
                        # recortar a max_followings si vino más
                        if max_followings and len(followings) > max_followings:
                            followings = followings[:max_followings]

                        analyze_job_id = "analyze"
                        router.add_job(Job(
                            job_id=analyze_job_id,
                            kind="analyze",
                            items=followings,
                            batch_size=25  # ajustable
                        ))
                        analyze_created = True
                        logger.info(f"Job de análisis creado con {len(followings)} perfiles.")

                elif rtype == RES_PROFILE_ANALYZED:
                    # Podés actualizar métricas, loguear statuses, etc.
                    res = result.get('results') or []
                    if res:
                        u = (res[0] or {}).get('username')
                        st = (res[0] or {}).get('status')
                        logger.info(f"Analizado {u}: {st}")

                elif rtype == RES_ERROR:
                    logger.error(f"Error de worker: {result.get('error')}")

            # 3) Condición de salida:
            # - Si ya creamos el analyze job, esperamos a que el router declare todos los jobs done
            # - Si no hubo followings (ni worker ni DB), terminamos cuando el fetch job esté done
            all_done = router.all_done()
            if all_done:
                break

        # Resumen
        elapsed = int(time.time() - start_time)
        m, s = divmod(elapsed, 60)
        h, m = divmod(m, 60)
        tstr = f"{h} h {m} min {s} s" if h else (f"{m} min {s} s" if m else f"{s} s")
        logger.info(f"✅ Flujo finalizado en {tstr}")
        logger.info(f"Total de jobs procesados: {len(router.jobs)}")
        logger.info(f"Total de inflights: {sum(router.inflight.values())}")
        logger.info(f"Total de tareas despachadas: {sum(q.qsize() for q in worker_queues.values())}")
        logger.info(f"Total de resultados en cola: {result_queue.qsize()}")
        total_analyzed = sum(len(job.pending) for job in router.jobs.values() if job.kind == 'analyze')
        logger.info(f"Total de perfiles analizados: {total_analyzed}")
        total_with_rubro = sum(1 for job in router.jobs.values() if job.kind == 'analyze' and not job.done)
        logger.info(f"Total de perfiles con coincidencia de rubro: {total_with_rubro}") 

    except KeyboardInterrupt:
        logger.warning("Interrumpido por el usuario (Ctrl+C)")

    finally:
        try:
            if processes and worker_queues:
                shutdown(processes, worker_queues)
        except Exception as e:
            logger.error(f"Error durante el apagado: {e}")


if __name__ == "__main__":
    main()
