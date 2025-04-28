def save_followings(db_conn, username_origin, followings_list):
    if not db_conn:
        print("No hay conexión activa para guardar followings.")
        return
    
    try:
        cursor = db_conn.cursor()
        query = "INSERT INTO followings (username_origin, username_target) VALUES (%s, %s)"
        values = [(username_origin, username_target) for username_target in followings_list]
        cursor.executemany(query, values)
        db_conn.commit()
        print(f"Followings de {username_origin} guardados exitosamente.")
    except Exception as e:
        print(f"Error guardando followings: {e}")
    finally:
        cursor.close()

def save_filtered_profile(db_conn, profile_data):
    if not db_conn:
        print("No hay conexión activa para guardar perfil filtrado.")
        return

    try:
        cursor = db_conn.cursor()
        query = """
        INSERT INTO filtered_profiles (username, followers, following, posts, bio, rubro, profile_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            profile_data["username"],
            profile_data["followers"],
            profile_data["following"],
            profile_data["posts"],
            profile_data["bio"],
            profile_data["rubro"],
            profile_data["url"]
        )
        cursor.execute(query, values)
        db_conn.commit()
        print(f"Perfil {profile_data['username']} guardado exitosamente.")
    except Exception as e:
        print(f"Error guardando perfil: {e}")
    finally:
        cursor.close()
