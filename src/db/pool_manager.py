"""
Pool Manager para MySQL Connection Pooling
"""
import logging
import threading
from contextlib import contextmanager
from typing import Dict, Any
import mysql.connector
from mysql.connector import pooling, Error
from config.settings import DATABASE_CONFIG, POOL_CONFIG
from utils.exception_handlers import log_exception_details
from exceptions.database_exceptions import (
    DatabaseConnectionError, DatabasePoolError
)

logger = logging.getLogger(__name__)


class PoolManager:
    """
    Gestor del pool de conexiones MySQL con patrón Singleton
    """
    _instance = None
    _lock = threading.Lock()
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PoolManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._pool = None
            self._initialize_pool()
    
    def _initialize_pool(self):
        """Inicializa el pool de conexiones"""
        try:
            # Combinar configuración de base de datos con configuración del pool
            pool_config = {**DATABASE_CONFIG, **POOL_CONFIG}
            
            # Crear el pool de conexiones
            self._pool = pooling.MySQLConnectionPool(**pool_config)
            
            logger.info(f"Pool de conexiones inicializado: {POOL_CONFIG['pool_name']} "
                       f"(tamaño: {POOL_CONFIG['pool_size']})")
            
        except Error as e:
            error_msg = f"Error inicializando pool de conexiones: {e}"
            logger.error(error_msg)
            
            # Convertir a excepción personalizada
            if e.errno == 2003:  # Can't connect to MySQL server
                raise DatabaseConnectionError(
                    f"No se puede conectar al servidor MySQL: {e.msg}",
                    host=DATABASE_CONFIG.get('host'),
                    port=DATABASE_CONFIG.get('port', 3306),
                    database=DATABASE_CONFIG.get('database')
                )
            elif e.errno == 1045:  # Access denied
                raise DatabaseConnectionError(
                    f"Acceso denegado a la base de datos: {e.msg}",
                    host=DATABASE_CONFIG.get('host'),
                    database=DATABASE_CONFIG.get('database')
                )
            else:
                raise DatabasePoolError(
                    f"Error inicializando pool: {e.msg}",
                    pool_name=POOL_CONFIG.get('pool_name'),
                    pool_size=POOL_CONFIG.get('pool_size'),
                    error_code=str(e.errno)
                )
        except Exception as e:
            error_msg = f"Error inesperado inicializando pool: {e}"
            logger.error(error_msg)
            log_exception_details(e, {'pool_config': pool_config})
            raise DatabasePoolError(
                f"Error inesperado inicializando pool: {str(e)}",
                pool_name=POOL_CONFIG.get('pool_name'),
                pool_size=POOL_CONFIG.get('pool_size')
            )
    
    def get_connection(self) -> mysql.connector.connection.MySQLConnection:
        """
        Obtiene una conexión del pool
        
        Returns:
            MySQLConnection: Conexión del pool
            
        Raises:
            DatabasePoolError: Si no se puede obtener conexión del pool
        """
        if self._pool is None:
            raise DatabasePoolError(
                "Pool de conexiones no inicializado",
                pool_name=POOL_CONFIG.get('pool_name')
            )
        
        try:
            connection = self._pool.get_connection()
            logger.debug("Conexión obtenida del pool")
            return connection
        except Error as e:
            error_msg = f"Error obteniendo conexión del pool: {e}"
            logger.error(error_msg)
            
            # Convertir a excepción personalizada
            if e.errno == 2003:  # Can't connect to MySQL server
                raise DatabaseConnectionError(
                    f"No se puede conectar al servidor MySQL: {e.msg}",
                    host=DATABASE_CONFIG.get('host'),
                    database=DATABASE_CONFIG.get('database')
                )
            else:
                raise DatabasePoolError(
                    f"Error obteniendo conexión del pool: {e.msg}",
                    pool_name=POOL_CONFIG.get('pool_name'),
                    pool_size=POOL_CONFIG.get('pool_size'),
                    error_code=str(e.errno)
                )
        except Exception as e:
            error_msg = f"Error inesperado obteniendo conexión: {e}"
            logger.error(error_msg)
            log_exception_details(e)
            raise DatabasePoolError(
                f"Error inesperado obteniendo conexión: {str(e)}",
                pool_name=POOL_CONFIG.get('pool_name')
            )
    
    def return_connection(self, connection: mysql.connector.connection.MySQLConnection):
        """
        Devuelve una conexión al pool
        
        Args:
            connection: Conexión a devolver al pool
        """
        if connection and connection.is_connected():
            try:
                connection.close()
                logger.debug("Conexión devuelta al pool")
            except Error as e:
                logger.warning(f"Error devolviendo conexión al pool: {e}")
        else:
            logger.warning("Intento de devolver conexión no válida al pool")
    
    @contextmanager
    def get_connection_context(self):
        """
        Context manager para obtener y devolver automáticamente una conexión
        
        Usage:
            with pool_manager.get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
                result = cursor.fetchall()
        """
        connection = None
        try:
            connection = self.get_connection()
            yield connection
        except Exception as e:
            logger.error(f"Error en contexto de conexión: {e}")
            raise
        finally:
            if connection:
                self.return_connection(connection)
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        Obtiene el estado del pool de conexiones
        
        Returns:
            Dict con información del estado del pool
        """
        if self._pool is None:
            return {"status": "not_initialized"}
        
        try:
            # Obtener información básica del pool
            pool_info = {
                "status": "active",
                "pool_name": self._pool.pool_name,
                "pool_size": self._pool.pool_size
            }
            
            # Intentar obtener información de la cola si está disponible
            try:
                if hasattr(self._pool, '_cnx_queue') and hasattr(self._pool._cnx_queue, 'qsize'):
                    available_connections = self._pool._cnx_queue.qsize()
                    pool_info.update({
                        "available_connections": available_connections,
                        "used_connections": self._pool.pool_size - available_connections
                    })
                else:
                    pool_info.update({
                        "available_connections": "unknown",
                        "used_connections": "unknown"
                    })
            except Exception:
                pool_info.update({
                    "available_connections": "unknown",
                    "used_connections": "unknown"
                })
            
            return pool_info
        except Exception as e:
            logger.error(f"Error obteniendo estado del pool: {e}")
            return {"status": "error", "error": str(e)}
    
    def close_pool(self):
        """Cierra el pool de conexiones"""
        if self._pool:
            try:
                # El pool se cierra automáticamente cuando se destruye
                self._pool = None
                logger.info("Pool de conexiones cerrado")
            except Exception as e:
                logger.error(f"Error cerrando pool: {e}")
    
    def test_connection(self) -> bool:
        """
        Prueba una conexión del pool
        
        Returns:
            bool: True si la conexión funciona, False en caso contrario
        """
        try:
            with self.get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                return result[0] == 1
        except Exception as e:
            logger.error(f"Error probando conexión: {e}")
            return False


# Instancia global del pool manager
pool_manager = PoolManager()


def get_pool_manager() -> PoolManager:
    """
    Obtiene la instancia del pool manager
    
    Returns:
        PoolManager: Instancia singleton del pool manager
    """
    return pool_manager


# Función de conveniencia para obtener conexión
def get_db_connection() -> mysql.connector.connection.MySQLConnection:
    """
    Obtiene una conexión del pool (función de conveniencia)
    
    Returns:
        MySQLConnection: Conexión del pool
    """
    return pool_manager.get_connection()


# Context manager de conveniencia
@contextmanager
def get_db_connection_context():
    """
    Context manager para obtener conexión del pool (función de conveniencia)
    """
    with pool_manager.get_connection_context() as conn:
        yield conn
