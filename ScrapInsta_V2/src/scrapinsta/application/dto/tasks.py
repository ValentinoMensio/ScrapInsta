from __future__ import annotations

from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field

TaskName = Literal[
    "analyze_profile",
    "send_message",
    "fetch_followings",
]

class TaskEnvelope(BaseModel):
    """
    Sobre de tarea genérico para routers/workers.
    - task: nombre lógico (mapea a un use case)
    - payload: dict con los campos del DTO del use case
    - account_id: opcional, para seleccionar el worker/adapters por cuenta
    - id/correlation_id: trazabilidad
    """
    task: TaskName
    payload: Dict[str, Any] = Field(default_factory=dict)
    account_id: Optional[str] = None
    id: Optional[str] = None
    correlation_id: Optional[str] = None

class ResultEnvelope(BaseModel):
    """
    Resultado estandarizado que devuelve el worker.
    - ok: True si el use case terminó sin excepciones
    - result: respuesta del use case (DTO de respuesta) si aplica
    - error: string breve si falló
    - attempts: cuántos reintentos ejecutó internamente el use case/adapter
    """
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    attempts: int = 1
    task_id: Optional[str] = None
    correlation_id: Optional[str] = None
