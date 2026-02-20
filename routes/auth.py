"""Auth helper functions shared across route blueprints."""

from typing import Optional

from flask import request

import database as db


def _resolve_auth() -> Optional[dict]:
    """Resolve the authenticated user for the current request.

    Checks in order:
      1. ``Authorization: Bearer <session-token>``
      2. ``X-Api-Key`` header  or  ``api_key`` query param
    Returns the user dict (without password_hash) or None.
    """
    # 1. Bearer session token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            session = db.get_session(token)
            if session:
                user = db.get_user(session["user_id"])
                if user:
                    user.pop("password_hash", None)
                    return user

    # 2. Permanent API key
    key = request.headers.get("X-Api-Key") or request.args.get("api_key", "")
    if key:
        user = db.get_user_by_api_key(key)
        if user:
            user.pop("password_hash", None)
            return user

    return None


def _current_user_id() -> Optional[int]:
    """Thin wrapper – returns just the user id (or None)."""
    user = _resolve_auth()
    return user["id"] if user else None


def _bearer_token() -> Optional[str]:
    """Extract the Bearer token from the current request, if present."""
    h = request.headers.get("Authorization", "")
    return h[7:].strip() if h.startswith("Bearer ") else None
