# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any, Dict, List, Optional


@runtime_checkable
class JobStorePort(Protocol):
    """
    Puerto de persistencia de Jobs y Tasks.
    
    Define el contrato para almacenamiento de trabajos y tareas
    asociadas en el sistema de procesamiento.
    """

    def create_job(
        self,
        job_id: str,
        kind: str,
        priority: int,
        batch_size: int,
        extra: Optional[Dict[str, Any]],
        total_items: int,
    ) -> None:
        """
        Crea un nuevo job con los parámetros especificados.
        
        Args:
            job_id: Identificador único del job
            kind: Tipo de job (ej: 'analyze_profile', 'send_message')
            priority: Prioridad del job (mayor = más importante)
            batch_size: Tamaño del lote de procesamiento
            extra: Metadatos adicionales en formato JSON
            total_items: Número total de items a procesar
        """
        ...

    def mark_job_running(self, job_id: str) -> None:
        """Marca un job como en ejecución."""
        ...

    def mark_job_done(self, job_id: str) -> None:
        """Marca un job como completado exitosamente."""
        ...

    def mark_job_error(self, job_id: str) -> None:
        """Marca un job como fallido/error."""
        ...

    def add_task(
        self,
        job_id: str,
        task_id: str,
        correlation_id: Optional[str],
        account_id: Optional[str],
        username: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> None:
        """
        Añade una tarea a un job existente.
        
        Args:
            job_id: ID del job padre
            task_id: Identificador único de la tarea
            correlation_id: ID para correlación/cross-reference
            account_id: ID de la cuenta que procesará la tarea
            username: Username objetivo de la tarea
            payload: Datos específicos de la tarea (ej: profile snapshot)
        """
        ...

    def mark_task_sent(self, job_id: str, task_id: str) -> None:
        """Marca una tarea como enviada al worker."""
        ...

    def mark_task_ok(self, job_id: str, task_id: str, result: Optional[Dict[str, Any]]) -> None:
        """
        Marca una tarea como completada exitosamente.
        
        Args:
            job_id: ID del job padre
            task_id: ID de la tarea
            result: Resultado de la tarea (opcional)
        """
        ...

    def mark_task_error(self, job_id: str, task_id: str, error: str) -> None:
        """
        Marca una tarea como fallida.
        
        Args:
            job_id: ID del job padre
            task_id: ID de la tarea
            error: Mensaje de error descriptivo
        """
        ...

    def all_tasks_finished(self, job_id: str) -> bool:
        """
        Verifica si todas las tareas de un job están completadas.
        
        Returns:
            True si todas las tareas están en estado 'ok' o 'error'
        """
        ...

    def pending_jobs(self) -> List[str]:
        """
        Obtiene la lista de job IDs pendientes.
        
        Returns:
            Lista de IDs de jobs en estado 'pending'
        """
        ...

    def job_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Obtiene un resumen de un job.
        
        Args:
            job_id: ID del job
        
        Returns:
            Dict con información del job (status, counts, etc.)
        """
        ...

    def lease_tasks(self, account_id: str, limit: int) -> List[Dict[str, Any]]:
        """
        Obtiene hasta `limit` tareas pendientes para la cuenta dada.
        Las marca atómicamente como 'sent' y devuelve su payload.
        
        Args:
            account_id: ID de la cuenta del worker
            limit: Número máximo de tareas a obtener
        
        Returns:
            Lista de dicts con payload y metadatos de las tareas
        """
        ...

    # -----------------------
    # Ledger de mensajes enviados
    # -----------------------
    def was_message_sent(self, client_username: str, dest_username: str) -> bool:
        """Retorna True si ya se envió un mensaje (ledger) para (cliente, destino)."""
        ...

    def was_message_sent_any(self, dest_username: str) -> bool:
        """Retorna True si cualquier cliente ya envió un mensaje al destino."""
        ...

    def release_task(self, job_id: str, task_id: str, error: Optional[str]) -> None:
        """
        Libera o marca error en una tarea leaseada.
        Usado cuando el worker falla al procesar la tarea.
        
        Args:
            job_id: ID del job padre
            task_id: ID de la tarea
            error: Mensaje de error si hubo fallo, None si solo se libera
        """
        ...
