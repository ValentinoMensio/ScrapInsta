import mysql.connector
from mysql.connector import Error

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",       # O el nombre del contenedor si usás Docker (por ejemplo: "db")
            user="scrapinsta",
            password="4312",
            database="scrapinsta_db"
        )
        if connection.is_connected():
            print("Conexión a MySQL exitosa")
            return connection
    except Error as e:
        print(f"Error de conexión a MySQL: {e}")
        return None
