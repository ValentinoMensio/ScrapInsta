"""
Esquemas de validación para datos de perfiles de Instagram
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime


class ProfileData(BaseModel):
    """Esquema base para datos de perfil de Instagram"""
    username: str = Field(..., min_length=1, max_length=30, pattern=r'^[a-zA-Z0-9._]+$')
    bio: Optional[str] = Field(None, max_length=150)
    followers: int = Field(..., ge=0)
    following: int = Field(..., ge=0)
    posts: int = Field(..., ge=0)
    avg_likes: float = Field(..., ge=0.0)
    avg_comments: float = Field(..., ge=0.0)
    avg_views: float = Field(..., ge=0.0)
    is_private: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    engagement_score: float = Field(..., ge=0.0, le=1.0)
    success_score: float = Field(..., ge=0.0, le=1.0)
    rubro: str = Field(..., min_length=1, max_length=100)
    
    @validator('username')
    def validate_username(cls, v):
        """Validar formato de username de Instagram"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username no puede estar vacío')
        return v.strip().lower()
    
    @validator('bio')
    def validate_bio(cls, v):
        """Validar bio de Instagram"""
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    @validator('rubro')
    def validate_rubro(cls, v):
        """Validar rubro"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Rubro no puede estar vacío')
        return v.strip().title()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"  # No permitir campos adicionales


class ProfileCreate(ProfileData):
    """Esquema para crear un nuevo perfil"""
    pass


class ProfileUpdate(BaseModel):
    """Esquema para actualizar un perfil existente"""
    bio: Optional[str] = Field(None, max_length=150)
    followers: Optional[int] = Field(None, ge=0)
    following: Optional[int] = Field(None, ge=0)
    posts: Optional[int] = Field(None, ge=0)
    avg_likes: Optional[float] = Field(None, ge=0.0)
    avg_comments: Optional[float] = Field(None, ge=0.0)
    avg_views: Optional[float] = Field(None, ge=0.0)
    is_private: Optional[bool] = None
    is_verified: Optional[bool] = None
    engagement_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    success_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    rubro: Optional[str] = Field(None, min_length=1, max_length=100)
    
    @validator('bio')
    def validate_bio(cls, v):
        """Validar bio de Instagram"""
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
    @validator('rubro')
    def validate_rubro(cls, v):
        """Validar rubro"""
        if v is not None and len(v.strip()) > 0:
            return v.strip().title()
        return v
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class ProfileAnalysisResult(BaseModel):
    """Esquema para resultado de análisis de perfil"""
    username: str = Field(..., min_length=1, max_length=30)
    status: Literal['success', 'error', 'no_match', 'private', 'no_rubro', 'no_stats', 'no_reel_data', 'no_evaluation', 'db_error'] = Field(...)
    reason: Optional[str] = Field(None, max_length=200)
    data: Optional[ProfileData] = None
    error: Optional[str] = Field(None, max_length=500)
    
    @validator('username')
    def validate_username(cls, v):
        """Validar formato de username"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username no puede estar vacío')
        return v.strip().lower()
    
    @validator('reason')
    def validate_reason(cls, v):
        """Validar razón del resultado"""
        if v is not None:
            return v.strip() if v.strip() else None
        return v
    
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


class ProfileEvaluation(BaseModel):
    """Esquema para evaluación de perfil"""
    username: str = Field(..., min_length=1, max_length=30)
    engagement_score: float = Field(..., ge=0.0, le=1.0)
    success_score: float = Field(..., ge=0.0, le=1.0)
    
    @validator('username')
    def validate_username(cls, v):
        """Validar formato de username"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username no puede estar vacío')
        return v.strip().lower()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"
