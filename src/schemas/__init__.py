"""
Esquemas de validación de datos para ScrapInsta4
"""
from .profile_schemas import (
    ProfileData,
    ProfileCreate,
    ProfileUpdate,
    ProfileAnalysisResult,
    ProfileEvaluation
)
from .task_schemas import (
    TaskData,
    AnalyzeTask,
    FetchFollowingsTask,
    SendMessageTask,
    TaskResult,
    WorkerStatus,
    PoolStatus
)
from .database_schemas import (
    FollowingData,
    FollowingCreate,
    FollowingList,
    DatabaseConfig,
    PoolConfig
)

__all__ = [
    # Profile schemas
    'ProfileData',
    'ProfileCreate', 
    'ProfileUpdate',
    'ProfileAnalysisResult',
    'ProfileEvaluation',
    
    # Task schemas
    'TaskData',
    'AnalyzeTask',
    'FetchFollowingsTask',
    'SendMessageTask',
    'TaskResult',
    'WorkerStatus',
    'PoolStatus',
    
    # Database schemas
    'FollowingData',
    'FollowingCreate',
    'FollowingList',
    'DatabaseConfig',
    'PoolConfig'
]
