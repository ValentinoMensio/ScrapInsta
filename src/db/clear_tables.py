import logging
from connection import get_db_connection

logger = logging.getLogger(__name__)

def clear_tables():
    conn = get_db_connection()
    if conn is None:
        logger.error("No se pudo conectar a la base de datos.")
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM followings;")
        cursor.execute("DELETE FROM filtered_profiles;")
        conn.commit()
        logger.info("Tablas limpiadas exitosamente.")
    except Exception as e:
        logger.error(f"Error limpiando tablas: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    clear_tables()
