import os
import time
import logging
import queue
from datetime import datetime
# Ya no necesitamos get_db_connection directamente, usamos connection pooling
from config.settings import RETRY_CONFIG
from core.browser.driver_manager import DriverManager
from core.worker.task_handlers import (
    handle_analyze_profiles,
    handle_fetch_followings,
    handle_send_message
)
from core.auth.session_controller import initialize_session
from core.worker.messages import (
    TASK_ANALYZE,
    TASK_FETCH_FOLLOWINGS,
    TASK_SEND_MESSAGE,
    RES_ERROR
)

logger = logging.getLogger(__name__)


class InstagramSessionManager:
    def __init__(self, driver, account, last_check):
        self.driver = driver
        self.account = account
        self.last_check = last_check

    def refresh(self):
        success, self.last_check = initialize_session(
            self.driver, self.account, self.last_check
        )
        return success


class InstagramWorker:
    def __init__(self, account=None, task_queue=None, result_queue=None, workers_ready=None,
                 driver_manager=None):
        self.account = account or {}
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.workers_ready = workers_ready
        self.driver = None
        self.worker_id = None
        self.driver_manager = driver_manager or DriverManager(self.account)
        self.session_manager = None

    def _wrap_result(self, task, payload: dict) -> dict:
        payload.setdefault('task_id', task.get('id'))
        payload.setdefault('task_type', task.get('type'))
        payload.setdefault('timestamp', datetime.now().isoformat())
        payload.setdefault('worker_id', self.worker_id)
        return payload


    def initialize(self, announce_ready=True):
        logger.info(f"Entrando en initialize() (PID: {os.getpid()})")
        self._announce_ready = bool(announce_ready)
        for attempt in range(RETRY_CONFIG['max_retries']):
            if self._try_initialize(attempt):
                return True
        return False


    def _try_initialize(self, attempt):
        try:
            logger.info(f"Intento {attempt + 1} de {RETRY_CONFIG['max_retries']} para inicializar")
            self.driver_manager.cleanup()
            self.driver = self.driver_manager.initialize_driver()
            if not self.driver:
                raise Exception("No se pudo inicializar el driver")

            # Ya no necesitamos establecer conexión manual, usamos connection pooling

            self.session_manager = InstagramSessionManager(self.driver, self.account, None)
            if not self.session_manager.refresh():
                raise Exception("No se pudo iniciar sesión en Instagram")

            if self.workers_ready and self._announce_ready:
                self.workers_ready.put(True)

            return True

        except Exception as e:
            logger.error(f"Error en intento {attempt + 1}: {e}")
            self.driver_manager.cleanup()
            if attempt < RETRY_CONFIG['max_retries'] - 1:
                wait_time = RETRY_CONFIG['initial_delay'] * (attempt + 1)
                logger.info(f"Esperando {wait_time} segundos antes de reintentar...")
                time.sleep(wait_time)
            return False

    def process_task(self, task):
        try:
            task_type = task.get('type')
            logger.info(f"Procesando tarea tipo: {task_type}")
            if task_type == TASK_SEND_MESSAGE:
                res = handle_send_message(self.driver, task, self.session_manager.refresh)
            elif task_type == TASK_ANALYZE:
                has_session = bool(self.account and 'username' in self.account)
                reinit = lambda: self.initialize(announce_ready=False)
                res = handle_analyze_profiles(self.driver, task, reinit, self.session_manager.refresh, has_session)
            elif task_type == TASK_FETCH_FOLLOWINGS:
                reinit = lambda: self.initialize(announce_ready=False)
                res = handle_fetch_followings(self.driver, task, reinit, self.session_manager.refresh)
            else:
                raise ValueError(f"Tipo de tarea desconocido: {task_type}")
            return self._wrap_result(task, res)

        except Exception as e:
            logger.error(f"Error procesando tarea '{task.get('type')}': {e}")
            return self._wrap_result(task, {
                'type': RES_ERROR,
                'error': str(e),
            })


    def run(self, worker_id):
        self.worker_id = worker_id

        if not self.initialize():
            logger.error("No se pudo inicializar el worker")
            return

        logger.info(f"Worker {worker_id} iniciado y listo para procesar tareas")

        while True:
            try:
                task = self.task_queue.get(timeout=None)
                if task is None:
                    logger.info("Señal de terminación recibida")
                    break

                result = self.process_task(task)
                self.result_queue.put(result)

            except queue.Empty:
                continue
            except Exception as e:
                self.result_queue.put(self._wrap_result({'type': task.get('type') if task else None}, {
                'type': RES_ERROR,
                'error': str(e)
            }))


        self.driver_manager.cleanup()
        logger.info(f"Worker {worker_id} finalizado")
