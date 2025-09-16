"""
Excepciones específicas para operaciones de base de datos
"""
from typing import Optional, Dict, Any


class DatabaseException(Exception):
    """Excepción base para errores de base de datos"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, 
                 query: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.query = query
        self.context = context or {}
    
    def __str__(self):
        base_msg = f"Database Error: {self.message}"
        if self.error_code:
            base_msg += f" (Code: {self.error_code})"
        if self.query:
            base_msg += f" | Query: {self.query[:100]}..."
        return base_msg


class DatabaseConnectionError(DatabaseException):
    """Error de conexión a la base de datos"""
    
    def __init__(self, message: str, host: Optional[str] = None, 
                 port: Optional[int] = None, database: Optional[str] = None):
        super().__init__(message)
        self.host = host
        self.port = port
        self.database = database
        self.context.update({
            'host': host,
            'port': port,
            'database': database
        })
    
    def __str__(self):
        base_msg = f"Database Connection Error: {self.message}"
        if self.host:
            base_msg += f" | Host: {self.host}"
        if self.port:
            base_msg += f":{self.port}"
        if self.database:
            base_msg += f" | Database: {self.database}"
        return base_msg


class DatabaseQueryError(DatabaseException):
    """Error en la ejecución de consultas SQL"""
    
    def __init__(self, message: str, query: str, error_code: Optional[str] = None,
                 affected_rows: Optional[int] = None):
        super().__init__(message, error_code, query)
        self.affected_rows = affected_rows
        self.context.update({
            'affected_rows': affected_rows
        })
    
    def __str__(self):
        base_msg = f"Database Query Error: {self.message}"
        if self.error_code:
            base_msg += f" (Code: {self.error_code})"
        if self.affected_rows is not None:
            base_msg += f" | Affected Rows: {self.affected_rows}"
        return base_msg


class DatabaseTransactionError(DatabaseException):
    """Error en transacciones de base de datos"""
    
    def __init__(self, message: str, operation: Optional[str] = None,
                 rollback_required: bool = True):
        super().__init__(message)
        self.operation = operation
        self.rollback_required = rollback_required
        self.context.update({
            'operation': operation,
            'rollback_required': rollback_required
        })
    
    def __str__(self):
        base_msg = f"Database Transaction Error: {self.message}"
        if self.operation:
            base_msg += f" | Operation: {self.operation}"
        if self.rollback_required:
            base_msg += " | Rollback Required"
        return base_msg


class DatabasePoolError(DatabaseException):
    """Error en el pool de conexiones"""
    
    def __init__(self, message: str, pool_name: Optional[str] = None,
                 pool_size: Optional[int] = None, available_connections: Optional[int] = None):
        super().__init__(message)
        self.pool_name = pool_name
        self.pool_size = pool_size
        self.available_connections = available_connections
        self.context.update({
            'pool_name': pool_name,
            'pool_size': pool_size,
            'available_connections': available_connections
        })
    
    def __str__(self):
        base_msg = f"Database Pool Error: {self.message}"
        if self.pool_name:
            base_msg += f" | Pool: {self.pool_name}"
        if self.pool_size is not None:
            base_msg += f" | Size: {self.pool_size}"
        if self.available_connections is not None:
            base_msg += f" | Available: {self.available_connections}"
        return base_msg


class DatabaseValidationError(DatabaseException):
    """Error de validación de datos para base de datos"""
    
    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[Any] = None, constraint: Optional[str] = None):
        super().__init__(message)
        self.field = field
        self.value = value
        self.constraint = constraint
        self.context.update({
            'field': field,
            'value': str(value) if value is not None else None,
            'constraint': constraint
        })
    
    def __str__(self):
        base_msg = f"Database Validation Error: {self.message}"
        if self.field:
            base_msg += f" | Field: {self.field}"
        if self.value is not None:
            base_msg += f" | Value: {self.value}"
        if self.constraint:
            base_msg += f" | Constraint: {self.constraint}"
        return base_msg
