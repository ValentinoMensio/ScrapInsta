"""
Excepciones específicas para validación de datos
"""
from typing import Optional, Dict, Any, List
from pydantic import ValidationError as PydanticValidationError


class ValidationException(Exception):
    """Excepción base para errores de validación"""
    
    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[Any] = None, errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.value = value
        self.errors = errors or []
    
    def __str__(self):
        base_msg = f"Validation Error: {self.message}"
        if self.field:
            base_msg += f" | Field: {self.field}"
        if self.value is not None:
            base_msg += f" | Value: {self.value}"
        return base_msg


class ValidationError(ValidationException):
    """Error general de validación"""
    
    def __init__(self, message: str, pydantic_error: Optional[PydanticValidationError] = None):
        super().__init__(message)
        self.pydantic_error = pydantic_error
        if pydantic_error:
            self.errors = pydantic_error.errors()
    
    def __str__(self):
        base_msg = f"Validation Error: {self.message}"
        if self.errors:
            base_msg += f" | {len(self.errors)} validation errors"
        return base_msg


class ProfileValidationError(ValidationException):
    """Error de validación específico para perfiles"""
    
    def __init__(self, message: str, username: Optional[str] = None,
                 field: Optional[str] = None, value: Optional[Any] = None):
        super().__init__(message, field, value)
        self.username = username
    
    def __str__(self):
        base_msg = f"Profile Validation Error: {self.message}"
        if self.username:
            base_msg += f" | Username: {self.username}"
        if self.field:
            base_msg += f" | Field: {self.field}"
        if self.value is not None:
            base_msg += f" | Value: {self.value}"
        return base_msg


class TaskValidationError(ValidationException):
    """Error de validación específico para tareas"""
    
    def __init__(self, message: str, task_id: Optional[str] = None,
                 task_type: Optional[str] = None, field: Optional[str] = None,
                 value: Optional[Any] = None):
        super().__init__(message, field, value)
        self.task_id = task_id
        self.task_type = task_type
    
    def __str__(self):
        base_msg = f"Task Validation Error: {self.message}"
        if self.task_id:
            base_msg += f" | Task ID: {self.task_id}"
        if self.task_type:
            base_msg += f" | Type: {self.task_type}"
        if self.field:
            base_msg += f" | Field: {self.field}"
        if self.value is not None:
            base_msg += f" | Value: {self.value}"
        return base_msg


class FollowingValidationError(ValidationException):
    """Error de validación específico para followings"""
    
    def __init__(self, message: str, username_origin: Optional[str] = None,
                 username_target: Optional[str] = None, field: Optional[str] = None,
                 value: Optional[Any] = None):
        super().__init__(message, field, value)
        self.username_origin = username_origin
        self.username_target = username_target
    
    def __str__(self):
        base_msg = f"Following Validation Error: {self.message}"
        if self.username_origin:
            base_msg += f" | Origin: {self.username_origin}"
        if self.username_target:
            base_msg += f" | Target: {self.username_target}"
        if self.field:
            base_msg += f" | Field: {self.field}"
        if self.value is not None:
            base_msg += f" | Value: {self.value}"
        return base_msg


class ConfigurationValidationError(ValidationException):
    """Error de validación específico para configuración"""
    
    def __init__(self, message: str, config_key: Optional[str] = None,
                 config_value: Optional[Any] = None, config_file: Optional[str] = None):
        super().__init__(message, config_key, config_value)
        self.config_key = config_key
        self.config_value = config_value
        self.config_file = config_file
    
    def __str__(self):
        base_msg = f"Configuration Validation Error: {self.message}"
        if self.config_key:
            base_msg += f" | Key: {self.config_key}"
        if self.config_value is not None:
            base_msg += f" | Value: {self.config_value}"
        if self.config_file:
            base_msg += f" | File: {self.config_file}"
        return base_msg
