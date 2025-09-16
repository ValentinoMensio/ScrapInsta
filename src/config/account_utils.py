import json
from pathlib import Path

def load_accounts(filepath="src/config/accounts.json"):
    with open(Path(filepath), "r", encoding="utf-8") as f:
        return json.load(f)

def get_followings_from_origin(origin_username, limit=None):
    from db.connection import get_db_connection_context
    with get_db_connection_context() as conn:
        cursor = conn.cursor()
        query = "SELECT username_target FROM followings WHERE username_origin = %s"
        params = [origin_username]
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [row[0] for row in rows] 