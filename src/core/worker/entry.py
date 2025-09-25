from core.worker.instagram_worker import InstagramWorker
import signal

def worker_entry(idx, account, task_q, result_q, ready_q, stop_event):
    """
    Crea el worker DENTRO del proceso hijo y corre el loop principal.
    Evita picklear instancias/métodos bound creados en el padre.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    w = InstagramWorker(
        account=account,
        task_queue=task_q,
        result_queue=result_q,
        workers_ready=ready_q,
        stop_event=stop_event,  # <— NUEVO
    )
    w.run(idx)
