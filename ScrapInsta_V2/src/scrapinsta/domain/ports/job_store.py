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
        client_id: str,
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
        client_id: str,
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

    def get_job_client_id(self, job_id: str) -> Optional[str]:
        """
        Obtiene el client_id de un job.
        
        Args:
            job_id: ID del job
            
        Returns:
            client_id del job o None si no existe
        """
        ...
    
    def job_exists(self, job_id: str) -> bool:
        """
        Verifica si un job existe en la base de datos.
        
        Args:
            job_id: ID del job a verificar
            
        Returns:
            True si el job existe, False en caso contrario
        """
        ...

    def pending_jobs(self) -> List[str]:
        """
        Obtiene la lista de job IDs pendientes.
        
        Returns:
            Lista de IDs de jobs en estado 'pending'
        """
        ...

    def list_jobs_by_client(
        self, client_id: str, limit: int = 5, kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista los últimos jobs del cliente, más recientes primero.
        
        Args:
            client_id: ID del cliente
            limit: Número máximo de jobs a devolver
            kind: Si se especifica, filtrar por tipo (ej: 'fetch_followings')
        
        Returns:
            Lista de dicts con id, kind, status, created_at
        """
        ...

    def job_summary(self, job_id: str, client_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene un resumen de un job.
        
        Args:
            job_id: ID del job
            client_id: ID del cliente para validar ownership (opcional)
        
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

    def has_active_send_task(
        self,
        client_username: str,
        dest_username: str,
        client_id: Optional[str] = None,
    ) -> bool:
        """True si ya existe una task send_message queued/sent para ese destino."""
        ...

    def count_messages_sent_today(self, client_id: str) -> int:
        """Cuenta mensajes enviados hoy por client_id."""
        ...

    def count_tasks_sent_today(self, client_id: str) -> int:
        """Cuenta tareas en estado 'sent' hoy por client_id (en vuelo)."""
        ...

    def register_message_sent(
        self,
        client_username: str,
        dest_username: str,
        job_id: Optional[str] = None,
        task_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> None:
        """
        Registra envío de mensaje en el ledger.
        
        Args:
            client_username: Username de la cuenta cliente que envió
            dest_username: Username del destino
            job_id: ID del job (opcional)
            task_id: ID de la tarea (opcional)
            client_id: ID del cliente (opcional, se obtiene del job si no se provee)
        """
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

    def cleanup_stale_tasks(self, older_than_days: int = 1, batch_size: int = 1000) -> int:
        """
        Elimina tasks 'queued' antiguas para mantener limpia la tabla.
        
        Args:
            older_than_days: Días de antigüedad
            batch_size: Tamaño del lote para procesamiento
            
        Returns:
            Total de tareas eliminadas
        """
        ...
    
    def cleanup_finished_tasks(self, older_than_days: int = 90, batch_size: int = 1000) -> int:
        """
        Elimina tasks 'ok'/'error' muy viejas para limitar el tamaño de la tabla.
        
        Args:
            older_than_days: Días de antigüedad
            batch_size: Tamaño del lote para procesamiento
            
        Returns:
            Total de tareas eliminadas
        """
        ...
    
    def cleanup_orphaned_jobs(self, older_than_days: int = 7) -> int:
        """
        Elimina jobs que no tienen tareas asociadas (huérfanos).
        
        Args:
            older_than_days: Días de antigüedad mínima
            
        Returns:
            Número de jobs eliminados
        """
        ...

    def reclaim_expired_leases(self, max_reclaimed: int = 100) -> int:
        """
        Reencola tareas con leases expirados.
        
        Busca tareas en estado 'sent' con leased_at expirado (según lease_ttl)
        y las reencola a 'queued' para que puedan ser procesadas nuevamente.
        
        Args:
            max_reclaimed: Número máximo de tareas a reencolar por ejecución
            
        Returns:
            Número de tareas reencoladas
        """
        ...

    def get_job_metadata(self, job_id: str) -> Dict[str, Any]:
        """
        Obtiene los metadatos de un job (kind, priority, batch_size, extra_json).
        
        Args:
            job_id: ID del job
            
        Returns:
            Diccionario con metadatos del job:
            - kind: Tipo de job
            - priority: Prioridad
            - batch_size: Tamaño de lote
            - extra: Metadatos adicionales (dict parseado desde JSON)
            
        Raises:
            RuntimeError: Si el job no existe
        """
        ...

    def get_followings_for_owner(self, owner: str, limit: int = 500) -> List[str]:
        """
        Obtiene la lista de followings para un owner específico.
        
        Args:
            owner: Username del owner
            limit: Límite de resultados
            
        Returns:
            Lista de usernames que el owner sigue
        """
        ...
