"""
Esquemas de validación de datos para ScrapInsta4
"""
from .profile_schemas import (
    ProfileData,
    ProfileCreate,
    ProfileUpdate,
    ProfileAnalysisResult
)
from .task_schemas import (
    TaskData,
    AnalyzeTask,
    FetchFollowingsTask,
    SendMessageTask,
    TaskResult
)
from .database_schemas import (
    FollowingData,
    FollowingCreate
)

__all__ = [
    # Profile schemas
    'ProfileData',
    'ProfileCreate', 
    'ProfileUpdate',
    'ProfileAnalysisResult',
    
    # Task schemas
    'TaskData',
    'AnalyzeTask',
    'FetchFollowingsTask',
    'SendMessageTask',
    'TaskResult',
    
    # Database schemas
    'FollowingData',
    'FollowingCreate'
]
