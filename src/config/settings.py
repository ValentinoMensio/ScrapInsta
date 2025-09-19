'''
Configuración centralizada para la aplicación
'''
import os
from dotenv import load_dotenv, find_dotenv

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(find_dotenv())

def _get_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f'Variable {name} no configurada en .env')
    return v

def _get_int(name: str, default: int | None = None) -> int:
    v = os.getenv(name)
    if v is None:
        if default is not None:
            return default
        raise RuntimeError(f'Variable {name} no configurada en .env')
    try:
        return int(v)
    except ValueError:
        raise RuntimeError(f'{name} debe ser entero. Recibido: {v!r}')

def get_openai_api_key():
    v = os.getenv("OPENAI_API_KEY")
    if not v:
        raise RuntimeError("OPENAI_API_KEY no configurado")
    return v

OPENAI_API_KEY = get_openai_api_key()

# Configuración de Instagram
INSTAGRAM_CONFIG = {
    'target_profile': _get_required('INSTAGRAM_TARGET_PROFILE'),
    'max_followings': _get_int('INSTAGRAM_MAX_FOLLOWINGS', 12),
    'cookie_refresh_interval': _get_int('INSTAGRAM_COOKIE_REFRESH_INTERVAL', 15),
}

BROWSER_CONFIG = {
    'user_agents': [
        # Chrome en Linux (solo Chromium-based)
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        # Edge en Linux (también Chromium, opcional)
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0'
    ],
    'chrome_version': 137,
    'timeouts': {
        'page_load': 90,
        'script': 30,
        'implicit': 2,   # <= clave
        'explicit': 20
    }
}

# Configuración de reintentos
RETRY_CONFIG = {
    'max_retries': 3,
    'initial_delay': 10,
    'max_delay': 30
}

# Configuración de puertos
PORT_CONFIG = {
    'max_port_attempts': 20
}

# Configuración de logging
LOGGING_CONFIG = {
    'version': 1,  # ¡En minúsculas!
    'disable_existing_loggers': False,  # Opcional pero recomendado
    'formatters': {
        'standard': {  # Nombre del formatter (puedes cambiarlo)
            'format': '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',  # Clave correcta: 'datefmt' (no 'date_format')
        },
    },
    'handlers': {
        'console': {  # Handler para mostrar logs en consola
            'class': 'logging.StreamHandler',
            'formatter': 'standard',  # Usa el formatter definido arriba
            'level': 'INFO',  # Nivel mínimo para este handler
        },
    },
    'loggers': {
        'seleniumwire': {  # Silencia Selenium Wire
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
        },
        # Agrega otros loggers específicos si es necesario
    },
    'root': {  # Configuración global (para todos los loggers no especificados)
        'level': 'INFO',  # Nivel mínimo global
        'handlers': ['console'],
    },
}

# Configuración de Base de Datos
DATABASE_CONFIG = {
    "host": _get_required("MYSQL_HOST"),
    "user": _get_required("MYSQL_USER"),
    "password": _get_required("MYSQL_PASSWORD"),
    "database": _get_required("MYSQL_DATABASE"),
    "port": _get_int("MYSQL_PORT", 3306),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "sql_mode": "TRADITIONAL",
    "connection_timeout": _get_int("MYSQL_CONNECTION_TIMEOUT", 60),
}

# Configuración del Pool de Conexiones
POOL_CONFIG = {
    "pool_name": "scrapinsta_pool",
    "pool_size": _get_int("MYSQL_POOL_SIZE", 10),
    "pool_reset_session": True,
    "autocommit": True
}