from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Callable, Iterable, Protocol, Optional, Sequence

from scrapinsta.domain.ports.profile_repo import (
    ProfileRepository,
    ProfileRepoError,
    ProfileValidationError,
    ProfilePersistenceError,
)
from scrapinsta.domain.models.profile_models import (
    ProfileSnapshot,
    BasicStats,
    ReelMetrics,
    PostMetrics,
)
from scrapinsta.crosscutting.retry import retry

logger = logging.getLogger(__name__)

# Errores específicos de DB para retry
try:
    import pymysql
    DB_ERRORS = (pymysql.Error,)
except ImportError:
    try:
        import mysql.connector
        DB_ERRORS = (mysql.connector.Error,)
    except ImportError:
        # Fallback genérico si no hay driver específico
        DB_ERRORS = (Exception,)


class _Cursor(Protocol):
    def execute(self, query: str, params: Iterable[object] | None = ...) -> None: ...
    def executemany(self, query: str, seq_of_params: Iterable[Iterable[object]]) -> None: ...
    def fetchone(self) -> tuple | None: ...
    def close(self) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class ProfileRepoSQL(ProfileRepository):
    def __init__(self, conn_factory: Callable[[], _Connection]) -> None:
        self._conn_factory = conn_factory

    # ---------- helpers ----------
    def _select_scalar(self, cur, sql: str, params: tuple):
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        # Soporta DictCursor y cursores por índice
        try:
            # tuple/list
            if isinstance(row, (tuple, list)):
                return int(row[0]) if row[0] is not None else None
            # dict-like
            if isinstance(row, dict):
                val = row.get("id")
                if val is None and row:
                    # tomar el primer valor cualquiera (por compat antigua)
                    val = next(iter(row.values()))
                return int(val) if val is not None else None
            # fallback conservador
            return None
        except Exception:
          return None


    # ---------- API ----------
    @retry(DB_ERRORS)
    def get_profile_id(self, username: str) -> Optional[int]:
        u = (username or "").strip().lower()
        if not u:
            return None
        conn = self._conn_factory()
        cur: _Cursor | None = None
        try:
            cur = conn.cursor()
            return self._select_scalar(cur, "SELECT id FROM profiles WHERE username = %s", (u,))
        finally:
            try:
                if cur: cur.close()
            finally:
                conn.close()

    @retry(DB_ERRORS)
    def get_last_analysis_date(self, username: str) -> Optional[str]:
        """
        Obtiene la fecha del último análisis para un usuario.
        Retorna None si no existe análisis previo.
        """
        u = (username or "").strip().lower()
        if not u:
            return None

        conn = self._conn_factory()
        cur: _Cursor | None = None
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(created_at) as last_analysis
                FROM profile_analysis pa
                JOIN profiles p ON pa.profile_id = p.id
                WHERE p.username = %s
                """,
                (u,)
            )
            result = cur.fetchone()
            if not result:
                return None
            # Soporta cursores por índice y DictCursor
            try:
                if isinstance(result, (tuple, list)):
                    val = result[0]
                elif isinstance(result, dict):
                    val = result.get("last_analysis")
                    if val is None and result:
                        # compat: tomar el primer valor si el alias no está
                        val = next(iter(result.values()))
                else:
                    # intento de atributo (fallback muy defensivo)
                    val = getattr(result, "last_analysis", None)

                if val is None:
                    return None
                if isinstance(val, (datetime, date)):
                    return val.isoformat()
                # si viene como str u otro tipo serializable
                return str(val)
            except Exception:
                return None
        except Exception as e:
            logger.exception("get_last_analysis_date failed", extra={"username": u})
            return None
        finally:
            try:
                if cur: cur.close()
            finally:
                conn.close()

    @retry(DB_ERRORS)
    def upsert_profile(self, snap: ProfileSnapshot) -> int:
        u = (snap.username or "").strip().lower()
        if not u:
            raise ValueError("username inválido")

        conn = self._conn_factory()
        cur: _Cursor | None = None
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO profiles (username, bio,
                                      followers, followings, posts,
                                      is_verified, privacy)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    bio=VALUES(bio),
                    followers=VALUES(followers),
                    followings=VALUES(followings),
                    posts=VALUES(posts),
                    is_verified=VALUES(is_verified),
                    privacy=VALUES(privacy)
                """,
                (
                    u,
                    snap.bio,
                    snap.followers,
                    snap.followings,
                    snap.posts,
                    snap.is_verified,
                    snap.privacy.value if hasattr(snap.privacy, "value") else str(snap.privacy)
                ),
            )
            conn.commit()

            pid = self.get_profile_id(u)
            if pid is None:
                raise RuntimeError("No se recuperó profile_id luego del upsert")
            return pid

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.exception("upsert_profile failed", extra={"username": u})
            raise ProfilePersistenceError("Failed to upsert profile", cause=e) from e
        finally:
            try:
                if cur: cur.close()
            finally:
                conn.close()

    @retry(DB_ERRORS)
    def save_analysis_snapshot(
        self,
        profile_id: int,
        snapshot: ProfileSnapshot,
        basic: Optional[BasicStats],
        reels: Optional[Sequence[ReelMetrics]],
        posts: Optional[Sequence[PostMetrics]],
    ) -> int:
        """
        Guarda un registro del análisis usando SOLO modelos de dominio.
        NO debe recibir DTOs de aplicación.
        """
        conn = self._conn_factory()
        cur: _Cursor | None = None
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO profile_analysis (profile_id, source, rubro, engagement_score, success_score, analyzed_at)
                VALUES (%s,%s,%s,%s,%s,NOW())
                """,
                (
                    profile_id,
                    "selenium",
                    snapshot.rubro,
                    basic.engagement_score if basic else None,
                    basic.success_score if basic else None,
                ),
            )
            conn.commit()
            cur.execute("SELECT LAST_INSERT_ID() as id")
            row = cur.fetchone()
            return int(row.get("id", 0)) if row and row.get("id") is not None else 0
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.exception("save_analysis_snapshot failed", extra={"profile_id": profile_id})
            raise ProfilePersistenceError("Failed to save analysis snapshot", cause=e) from e
        finally:
            try:
                if cur: cur.close()
            finally:
                conn.close()
