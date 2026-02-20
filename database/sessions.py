"""Session management functions for Packbot database."""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from database.connection import _exec, get_db


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

_SESSION_DURATION_DAYS: int = int(os.getenv("SESSION_DURATION_DAYS", 30))


def _utc_str(dt: datetime) -> str:
    """Format a datetime as a UTC string that sorts correctly in SQLite."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def create_session(user_id: int, duration_days: Optional[int] = None) -> dict:
    """Create a new session for *user_id* and return the session row."""
    duration_days = duration_days if duration_days is not None else _SESSION_DURATION_DAYS
    token = secrets.token_urlsafe(32)
    expires_at = _utc_str(datetime.now(timezone.utc) + timedelta(days=duration_days))
    with get_db() as conn:
        _exec(
            conn,
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        row = _exec(conn, "SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
    return dict(row) if row else {}


def get_session(token: str) -> Optional[dict]:
    """Return the session row if the token is valid and not expired.

    Also bumps *last_seen* to the current time.
    """
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        row = _exec(
            conn,
            "SELECT * FROM sessions WHERE token = ? AND expires_at > ?",
            (token, now),
        ).fetchone()
        if row:
            _exec(
                conn,
                "UPDATE sessions SET last_seen = ? WHERE token = ?",
                (now, token),
            )
    return dict(row) if row else None


def delete_session(token: str) -> bool:
    """Invalidate a single session token (logout)."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM sessions WHERE token = ?", (token,))
        return cur.rowcount > 0


def delete_all_user_sessions(user_id: int) -> int:
    """Invalidate all sessions for *user_id*. Returns number of rows deleted."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return cur.rowcount


def get_user_sessions(user_id: int) -> list:
    """Return all active (non-expired) sessions for *user_id*."""
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        rows = _exec(
            conn,
            """
            SELECT token, user_id, created_at, expires_at, last_seen
            FROM sessions
            WHERE user_id = ? AND expires_at > ?
            ORDER BY last_seen DESC
            """,
            (user_id, now),
        ).fetchall()
    return [dict(r) for r in rows]


def cleanup_expired_sessions() -> int:
    """Delete all expired sessions. Returns number of rows removed."""
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM sessions WHERE expires_at <= ?", (now,))
        return cur.rowcount
