from __future__ import annotations
import logging
from typing import Dict, List, Tuple

from scrapinsta.config.settings import Settings
from .ports import TaskQueuePort, ResultQueuePort
from .local_mp import LocalTaskQueue, LocalResultQueue
from .sqs import SqsTaskQueue, SqsResultQueue

logger = logging.getLogger(__name__)


def build_queues(
    *,
    settings: Settings,
    accounts: List[str],
) -> Tuple[Dict[str, TaskQueuePort], Dict[str, ResultQueuePort], str]:
    """
    Crea colas (task/result) por cuenta según el backend configurado.

    Devuelve:
        (task_queues_by_account, result_queues_by_account, backend_name)

    Backends soportados:
      - "local": multiprocessing.Queue (por proceso)
      - "sqs": AWS SQS FIFO (compartido entre procesos)
    """
    backend = (getattr(settings, "queues_backend", "local") or "local").strip().lower()

    if backend not in {"local", "sqs"}:
        logger.warning("[queues_factory] backend desconocido '%s' -> usando 'local'", backend)
        backend = "local"

    # ------------------------
    # LOCAL BACKEND
    # ------------------------
    if backend == "local":
        maxsize = getattr(settings, "queue_maxsize", 200)
        tqs: Dict[str, TaskQueuePort] = {}
        rqs: Dict[str, ResultQueuePort] = {}
        for acc in accounts:
            tqs[acc] = LocalTaskQueue(maxsize=maxsize)
            rqs[acc] = LocalResultQueue(maxsize=maxsize)
        logger.info("[queues_factory] usando backend LOCAL (multiprocessing.Queue)")
        return tqs, rqs, "local"

    # ------------------------
    # SQS BACKEND
    # ------------------------
    try:
        queue_url_tasks = getattr(settings, "sqs_task_queue_url", None)
        queue_url_results = getattr(settings, "sqs_result_queue_url", None)
        region = getattr(settings, "aws_region", None) or "us-east-1"

        if not queue_url_tasks or not queue_url_results:
            raise ValueError("Faltan URLs de colas SQS (SQS_TASK_QUEUE_URL, SQS_RESULT_QUEUE_URL)")

        shared_tq = SqsTaskQueue(queue_url=queue_url_tasks, aws_region=region)
        shared_rq = SqsResultQueue(queue_url=queue_url_results, aws_region=region)

        tqs = {acc: shared_tq for acc in accounts}
        rqs = {acc: shared_rq for acc in accounts}

        logger.info("[queues_factory] usando backend SQS | región=%s", region)
        return tqs, rqs, "sqs"

    except Exception as e:
        logger.error("[queues_factory] error inicializando SQS: %s -> fallback a LOCAL", e, exc_info=True)
        maxsize = getattr(settings, "queue_maxsize", 200)
        tqs: Dict[str, TaskQueuePort] = {}
        rqs: Dict[str, ResultQueuePort] = {}
        for acc in accounts:
            tqs[acc] = LocalTaskQueue(maxsize=maxsize)
            rqs[acc] = LocalResultQueue(maxsize=maxsize)
        return tqs, rqs, "local"
