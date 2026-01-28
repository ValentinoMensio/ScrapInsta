from __future__ import annotations

import os
from typing import Callable, Optional, Dict, Any
from urllib.parse import urlparse, unquote
import pymysql

from scrapinsta.crosscutting.retry import retry, RetryError

from scrapinsta.config.settings import Settings


def _parse_mysql_dsn(dsn: str) -> Optional[Dict[str, Any]]:
    """
    Soporta: mysql://user:pass@host:port/dbname?charset=utf8mb4
    """
    if not dsn:
        return None
    u = urlparse(dsn)
    if u.scheme not in ("mysql", "mysql+pymysql"):
        return None
    host = u.hostname or "localhost"
    port = u.port or 3307
    user = unquote(u.username or "")
    password = unquote(u.password or "")
    db = u.path.lstrip("/") or ""
    q = {}
    if u.query:
        for kv in u.query.split("&"):
            if not kv:
                continue
            if "=" in kv:
                k, v = kv.split("=", 1)
                q[k] = v
            else:
                q[kv] = ""
    charset = q.get("charset", "utf8mb4")
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "db": db,
        "charset": charset,
    }


def _normalize_params(dsn_or_settings: Optional[str | Settings]) -> Dict[str, Any]:
    """
    Si viene un DSN válido lo parsea; si no, toma datos de Settings.
    """
    s = dsn_or_settings if isinstance(dsn_or_settings, Settings) else Settings()
    if isinstance(dsn_or_settings, str) and dsn_or_settings.strip():
        p = _parse_mysql_dsn(dsn_or_settings.strip())
        if p:
            return {
                **p,
                "connect_timeout": float(s.db_connect_timeout),
                "read_timeout": float(s.db_read_timeout),
                "write_timeout": float(s.db_write_timeout),
            }

    return {
        "host": s.db_host,
        "port": int(s.db_port),
        "user": s.db_user,
        "password": s.db_pass,
        "db": s.db_name,
        "charset": "utf8mb4",
        "connect_timeout": float(s.db_connect_timeout),
        "read_timeout": float(s.db_read_timeout),
        "write_timeout": float(s.db_write_timeout),
    }


def _connect(params: Dict[str, Any]):
    retries = int(os.getenv("DB_CONNECT_RETRIES", "2"))

    @retry((pymysql.err.OperationalError, pymysql.err.InterfaceError), max_retries=retries)
    def _connect_retry():
        return pymysql.connect(
            host=params["host"],
            port=int(params["port"]),
            user=params["user"],
            password=params["password"],
            database=params["db"],
            charset=params["charset"],
            connect_timeout=float(params.get("connect_timeout", 5.0)),
            read_timeout=float(params.get("read_timeout", 10.0)),
            write_timeout=float(params.get("write_timeout", 10.0)),
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

    try:
        return _connect_retry()
    except RetryError as e:
        raise e.last_error or e


class ConnectionProvider:
    """
    Proveedor OO usado por repos que esperan un objeto con __call__ o connect().
    Ejemplos de uso desde repos:
        con = provider()             # usa __call__
        con = provider.connect()     # o método explícito
    """
    def __init__(self, dsn_or_settings: Optional[str | Settings] = None) -> None:
        self._params = _normalize_params(dsn_or_settings)

    def __call__(self):
        return _connect(self._params)

    def connect(self):
        return _connect(self._params)


def make_mysql_conn_factory(dsn_or_settings: Optional[str | Settings] = None) -> Callable[[], Any]:
    """
    Proveedor funcional (callable) usado por repos que esperan conn_factory=callable.
    """
    params = _normalize_params(dsn_or_settings)

    def _factory():
        return _connect(params)

    return _factory
