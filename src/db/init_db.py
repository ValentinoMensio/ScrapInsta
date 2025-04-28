import mysql.connector
from mysql.connector import errorcode

DB_NAME = "scrapinsta_db"

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
    "  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  INDEX (username)"
    ") ENGINE=InnoDB"
)

def connect_server():
    return mysql.connector.connect(
        host="localhost",
        user="scrapinsta",                 # <--- tu usuario MySQL
        password="4312"      # <--- tu contraseña MySQL
    )

def create_database(cursor):
    try:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET 'utf8mb4'"
        )
        print(f"✔ Base de datos `{DB_NAME}` verificada/creada.")
    except mysql.connector.Error as err:
        print(f"! Error creando base de datos: {err}")
        exit(1)

def drop_tables(cursor):
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table_name in TABLES.keys():
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            print(f"✔ Tabla `{table_name}` eliminada (si existía).")
        except mysql.connector.Error as err:
            print(f"! Error eliminando tabla `{table_name}`: {err}")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1") 

def create_tables(connection):
    cursor = connection.cursor()
    drop_tables(cursor)
    for table_name, ddl in TABLES.items():
        try:
            cursor.execute(ddl)
            print(f"✔ Tabla `{table_name}` verificada/creada.")
        except mysql.connector.Error as err:
            print(f"! Error creando tabla `{table_name}`: {err}")

    cursor.close()

def main():
    # Conexión inicial (sin base de datos)
    connection = connect_server()
    cursor = connection.cursor()

    # Crear DB si no existe
    create_database(cursor)
    cursor.close()
    connection.close()

    # Conexión ahora a la base de datos específica
    connection = mysql.connector.connect(
        host="localhost",
        user="scrapinsta",
        password="4312",
        database=DB_NAME
    )

    # Crear tablas si no existen
    create_tables(connection)
    connection.close()

if __name__ == "__main__":
    main()
