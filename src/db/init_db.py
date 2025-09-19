import mysql.connector
from mysql.connector import Error
import logging
# en src/db/init_db.py
from config.settings import DATABASE_CONFIG


logger = logging.getLogger(__name__)

DB_NAME = DATABASE_CONFIG['database']

TABLES = {}

TABLES["followings"] = (
    "CREATE TABLE IF NOT EXISTS followings ("
    "  id INT AUTO_INCREMENT PRIMARY KEY,"
    "  username_origin VARCHAR(255) NOT NULL,"
    "  username_target VARCHAR(255) NOT NULL,"
    "  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  UNIQUE KEY unique_following_pair (username_origin, username_target),"
    "  INDEX (username_origin),"
    "  INDEX (username_target)"
    ") ENGINE=InnoDB"
)

TABLES["filtered_profiles"] = (
    "CREATE TABLE IF NOT EXISTS filtered_profiles ("
    "  id INT AUTO_INCREMENT PRIMARY KEY,"
    "  username VARCHAR(255) NOT NULL UNIQUE,"
    "  followers INT UNSIGNED,"
    "  following INT UNSIGNED,"
    "  posts INT UNSIGNED,"
    "  bio TEXT,"
    "  rubro VARCHAR(100),"
    "  profile_url TEXT,"
    "  message_sent BOOLEAN DEFAULT FALSE,"
    "  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  INDEX (username)"
    ") ENGINE=InnoDB"
)

def connect_server():
    return mysql.connector.connect(
        host=DATABASE_CONFIG['host'],
        user=DATABASE_CONFIG['user'],
        password=DATABASE_CONFIG['password']
    )

def create_database(cursor):
    try:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;"
        )
        logger.info(f"✔ Base de datos `{DB_NAME}` verificada/creada.")
    except mysql.connector.Error as err:
        logger.error(f"! Error creando base de datos: {err}")
        exit(1)

def drop_tables(cursor):
    """
    Elimina todas las tablas existentes
    """
    try:
        # Desactivar verificación de claves foráneas
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Obtener todas las tablas existentes
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        
        # Eliminar cada tabla
        for table in tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                logger.info(f"Tabla {table} eliminada correctamente")
            except Error as e:
                logger.error(f"Error eliminando tabla {table}: {e}")
        
        # Reactivar verificación de claves foráneas
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
    except Error as e:
        logger.error(f"Error en drop_tables: {e}")
        raise

def create_tables(connection):
    cursor = connection.cursor()
    drop_tables(cursor)
    for table_name, ddl in TABLES.items():
        try:
            cursor.execute(ddl)
            logger.info(f"✔ Tabla `{table_name}` verificada/creada.")
        except mysql.connector.Error as err:
            logger.error(f"! Error creando tabla `{table_name}`: {err}")

    cursor.close()

def init_database():
    """
    Inicializa la base de datos y crea las tablas necesarias
    """
    conn = None
    try:
        # Conectar a MySQL
        conn = mysql.connector.connect(
            host=DATABASE_CONFIG['host'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password']
        )
        
        if conn.is_connected():
            cursor = conn.cursor()
            
            # Crear base de datos si no existe
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
            cursor.execute(f"USE {DB_NAME}")
            
            # Eliminar todas las tablas existentes
            drop_tables(cursor)
            
            # Crear tabla de perfiles filtrados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filtered_profiles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    bio TEXT,
                    followers INT,
                    following INT,
                    posts INT,
                    avg_likes FLOAT,
                    avg_comments FLOAT,
                    avg_views FLOAT,
                    is_private BOOLEAN,
                    is_verified BOOLEAN,
                    rubro VARCHAR(100),
                    engagement_score FLOAT,
                    success_score FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_username (username)
                )
            """)
            
            # Crear tabla de followings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS followings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username_origin VARCHAR(255) NOT NULL,
                    username_target VARCHAR(255) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_following_pair (username_origin, username_target),
                    INDEX (username_origin),
                    INDEX (username_target)
                )
            """)
            
            conn.commit()
            logger.info("Base de datos inicializada correctamente")
            
    except Error as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def main():
    logging.info("Inicializando base de datos...")
    # Conexión inicial (sin base de datos)
    connection = connect_server()
    cursor = connection.cursor()

    # Crear DB si no existe
    create_database(cursor)
    cursor.close()
    connection.close()

    # Conexión ahora a la base de datos específica
    connection = mysql.connector.connect(
        host=DATABASE_CONFIG['host'],
        user=DATABASE_CONFIG['user'],
        password=DATABASE_CONFIG['password'],
        database=DB_NAME
    )

    # Crear tablas si no existen
    create_tables(connection)
    connection.close()

if __name__ == "__main__":
    init_database()
