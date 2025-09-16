"""
Excepciones personalizadas para ScrapInsta4
"""
from .database_exceptions import (
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseTransactionError,
    DatabasePoolError,
    DatabaseValidationError
)
from .selenium_exceptions import (
    SeleniumDriverError,
    SeleniumTimeoutError,
    SeleniumElementNotFoundError,
    SeleniumNavigationError,
    SeleniumSessionError
)
from .validation_exceptions import (
    ValidationError,
    ProfileValidationError,
    TaskValidationError,
    FollowingValidationError,
    ConfigurationValidationError
)
from .business_exceptions import (
    ProfileNotFoundError,
    ProfilePrivateError,
    ProfileBlockedError,
    InstagramRateLimitError,
    InstagramLoginError,
    TaskProcessingError,
    WorkerError
)
from .network_exceptions import (
    NetworkConnectionError,
    NetworkTimeoutError,
    ProxyError,
    InstagramAPIError
)

__all__ = [
    # Database exceptions
    'DatabaseConnectionError',
    'DatabaseQueryError', 
    'DatabaseTransactionError',
    'DatabasePoolError',
    'DatabaseValidationError',
    
    # Selenium exceptions
    'SeleniumDriverError',
    'SeleniumTimeoutError',
    'SeleniumElementNotFoundError',
    'SeleniumNavigationError',
    'SeleniumSessionError',
    
    # Validation exceptions
    'ValidationError',
    'ProfileValidationError',
    'TaskValidationError',
    'FollowingValidationError',
    'ConfigurationValidationError',
    
    # Business exceptions
    'ProfileNotFoundError',
    'ProfilePrivateError',
    'ProfileBlockedError',
    'InstagramRateLimitError',
    'InstagramLoginError',
    'TaskProcessingError',
    'WorkerError',
    
    # Network exceptions
    'NetworkConnectionError',
    'NetworkTimeoutError',
    'ProxyError',
    'InstagramAPIError'
]
