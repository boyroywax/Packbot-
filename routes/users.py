"""User management endpoints."""

from flask import Blueprint, jsonify, request

import database as db

users_bp = Blueprint("users", __name__)


@users_bp.route("/api/users", methods=["POST"])
def users_create():
    """Register a new user.

    Expects JSON body:
      username – required, unique
      email    – optional
      password – optional; required to use POST /api/sessions (login)

    Returns the created user including their api_key.
    """
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "username is required"}), 400

    if db.get_user_by_username(username):
        return jsonify({"error": f"Username '{username}' is already taken"}), 409

    user = db.create_user(
        username=username,
        email=data.get("email"),
        password=data.get("password"),
    )
    user.pop("password_hash", None)
    return jsonify({"data": user}), 201


@users_bp.route("/api/users/<int:user_id>", methods=["GET"])
def users_get(user_id: int):
    """Fetch a user profile by ID."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.pop("api_key", None)
    user.pop("password_hash", None)
    return jsonify({"data": user})


@users_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
def users_delete(user_id: int):
    """Delete a user and cascade-delete their collection and scan history."""
    removed = db.delete_user(user_id)
    if not removed:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})
