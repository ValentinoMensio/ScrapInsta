"""Dispatcher package - servicios para gestión de workers y jobs."""
from __future__ import annotations

# Re-exportar la función run() desde el módulo principal
# para mantener compatibilidad con imports existentes
from scrapinsta.interface.dispatcher_main import run

__all__ = ["run"]

