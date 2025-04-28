from connection import get_db_connection

def clear_tables():
    conn = get_db_connection()
    if conn is None:
        print("No se pudo conectar a la base de datos.")
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM followings;")
        cursor.execute("DELETE FROM filtered_profiles;")
        conn.commit()
        print("Tablas limpiadas exitosamente.")
    except Exception as e:
        print(f"Error limpiando tablas: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    clear_tables()
