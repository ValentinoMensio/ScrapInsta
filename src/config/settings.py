"""
Configuración centralizada para la aplicación
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Configuración de Instagram
INSTAGRAM_CONFIG = {
    'target_profile': os.getenv('INSTAGRAM_TARGET_PROFILE', 'dra.natalipaz'),
    'max_followings': int(os.getenv('INSTAGRAM_MAX_FOLLOWINGS', '12')),
    'cookie_refresh_interval': int(os.getenv('INSTAGRAM_COOKIE_REFRESH_INTERVAL', '15')),  # minutos
}

BROWSER_CONFIG = {
    'user_agents': [
        # Chrome en Linux (solo Chromium-based)
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        # Edge en Linux (también Chromium, opcional)
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
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


# Configuración de API Keys
OPEN_AI_API_KEY = os.getenv('OPENAI_API_KEY')

# Configuración de Base de Datos
DATABASE_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'scrapinsta'),
    'password': os.getenv('MYSQL_PASSWORD', '4312'),
    'database': os.getenv('MYSQL_DATABASE', 'scrapinsta_db')
}

# Configuración del Pool de Conexiones
POOL_CONFIG = {
    'pool_name': 'scrapinsta_pool',
    'pool_size': int(os.getenv('MYSQL_POOL_SIZE', '10')),  # Número de conexiones en el pool
    'pool_reset_session': True,  # Resetear sesión al devolver conexión al pool
    'autocommit': True,  # Autocommit por defecto
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'time_zone': '+00:00',
    'sql_mode': 'TRADITIONAL',
    'raise_on_warnings': True,
    'use_unicode': True,
    'get_warnings': True,
    'connection_timeout': int(os.getenv('MYSQL_CONNECTION_TIMEOUT', '60'))  # Timeout de conexión
} 