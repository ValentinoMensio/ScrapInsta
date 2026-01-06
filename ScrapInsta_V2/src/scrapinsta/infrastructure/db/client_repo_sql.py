from __future__ import annotations

import pymysql
from typing import Optional, Dict, Any
from passlib.context import CryptContext

from scrapinsta.domain.ports.client_repo import ClientRepo
from scrapinsta.infrastructure.db.connection_provider import _normalize_params

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class ClientRepoSQL(ClientRepo):
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._params = _normalize_params(dsn)

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=self._params["host"],
            port=self._params["port"],
            user=self._params["user"],
            password=self._params["password"],
            database=self._params["db"],
            charset=self._params["charset"],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )

    def get_by_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT id, name, email, api_key_hash, status, created_at, updated_at, metadata
            FROM clients
            WHERE id = %s AND status != 'deleted'
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (client_id,))
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
        finally:
            con.close()

    def get_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT id, name, email, api_key_hash, status, created_at, updated_at, metadata
            FROM clients
            WHERE status = 'active'
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                for row in rows:
                    if pwd_context.verify(api_key, row['api_key_hash']):
                        return dict(row)
                return None
        finally:
            con.close()

    def create(self, client_id: str, name: str, email: Optional[str], api_key_hash: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        import json
        sql = """
            INSERT INTO clients (id, name, email, api_key_hash, status, metadata)
            VALUES (%s, %s, %s, %s, 'active', %s)
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (client_id, name, email, api_key_hash, json.dumps(metadata) if metadata else None))
            con.commit()
        finally:
            con.close()

    def update_status(self, client_id: str, status: str) -> None:
        sql = """
            UPDATE clients
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (status, client_id))
            con.commit()
        finally:
            con.close()

    def get_limits(self, client_id: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT client_id, requests_per_minute, requests_per_hour, requests_per_day, messages_per_day
            FROM client_limits
            WHERE client_id = %s
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (client_id,))
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
        finally:
            con.close()

    def update_limits(self, client_id: str, limits: Dict[str, int]) -> None:
        sql = """
            INSERT INTO client_limits (client_id, requests_per_minute, requests_per_hour, requests_per_day, messages_per_day)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                requests_per_minute = VALUES(requests_per_minute),
                requests_per_hour = VALUES(requests_per_hour),
                requests_per_day = VALUES(requests_per_day),
                messages_per_day = VALUES(messages_per_day)
        """
        con = self._connect()
        try:
            with con.cursor() as cur:
                cur.execute(sql, (
                    client_id,
                    limits.get('requests_per_minute', 60),
                    limits.get('requests_per_hour', 1000),
                    limits.get('requests_per_day', 10000),
                    limits.get('messages_per_day', 500)
                ))
            con.commit()
        finally:
            con.close()

