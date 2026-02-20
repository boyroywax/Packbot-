"""User management functions for Packbot database."""

import secrets
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from database.connection import _exec, _is_pg, get_db


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(
    username: str,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> dict:
    """Create a new user and return the full row (including generated api_key).

    If *password* is provided it is bcrypt-hashed before storage.
    """
    api_key = secrets.token_urlsafe(32)
    pw_hash = generate_password_hash(password) if password else None
    with get_db() as conn:
        if _is_pg():
            cur = _exec(
                conn,
                "INSERT INTO users (username, email, api_key, password_hash) VALUES (?, ?, ?, ?) RETURNING *",
                (username, email, api_key, pw_hash),
            )
            row = cur.fetchone()
        else:
            _exec(
                conn,
                "INSERT INTO users (username, email, api_key, password_hash) VALUES (?, ?, ?, ?)",
                (username, email, api_key, pw_hash),
            )
            row = _exec(conn, "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else {}


def verify_password(username: str, password: str) -> Optional[dict]:
    """Return the user dict if *username* + *password* are valid, else None."""
    user = get_user_by_username(username)
    if not user or not user.get("password_hash"):
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def get_user(user_id: int) -> Optional[dict]:
    """Fetch a user by primary key."""
    with get_db() as conn:
        row = _exec(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[dict]:
    """Fetch a user by username."""
    with get_db() as conn:
        row = _exec(conn, "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_api_key(api_key: str) -> Optional[dict]:
    """Fetch a user by their API key."""
    with get_db() as conn:
        row = _exec(conn, "SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    return dict(row) if row else None


def delete_user(user_id: int) -> bool:
    """Delete a user (collection entries cascade-delete via FK)."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0
