"""Session (login / logout / introspection) endpoints."""

import os

from flask import Blueprint, jsonify, request

import database as db
from routes.auth import _resolve_auth, _current_user_id, _bearer_token

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/api/sessions", methods=["POST"])
def sessions_login():
    """Login with username + password and obtain a session token.

    Expects JSON body: { "username": "...", "password": "..." }

    Returns:
      token      – Bearer token for subsequent requests
      expires_at – UTC timestamp when the session expires
      user       – public user profile (no api_key / password_hash)
    """
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = db.verify_password(username, password)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    duration = int(os.getenv("SESSION_DURATION_DAYS", 30))
    session = db.create_session(user["id"], duration_days=duration)

    user.pop("password_hash", None)
    user.pop("api_key", None)
    return jsonify({
        "data": {
            "token": session["token"],
            "expires_at": session["expires_at"],
            "user": user,
        }
    }), 201


@sessions_bp.route("/api/sessions/me", methods=["GET"])
def sessions_me():
    """Return the authenticated user's public profile.

    Works with both Bearer session tokens and X-Api-Key.
    Returns 401 if not authenticated.
    """
    user = _resolve_auth()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": user})


@sessions_bp.route("/api/sessions", methods=["GET"])
def sessions_list():
    """List all active sessions for the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": db.get_user_sessions(user_id)})


@sessions_bp.route("/api/sessions", methods=["DELETE"])
def sessions_logout():
    """Invalidate the current Bearer session token (logout).

    Must be authenticated with a Bearer token; returns 400 for API-key-only
    requests since there is no session token to invalidate.
    """
    token = _bearer_token()
    if not token:
        return jsonify({"error": "No Bearer session token to invalidate"}), 400
    db.delete_session(token)
    return jsonify({"success": True})


@sessions_bp.route("/api/sessions/all", methods=["DELETE"])
def sessions_logout_all():
    """Invalidate every active session for the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    count = db.delete_all_user_sessions(user_id)
    return jsonify({"success": True, "sessions_revoked": count})
