from unittest.mock import MagicMock

from scrapinsta.application.dto.tasks import ResultEnvelope
from scrapinsta.interface.workers.router import Router, RouterConfig, Job


def test_router_requeues_retryable_result_and_restores_pending():
    store = MagicMock()
    store.requeue_task_with_attempts_cap.return_value = True
    store.all_tasks_finished.return_value = False

    router = Router(
        accounts=["acc1"],
        send_fn_by_account={"acc1": lambda _env: None},
        job_store=store,
        config=RouterConfig(max_inflight_per_account=1),
    )

    job_id = "job:1"
    username = "u1"
    task_id = f"{job_id}:fetch_followings:{username}"
    job = Job(job_id=job_id, kind="fetch_followings", items=[username], pending={username})
    router.add_job(job)

    # Simular que ya se despachó y está en vuelo (meta)
    router._task_meta[task_id] = {"account": "acc1", "username": username, "job_id": job_id, "start_time": router._now()}
    router._inflight["acc1"] = 1
    router._jobs[job_id].pending.discard(username)

    res = ResultEnvelope(
        ok=False,
        error="invalid session id: session deleted as the browser has closed the connection",
        attempts=1,
        task_id=task_id,
        correlation_id=job_id,
        result={"retryable": True, "retry_reason": "driver_dead", "max_attempts": 3},
    )

    router.on_result(res)

    store.requeue_task_with_attempts_cap.assert_called_once()
    store.mark_task_error.assert_not_called()
    assert username in router._jobs[job_id].pending


