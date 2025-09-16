"""
Excepciones específicas para lógica de negocio
"""
from typing import Optional, Dict, Any


class BusinessException(Exception):
    """Excepción base para errores de lógica de negocio"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}
    
    def __str__(self):
        return f"Business Error: {self.message}"


class ProfileNotFoundError(BusinessException):
    """Error cuando no se encuentra un perfil"""
    
    def __init__(self, message: str, username: Optional[str] = None,
                 search_context: Optional[str] = None):
        super().__init__(message)
        self.username = username
        self.search_context = search_context
        self.context.update({
            'username': username,
            'search_context': search_context
        })
    
    def __str__(self):
        base_msg = f"Profile Not Found: {self.message}"
        if self.username:
            base_msg += f" | Username: {self.username}"
        if self.search_context:
            base_msg += f" | Context: {self.search_context}"
        return base_msg


class ProfilePrivateError(BusinessException):
    """Error cuando un perfil es privado"""
    
    def __init__(self, message: str, username: Optional[str] = None,
                 access_attempted: Optional[str] = None):
        super().__init__(message)
        self.username = username
        self.access_attempted = access_attempted
        self.context.update({
            'username': username,
            'access_attempted': access_attempted
        })
    
    def __str__(self):
        base_msg = f"Profile Private: {self.message}"
        if self.username:
            base_msg += f" | Username: {self.username}"
        if self.access_attempted:
            base_msg += f" | Attempted: {self.access_attempted}"
        return base_msg


class ProfileBlockedError(BusinessException):
    """Error cuando se está bloqueado por un perfil"""
    
    def __init__(self, message: str, username: Optional[str] = None,
                 block_type: Optional[str] = None):
        super().__init__(message)
        self.username = username
        self.block_type = block_type
        self.context.update({
            'username': username,
            'block_type': block_type
        })
    
    def __str__(self):
        base_msg = f"Profile Blocked: {self.message}"
        if self.username:
            base_msg += f" | Username: {self.username}"
        if self.block_type:
            base_msg += f" | Type: {self.block_type}"
        return base_msg


class InstagramRateLimitError(BusinessException):
    """Error cuando se excede el límite de rate de Instagram"""
    
    def __init__(self, message: str, retry_after: Optional[int] = None,
                 action: Optional[str] = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.action = action
        self.context.update({
            'retry_after': retry_after,
            'action': action
        })
    
    def __str__(self):
        base_msg = f"Instagram Rate Limit: {self.message}"
        if self.action:
            base_msg += f" | Action: {self.action}"
        if self.retry_after:
            base_msg += f" | Retry After: {self.retry_after}s"
        return base_msg


class InstagramLoginError(BusinessException):
    """Error en el proceso de login de Instagram"""
    
    def __init__(self, message: str, username: Optional[str] = None,
                 login_step: Optional[str] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.username = username
        self.login_step = login_step
        self.error_code = error_code
        self.context.update({
            'username': username,
            'login_step': login_step,
            'error_code': error_code
        })
    
    def __str__(self):
        base_msg = f"Instagram Login Error: {self.message}"
        if self.username:
            base_msg += f" | Username: {self.username}"
        if self.login_step:
            base_msg += f" | Step: {self.login_step}"
        if self.error_code:
            base_msg += f" | Code: {self.error_code}"
        return base_msg


class TaskProcessingError(BusinessException):
    """Error en el procesamiento de tareas"""
    
    def __init__(self, message: str, task_id: Optional[str] = None,
                 task_type: Optional[str] = None, worker_id: Optional[int] = None,
                 retry_count: Optional[int] = None):
        super().__init__(message)
        self.task_id = task_id
        self.task_type = task_type
        self.worker_id = worker_id
        self.retry_count = retry_count
        self.context.update({
            'task_id': task_id,
            'task_type': task_type,
            'worker_id': worker_id,
            'retry_count': retry_count
        })
    
    def __str__(self):
        base_msg = f"Task Processing Error: {self.message}"
        if self.task_id:
            base_msg += f" | Task ID: {self.task_id}"
        if self.task_type:
            base_msg += f" | Type: {self.task_type}"
        if self.worker_id:
            base_msg += f" | Worker: {self.worker_id}"
        if self.retry_count is not None:
            base_msg += f" | Retries: {self.retry_count}"
        return base_msg


class WorkerError(BusinessException):
    """Error en workers"""
    
    def __init__(self, message: str, worker_id: Optional[int] = None,
                 worker_status: Optional[str] = None, current_task: Optional[str] = None):
        super().__init__(message)
        self.worker_id = worker_id
        self.worker_status = worker_status
        self.current_task = current_task
        self.context.update({
            'worker_id': worker_id,
            'worker_status': worker_status,
            'current_task': current_task
        })
    
    def __str__(self):
        base_msg = f"Worker Error: {self.message}"
        if self.worker_id:
            base_msg += f" | Worker ID: {self.worker_id}"
        if self.worker_status:
            base_msg += f" | Status: {self.worker_status}"
        if self.current_task:
            base_msg += f" | Task: {self.current_task}"
        return base_msg
