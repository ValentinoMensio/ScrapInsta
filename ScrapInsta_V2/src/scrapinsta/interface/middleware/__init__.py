"""Middlewares para la aplicación FastAPI."""
from scrapinsta.interface.middleware.observability import ObservabilityMiddleware
from scrapinsta.interface.middleware.security import SecurityMiddleware

__all__ = ["ObservabilityMiddleware", "SecurityMiddleware"]

