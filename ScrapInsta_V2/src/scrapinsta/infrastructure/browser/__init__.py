"""
Core del módulo de browser:
contiene utilidades comunes, creación/configuración del driver y su ciclo de vida.
"""

from .core.browser_utils import (
    detect_chrome_major,
    parse_proxy,
    quick_probe,
    safe_quit,
    safe_username,
)
from .core.driver_factory import build_chrome_options
from .core.driver_provider import DriverProvider, DriverManagerError

__all__ = [
    # browser_utils
    "detect_chrome_major",
    "parse_proxy",
    "quick_probe",
    "safe_quit",
    "safe_username",
    # driver_factory
    "build_chrome_options",
    # driver_provider
    "DriverProvider",
    "DriverManagerError",
]
