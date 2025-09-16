"""
Excepciones específicas para operaciones de Selenium
"""
from typing import Optional, Dict, Any


class SeleniumException(Exception):
    """Excepción base para errores de Selenium"""
    
    def __init__(self, message: str, url: Optional[str] = None, 
                 element_info: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.url = url
        self.element_info = element_info or {}
    
    def __str__(self):
        base_msg = f"Selenium Error: {self.message}"
        if self.url:
            base_msg += f" | URL: {self.url}"
        return base_msg


class SeleniumDriverError(SeleniumException):
    """Error en el driver de Selenium"""
    
    def __init__(self, message: str, driver_type: Optional[str] = None,
                 driver_version: Optional[str] = None):
        super().__init__(message)
        self.driver_type = driver_type
        self.driver_version = driver_version
        self.element_info.update({
            'driver_type': driver_type,
            'driver_version': driver_version
        })
    
    def __str__(self):
        base_msg = f"Selenium Driver Error: {self.message}"
        if self.driver_type:
            base_msg += f" | Driver: {self.driver_type}"
        if self.driver_version:
            base_msg += f" v{self.driver_version}"
        return base_msg


class SeleniumTimeoutError(SeleniumException):
    """Error de timeout en operaciones de Selenium"""
    
    def __init__(self, message: str, timeout: Optional[float] = None,
                 operation: Optional[str] = None, url: Optional[str] = None):
        super().__init__(message, url)
        self.timeout = timeout
        self.operation = operation
        self.element_info.update({
            'timeout': timeout,
            'operation': operation
        })
    
    def __str__(self):
        base_msg = f"Selenium Timeout Error: {self.message}"
        if self.operation:
            base_msg += f" | Operation: {self.operation}"
        if self.timeout:
            base_msg += f" | Timeout: {self.timeout}s"
        if self.url:
            base_msg += f" | URL: {self.url}"
        return base_msg


class SeleniumElementNotFoundError(SeleniumException):
    """Error cuando no se encuentra un elemento"""
    
    def __init__(self, message: str, selector: Optional[str] = None,
                 selector_type: Optional[str] = None, url: Optional[str] = None):
        super().__init__(message, url)
        self.selector = selector
        self.selector_type = selector_type
        self.element_info.update({
            'selector': selector,
            'selector_type': selector_type
        })
    
    def __str__(self):
        base_msg = f"Selenium Element Not Found: {self.message}"
        if self.selector_type and self.selector:
            base_msg += f" | {self.selector_type}: {self.selector}"
        if self.url:
            base_msg += f" | URL: {self.url}"
        return base_msg


class SeleniumNavigationError(SeleniumException):
    """Error en navegación de páginas"""
    
    def __init__(self, message: str, from_url: Optional[str] = None,
                 to_url: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message, to_url)
        self.from_url = from_url
        self.to_url = to_url
        self.status_code = status_code
        self.element_info.update({
            'from_url': from_url,
            'to_url': to_url,
            'status_code': status_code
        })
    
    def __str__(self):
        base_msg = f"Selenium Navigation Error: {self.message}"
        if self.from_url and self.to_url:
            base_msg += f" | {self.from_url} → {self.to_url}"
        elif self.to_url:
            base_msg += f" | URL: {self.to_url}"
        if self.status_code:
            base_msg += f" | Status: {self.status_code}"
        return base_msg


class SeleniumSessionError(SeleniumException):
    """Error de sesión de Selenium"""
    
    def __init__(self, message: str, session_id: Optional[str] = None,
                 is_logged_in: Optional[bool] = None, url: Optional[str] = None):
        super().__init__(message, url)
        self.session_id = session_id
        self.is_logged_in = is_logged_in
        self.element_info.update({
            'session_id': session_id,
            'is_logged_in': is_logged_in
        })
    
    def __str__(self):
        base_msg = f"Selenium Session Error: {self.message}"
        if self.session_id:
            base_msg += f" | Session: {self.session_id[:8]}..."
        if self.is_logged_in is not None:
            base_msg += f" | Logged In: {self.is_logged_in}"
        if self.url:
            base_msg += f" | URL: {self.url}"
        return base_msg
