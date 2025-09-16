"""
Esquemas de validación para tareas del sistema
"""
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime


class TaskData(BaseModel):
    """Esquema base para tareas del sistema"""
    id: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    profile: str = Field(..., min_length=1, max_length=30)
    timestamp: Optional[datetime] = None
    worker_id: Optional[int] = Field(None, ge=1)
    
    @validator('id')
    def validate_id(cls, v):
        """Validar ID de tarea"""
        if not v or len(v.strip()) == 0:
            raise ValueError('ID de tarea no puede estar vacío')
        return v.strip()
    
    @validator('type')
    def validate_type(cls, v):
        """Validar tipo de tarea"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Tipo de tarea no puede estar vacío')
        return v.strip().lower()
    
    @validator('profile')
    def validate_profile(cls, v):
        """Validar username del perfil"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Perfil no puede estar vacío')
        return v.strip().lower()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class AnalyzeTask(TaskData):
    """Esquema para tarea de análisis de perfil"""
    type: Literal['analyze'] = 'analyze'
    max_profiles: Optional[int] = Field(None, ge=1, le=1000)
    has_session: Optional[bool] = True
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class FetchFollowingsTask(TaskData):
    """Esquema para tarea de obtención de followings"""
    type: Literal['fetch_followings'] = 'fetch_followings'
    max_followings: Optional[int] = Field(None, ge=1, le=10000)
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class SendMessageTask(TaskData):
    """Esquema para tarea de envío de mensaje"""
    type: Literal['send_message'] = 'send_message'
    message: Optional[str] = Field(None, max_length=1000)
    max_retries: Optional[int] = Field(3, ge=1, le=10)
    
    @validator('message')
    def validate_message(cls, v):
        """Validar mensaje"""
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class TaskResult(BaseModel):
    """Esquema para resultado de tarea"""
    task_id: str = Field(..., min_length=1, max_length=100)
    task_type: str = Field(..., min_length=1, max_length=50)
    timestamp: datetime = Field(default_factory=datetime.now)
    worker_id: Optional[int] = Field(None, ge=1)
    type: str = Field(..., min_length=1, max_length=50)
    success: bool = Field(...)
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = Field(None, max_length=1000)
    results: Optional[List[Dict[str, Any]]] = None
    
    @validator('task_id')
    def validate_task_id(cls, v):
        """Validar ID de tarea"""
        if not v or len(v.strip()) == 0:
            raise ValueError('ID de tarea no puede estar vacío')
        return v.strip()
    
    @validator('task_type')
    def validate_task_type(cls, v):
        """Validar tipo de tarea"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Tipo de tarea no puede estar vacío')
        return v.strip().lower()
    
    @validator('type')
    def validate_type(cls, v):
        """Validar tipo de resultado"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Tipo de resultado no puede estar vacío')
        return v.strip().lower()
    
    @validator('error')
    def validate_error(cls, v):
        """Validar mensaje de error"""
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class WorkerStatus(BaseModel):
    """Esquema para estado de worker"""
    worker_id: int = Field(..., ge=1)
    status: Literal['initializing', 'ready', 'busy', 'error', 'stopped'] = Field(...)
    current_task: Optional[str] = Field(None, max_length=100)
    tasks_processed: int = Field(0, ge=0)
    errors_count: int = Field(0, ge=0)
    last_activity: Optional[datetime] = None
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class PoolStatus(BaseModel):
    """Esquema para estado del pool de conexiones"""
    status: Literal['active', 'not_initialized', 'error'] = Field(...)
    pool_name: Optional[str] = Field(None, max_length=100)
    pool_size: Optional[int] = Field(None, ge=1)
    available_connections: Optional[int] = Field(None, ge=0)
    used_connections: Optional[int] = Field(None, ge=0)
    error: Optional[str] = Field(None, max_length=500)
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"
