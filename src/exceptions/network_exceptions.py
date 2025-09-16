"""
Excepciones específicas para operaciones de red
"""
from typing import Optional, Dict, Any


class NetworkException(Exception):
    """Excepción base para errores de red"""
    
    def __init__(self, message: str, url: Optional[str] = None,
                 status_code: Optional[int] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.url = url
        self.status_code = status_code
        self.context = context or {}
    
    def __str__(self):
        base_msg = f"Network Error: {self.message}"
        if self.url:
            base_msg += f" | URL: {self.url}"
        if self.status_code:
            base_msg += f" | Status: {self.status_code}"
        return base_msg


class NetworkConnectionError(NetworkException):
    """Error de conexión de red"""
    
    def __init__(self, message: str, url: Optional[str] = None,
                 connection_type: Optional[str] = None, timeout: Optional[float] = None):
        super().__init__(message, url)
        self.connection_type = connection_type
        self.timeout = timeout
        self.context.update({
            'connection_type': connection_type,
            'timeout': timeout
        })
    
    def __str__(self):
        base_msg = f"Network Connection Error: {self.message}"
        if self.connection_type:
            base_msg += f" | Type: {self.connection_type}"
        if self.timeout:
            base_msg += f" | Timeout: {self.timeout}s"
        if self.url:
            base_msg += f" | URL: {self.url}"
        return base_msg


class NetworkTimeoutError(NetworkException):
    """Error de timeout de red"""
    
    def __init__(self, message: str, url: Optional[str] = None,
                 timeout: Optional[float] = None, operation: Optional[str] = None):
        super().__init__(message, url)
        self.timeout = timeout
        self.operation = operation
        self.context.update({
            'timeout': timeout,
            'operation': operation
        })
    
    def __str__(self):
        base_msg = f"Network Timeout Error: {self.message}"
        if self.operation:
            base_msg += f" | Operation: {self.operation}"
        if self.timeout:
            base_msg += f" | Timeout: {self.timeout}s"
        if self.url:
            base_msg += f" | URL: {self.url}"
        return base_msg


class ProxyError(NetworkException):
    """Error relacionado con proxy"""
    
    def __init__(self, message: str, proxy_url: Optional[str] = None,
                 proxy_type: Optional[str] = None, error_type: Optional[str] = None):
        super().__init__(message)
        self.proxy_url = proxy_url
        self.proxy_type = proxy_type
        self.error_type = error_type
        self.context.update({
            'proxy_url': proxy_url,
            'proxy_type': proxy_type,
            'error_type': error_type
        })
    
    def __str__(self):
        base_msg = f"Proxy Error: {self.message}"
        if self.proxy_type:
            base_msg += f" | Type: {self.proxy_type}"
        if self.error_type:
            base_msg += f" | Error: {self.error_type}"
        if self.proxy_url:
            base_msg += f" | URL: {self.proxy_url}"
        return base_msg


class InstagramAPIError(NetworkException):
    """Error específico de la API de Instagram"""
    
    def __init__(self, message: str, endpoint: Optional[str] = None,
                 status_code: Optional[int] = None, error_code: Optional[str] = None,
                 rate_limit_info: Optional[Dict[str, Any]] = None):
        super().__init__(message, endpoint, status_code)
        self.endpoint = endpoint
        self.error_code = error_code
        self.rate_limit_info = rate_limit_info or {}
        self.context.update({
            'endpoint': endpoint,
            'error_code': error_code,
            'rate_limit_info': rate_limit_info
        })
    
    def __str__(self):
        base_msg = f"Instagram API Error: {self.message}"
        if self.endpoint:
            base_msg += f" | Endpoint: {self.endpoint}"
        if self.status_code:
            base_msg += f" | Status: {self.status_code}"
        if self.error_code:
            base_msg += f" | Code: {self.error_code}"
        if self.rate_limit_info:
            base_msg += f" | Rate Limit: {self.rate_limit_info}"
        return base_msg
