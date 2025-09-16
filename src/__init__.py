# ScrapInsta4 - Instagram Scraping System
# Módulo principal del sistema

__version__ = "1.0.0"
__author__ = "ScrapInsta4 Team"

# Importaciones principales del sistema
try:
    from .core.worker.router import Router
    from .core.worker.instagram_worker import InstagramWorker
    from .db.pool_manager import pool_manager
    from .config.settings import INSTAGRAM_CONFIG, DATABASE_CONFIG
    
    __all__ = [
        'Router', 
        'InstagramWorker', 
        'pool_manager',
        'INSTAGRAM_CONFIG',
        'DATABASE_CONFIG'
    ]
except ImportError as e:
    # Si hay errores de importación, solo exportar la información básica
    __all__ = []
