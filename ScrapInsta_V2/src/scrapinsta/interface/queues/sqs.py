from __future__ import annotations
import json
import os
import time
from typing import Optional, Callable

import boto3
from botocore.config import Config

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope
from .ports import TaskQueuePort, ResultQueuePort, AckFn, NackFn


def _json_dumps(o) -> str:
    return json.dumps(o, separators=(",", ":"), ensure_ascii=False)


def _json_loads(s: str):
    return json.loads(s)


class SqsTaskQueue(TaskQueuePort):
    """
    SQS FIFO adapter para tareas.
    - Usa un solo queue FIFO compartido.
    - MessageGroupId = account_id para preservar orden por cuenta.
    - DeduplicationId = task_id para idempotencia.
    """

    def __init__(
        self,
        *,
        queue_url: str,
        aws_region: Optional[str] = None,
        visibility_timeout_s: int = 120,
        long_poll_s: int = 20,
    ) -> None:
        self._queue_url = queue_url
        self._visibility = visibility_timeout_s
        self._wait = long_poll_s

        session = boto3.session.Session(region_name=aws_region or os.getenv("AWS_REGION") or "us-east-1")
        self._sqs = session.client("sqs", config=Config(retries={"max_attempts": 10, "mode": "adaptive"}))

    def send(self, env: TaskEnvelope) -> None:
        body = _json_dumps({
            "task": env.task,
            "payload": env.payload,
            "account_id": env.account_id,
            "id": env.id,
            "correlation_id": env.correlation_id,
        })
        # group por cuenta para ordenar
        group_id = env.account_id or "default"
        dedup_id = env.id or f"{env.task}:{int(time.time()*1000)}"

        self._sqs.send_message(
            QueueUrl=self._queue_url,
            MessageBody=body,
            MessageGroupId=group_id,
            MessageDeduplicationId=dedup_id,
        )

    def receive(self, timeout_s: float) -> Optional[tuple[TaskEnvelope, AckFn, NackFn]]:
        # Unificamos timeout con long polling. SQS permite 0..20s
        wait = min(self._wait, int(max(0.0, timeout_s)))
        resp = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait,
            VisibilityTimeout=self._visibility,
        )
        msgs = resp.get("Messages") or []
        if not msgs:
            return None

        msg = msgs[0]
        receipt = msg["ReceiptHandle"]
        try:
            payload = _json_loads(msg["Body"])
        except Exception:
            # Si hubo un mensaje corrupto, lo descartamos (ACK) para no bloquear.
            self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)
            return None

        env = TaskEnvelope(
            task=payload.get("task"),
            payload=payload.get("payload"),
            account_id=payload.get("account_id"),
            id=payload.get("id"),
            correlation_id=payload.get("correlation_id"),
        )

        def _ack() -> None:
            self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)

        def _nack() -> None:
            # No borramos; dejamos que expire visibility timeout.
            return None

        return (env, _ack, _nack)


class SqsResultQueue(ResultQueuePort):
    """
    SQS FIFO adapter para resultados.
    - Puedes agrupar por job_id para orden de resultados por job.
    """
    def __init__(self, *, queue_url: str, aws_region: Optional[str] = None) -> None:
        self._queue_url = queue_url
        session = boto3.session.Session(region_name=aws_region or os.getenv("AWS_REGION") or "us-east-1")
        self._sqs = session.client("sqs", config=Config(retries={"max_attempts": 10, "mode": "adaptive"}))

    def send(self, res: ResultEnvelope) -> None:
        body = _json_dumps({
            "ok": res.ok,
            "result": res.result,
            "error": res.error,
            "attempts": res.attempts,
            "task_id": res.task_id,
            "correlation_id": res.correlation_id,
        })
        group_id = res.correlation_id or "default"
        dedup_id = res.task_id or f"res:{int(time.time()*1000)}"

        self._sqs.send_message(
            QueueUrl=self._queue_url,
            MessageBody=body,
            MessageGroupId=group_id,
            MessageDeduplicationId=dedup_id,
        )

    def try_get_nowait(self) -> Optional[ResultEnvelope]:
        # SQS no tiene "nowait". Implementamos un poll con WaitTimeSeconds=0
        resp = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=0,
            VisibilityTimeout=10,
        )
        msgs = resp.get("Messages") or []
        if not msgs:
            return None

        msg = msgs[0]
        receipt = msg["ReceiptHandle"]
        try:
            payload = _json_loads(msg["Body"])
        except Exception:
            # Si corrupto, borrar para no ciclar
            self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)
            return None

        res = ResultEnvelope(
            ok=bool(payload.get("ok")),
            result=payload.get("result"),
            error=payload.get("error"),
            attempts=int(payload.get("attempts") or 1),
            task_id=payload.get("task_id"),
            correlation_id=payload.get("correlation_id"),
        )

        # Confirmamos consumo (ACK)
        self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)
        return res
