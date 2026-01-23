"""
Factory para crear la aplicación FastAPI.

Proporciona una función create_app() que permite inyectar dependencias,
facilitando testing y configuración dinámica.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI

from scrapinsta.interface.dependencies import Dependencies, get_dependencies
from scrapinsta.crosscutting.logging_config import (
    configure_structured_logging,
    get_logger,
)

logger = get_logger("app_factory")


def create_app(
    dependencies: Optional[Dependencies] = None,
    *,
    title: str = "ScrapInsta Send API",
    version: str = "0.1.0",
) -> FastAPI:
    """
    Crea y configura la aplicación FastAPI.
    
    Args:
        dependencies: Contenedor de dependencias (se crea si no se provee)
        title: Título de la aplicación
        version: Versión de la aplicación
        
    Returns:
        Aplicación FastAPI configurada
    """
    # Importar middlewares desde módulo dedicado
    from scrapinsta.interface.middleware import (
        ObservabilityMiddleware,
        SecurityMiddleware,
    )
    
    # Configurar logging si no está configurado
    if not logger.handlers:
        configure_structured_logging(
            level=os.getenv("LOG_LEVEL", "INFO"),
            json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
        )
    
    # Usar dependencias provistas o crear nuevas
    if dependencies is None:
        dependencies = get_dependencies()
    
    # Crear app FastAPI
    app = FastAPI(title=title, version=version)
    
    # Almacenar dependencias en el estado de la app para acceso en endpoints
    app.state.dependencies = dependencies
    
    logger.info(
        "app_created",
        title=title,
        version=version,
        db_dsn=dependencies.settings.db_dsn,
    )
    
    # Configurar middlewares
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(SecurityMiddleware)
    
    # Configurar CORS (importar función desde api)
    from scrapinsta.interface.api import _setup_app
    _setup_app(app, dependencies)
    
    # Registrar routers
    from scrapinsta.interface.routers import (
        auth_router,
        send_router,
        external_router,
        health_router,
    )
    app.include_router(auth_router)
    app.include_router(send_router)
    app.include_router(external_router)
    app.include_router(health_router)
    
    logger.info("routers_registered", message="Routers registrados exitosamente")
    
    return app

