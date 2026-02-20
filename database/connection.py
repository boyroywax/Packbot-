"""Connection management for Packbot database layer.

Backend is selected automatically:
  • Set DATABASE_URL=postgresql://... to use PostgreSQL
  • Otherwise SQLite is used (DATABASE_PATH, default packbot.db)
"""

import os
import sqlite3
from contextlib import contextmanager


def _get_database_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _get_database_path() -> str:
    return os.getenv("DATABASE_PATH", "packbot.db")


# Keep module-level names for backward compatibility
DATABASE_URL: str = _get_database_url()
DATABASE_PATH: str = _get_database_path()


# ---------------------------------------------------------------------------
# Backend detection & helpers
# ---------------------------------------------------------------------------

def _is_pg() -> bool:
    url = _get_database_url()
    return bool(url and url.startswith(("postgres://", "postgresql://")))


def _q(query: str) -> str:
    """Adapt ? placeholders to %s for PostgreSQL."""
    return query.replace("?", "%s") if _is_pg() else query


def _exec(conn, query: str, params=()):
    """Execute *query* against *conn*, adapting placeholders automatically.

    Returns a cursor whose .fetchone() / .fetchall() / .rowcount work the
    same way regardless of the underlying driver.
    """
    if _is_pg():
        cur = conn.cursor()
        cur.execute(_q(query), params)
        return cur
    return conn.execute(query, params)


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    """Yield a live database connection; commit on success, rollback on error."""
    if _is_pg():
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_get_database_url(), cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_get_database_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
