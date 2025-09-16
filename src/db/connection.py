"""
Módulo de conexión a base de datos con connection pooling
"""
import logging
from mysql.connector import Error
from .pool_manager import get_db_connection as get_pooled_connection, get_db_connection_context

logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Obtiene una conexión del pool de conexiones
    
    Returns:
        MySQLConnection: Conexión del pool o None si hay error
        
    Note:
        Esta función mantiene compatibilidad con el código existente.
        Para mejor rendimiento, usa get_db_connection_context() en su lugar.
    """
    try:
        connection = get_pooled_connection()
        if connection and connection.is_connected():
            logger.debug("Conexión obtenida del pool exitosamente")
            return connection
        else:
            logger.error("No se pudo obtener conexión válida del pool")
            return None
    except Error as e:
        logger.error(f"Error obteniendo conexión del pool: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado obteniendo conexión: {e}")
        return None


def get_db_connection_context():
    """
    Context manager para obtener conexión del pool
    
    Returns:
        Context manager que maneja automáticamente la conexión
        
    Usage:
        with get_db_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
            result = cursor.fetchall()
    """
    from .pool_manager import get_db_connection_context as pool_context
    return pool_context()
