"""Middlewares para la aplicación FastAPI."""
from scrapinsta.interface.middleware.observability import ObservabilityMiddleware
from scrapinsta.interface.middleware.security import SecurityMiddleware
from scrapinsta.interface.middleware.request_limits import RequestSizeLimitMiddleware

__all__ = ["ObservabilityMiddleware", "SecurityMiddleware", "RequestSizeLimitMiddleware"]

