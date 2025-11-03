from __future__ import annotations

from typing import Callable, Iterable, Optional, Protocol

from scrapinsta.crosscutting.retry import retry
from scrapinsta.domain.models.profile_models import Following, Username
from scrapinsta.domain.ports.followings_repo import (
    FollowingsRepo,
    FollowingsPersistenceError,
)

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

# =========================
# Tipos de bajo nivel (DB-API)
# =========================

class _Cursor(Protocol):
    def execute(self, query: str, params: Iterable[object] | None = None) -> None: ...
    def executemany(self, query: str, seq_of_params: Iterable[Iterable[object]]) -> None: ...
    def fetchall(self) -> list[tuple]: ...
    def close(self) -> None: ...
    @property
    def rowcount(self) -> int: ...


class _Conn(Protocol):
    def cursor(self) -> _Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


# =========================
# Implementación SQL del repositorio
# =========================

class FollowingsRepoSQL(FollowingsRepo):
    """
    Repositorio SQL para followings (owner -> target) con idempotencia delegada a la DB.

    - Requiere un índice/constraint único en (username_origin, username_target)
      por ejemplo en MySQL:
          ALTER TABLE followings
          ADD UNIQUE KEY uq_followings (username_origin, username_target);
    """

    def __init__(self, conn_factory: Callable[[], _Conn], *, dialect: str = "mysql") -> None:
        """
        Args:
            conn_factory: callable que retorna una conexión DB-API abierta.
            dialect: "mysql" (INSERT IGNORE) o "postgres" (ON CONFLICT DO NOTHING).
        """
        self._conn_factory = conn_factory
        self._dialect = dialect.lower()

        if self._dialect not in {"mysql", "postgres"}:
            raise ValueError("dialect must be 'mysql' or 'postgres'")

    # Reintenta en errores transientes (timeouts, deadlocks, conexiones perdidas)
    @retry(DB_ERRORS)
    def save_for_owner(self, owner: Username, followings: Iterable[Following]) -> int:
        """
        Inserta followings NUEVOS para 'owner' de forma idempotente.
        Retorna cuántas filas fueron realmente insertadas.
        """
        params = [(owner.value, f.target.value) for f in followings]
        if not params:
            return 0

        insert_sql: str
        if self._dialect == "mysql":
            # Idempotencia en MySQL
            insert_sql = (
                "INSERT IGNORE INTO followings (username_origin, username_target) "
                "VALUES (%s, %s)"
            )
        else:
            # Idempotencia en Postgres (la constraint se llama uq_followings en el ejemplo)
            insert_sql = (
                "INSERT INTO followings (username_origin, username_target) "
                "VALUES (%s, %s) "
                "ON CONFLICT (username_origin, username_target) DO NOTHING"
            )

        conn = self._conn_factory()
        cur: Optional[_Cursor] = None
        try:
            cur = conn.cursor()
            cur.executemany(insert_sql, params)
            conn.commit()
            # En MySQL con INSERT IGNORE, rowcount suele reflejar los realmente insertados.
            # En Postgres con DO NOTHING también.
            return getattr(cur, "rowcount", 0)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            raise FollowingsPersistenceError("Fallo guardando followings", cause=e) from e
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally:
                conn.close()

    @retry(DB_ERRORS)
    def get_for_owner(self, owner: Username, limit: int | None = None) -> list[Following]:
        """
        Devuelve las relaciones (owner -> target) persistidas.
        Si 'limit' > 0, aplica recorte en el SELECT.
        """
        base_sql = (
            "SELECT username_origin, username_target "
            "FROM followings "
            "WHERE username_origin = %s"
        )
        params: list[object] = [owner.value]

        if limit is not None and limit > 0:
            # Compatible con MySQL y Postgres
            base_sql += " LIMIT %s"
            params.append(limit)

        conn = self._conn_factory()
        cur: Optional[_Cursor] = None
        try:
            cur = conn.cursor()
            cur.execute(base_sql, params)
            rows = cur.fetchall()  # list[tuple[str, str]]
            # Construimos entidades de dominio (ya normalizadas)
            out: list[Following] = []
            for origin, target in rows:
                # origin debe ser igual a owner.value; usamos igual VO para coherencia
                f = Following(owner=Username(value=origin), target=Username(value=target))
                out.append(f)
            return out
        except Exception as e:
            raise FollowingsPersistenceError("Fallo leyendo followings", cause=e) from e
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally:
                conn.close()

