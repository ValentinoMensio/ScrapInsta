"""
Esquemas de validación para datos de base de datos
"""
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime


class FollowingData(BaseModel):
    """Esquema para datos de following"""
    id: Optional[int] = Field(None, ge=1)
    username_origin: str = Field(..., min_length=1, max_length=30)
    username_target: str = Field(..., min_length=1, max_length=30)
    timestamp: Optional[datetime] = None
    
    @validator('username_origin')
    def validate_username_origin(cls, v):
        """Validar username de origen"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username de origen no puede estar vacío')
        return v.strip().lower()
    
    @validator('username_target')
    def validate_username_target(cls, v):
        """Validar username de destino"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username de destino no puede estar vacío')
        return v.strip().lower()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class FollowingCreate(BaseModel):
    """Esquema para crear following"""
    username_origin: str = Field(..., min_length=1, max_length=30)
    username_target: str = Field(..., min_length=1, max_length=30)
    
    @validator('username_origin')
    def validate_username_origin(cls, v):
        """Validar username de origen"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username de origen no puede estar vacío')
        return v.strip().lower()
    
    @validator('username_target')
    def validate_username_target(cls, v):
        """Validar username de destino"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username de destino no puede estar vacío')
        return v.strip().lower()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class FollowingList(BaseModel):
    """Esquema para lista de followings"""
    username_origin: str = Field(..., min_length=1, max_length=30)
    followings: List[str] = Field(..., min_items=0, max_items=10000)
    
    @validator('username_origin')
    def validate_username_origin(cls, v):
        """Validar username de origen"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Username de origen no puede estar vacío')
        return v.strip().lower()
    
    @validator('followings')
    def validate_followings(cls, v):
        """Validar lista de followings"""
        if v is None:
            return []
        
        validated_followings = []
        for username in v:
            if username is not None and isinstance(username, str) and len(username.strip()) > 0:
                validated_followings.append(username.strip().lower())
        
        return validated_followings
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class DatabaseConfig(BaseModel):
    """Esquema para configuración de base de datos"""
    host: str = Field(..., min_length=1, max_length=255)
    user: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=255)
    database: str = Field(..., min_length=1, max_length=64)
    port: Optional[int] = Field(3306, ge=1, le=65535)
    charset: Optional[str] = Field('utf8mb4', max_length=20)
    
    @validator('host')
    def validate_host(cls, v):
        """Validar host de base de datos"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Host no puede estar vacío')
        return v.strip()
    
    @validator('user')
    def validate_user(cls, v):
        """Validar usuario de base de datos"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Usuario no puede estar vacío')
        return v.strip()
    
    @validator('password')
    def validate_password(cls, v):
        """Validar contraseña de base de datos"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Contraseña no puede estar vacía')
        return v.strip()
    
    @validator('database')
    def validate_database(cls, v):
        """Validar nombre de base de datos"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Nombre de base de datos no puede estar vacío')
        return v.strip()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"


class PoolConfig(BaseModel):
    """Esquema para configuración del pool de conexiones"""
    pool_name: str = Field(..., min_length=1, max_length=100)
    pool_size: int = Field(..., ge=1, le=100)
    pool_reset_session: bool = Field(True)
    autocommit: bool = Field(True)
    charset: str = Field('utf8mb4', max_length=20)
    collation: str = Field('utf8mb4_unicode_ci', max_length=50)
    time_zone: str = Field('+00:00', max_length=10)
    sql_mode: str = Field('TRADITIONAL', max_length=50)
    raise_on_warnings: bool = Field(True)
    use_unicode: bool = Field(True)
    get_warnings: bool = Field(True)
    connection_timeout: int = Field(60, ge=1, le=3600)
    
    @validator('pool_name')
    def validate_pool_name(cls, v):
        """Validar nombre del pool"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Nombre del pool no puede estar vacío')
        return v.strip()
    
    @validator('charset')
    def validate_charset(cls, v):
        """Validar charset"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Charset no puede estar vacío')
        return v.strip().lower()
    
    @validator('collation')
    def validate_collation(cls, v):
        """Validar collation"""
        if not v or len(v.strip()) == 0:
            raise ValueError('Collation no puede estar vacío')
        return v.strip().lower()
    
    class Config:
        """Configuración del modelo"""
        validate_assignment = True
        use_enum_values = True
        extra = "forbid"
