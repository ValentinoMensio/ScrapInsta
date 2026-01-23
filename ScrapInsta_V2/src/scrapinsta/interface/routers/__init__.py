"""Routers para la aplicación FastAPI."""
from scrapinsta.interface.routers.auth_router import router as auth_router
from scrapinsta.interface.routers.send_router import router as send_router
from scrapinsta.interface.routers.external_router import router as external_router
from scrapinsta.interface.routers.health_router import router as health_router

__all__ = ["auth_router", "send_router", "external_router", "health_router"]

