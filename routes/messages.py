"""Messaging endpoints."""

from flask import Blueprint, jsonify, request

import database as db
import notifier
from routes.auth import _resolve_auth, _current_user_id

messages_bp = Blueprint("messages", __name__)


@messages_bp.route("/api/messages/unread-count", methods=["GET"])
def messages_unread_count():
    """Return the number of unread messages for the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": {"count": db.get_unread_count(user_id)}})


@messages_bp.route("/api/messages", methods=["GET"])
def messages_inbox():
    """Return the authenticated user's inbox (received messages)."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"data": db.get_inbox(user_id, limit=limit)})


@messages_bp.route("/api/messages", methods=["POST"])
def messages_send():
    """Send a message to another user.

    Expects JSON:
      to      – recipient username (required)
      subject – optional string
      body    – message text (required)
    """
    sender = _resolve_auth()
    if not sender:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    to_username = (data.get("to") or "").strip()
    body = (data.get("body") or "").strip()

    if not to_username:
        return jsonify({"error": "to field is required"}), 400
    if not body:
        return jsonify({"error": "body field is required"}), 400

    recipient = db.get_user_by_username(to_username)
    if not recipient:
        return jsonify({"error": f"User '{to_username}' not found"}), 404
    if recipient["id"] == sender["id"]:
        return jsonify({"error": "Cannot send a message to yourself"}), 400

    subject = (data.get("subject") or "").strip()
    message = db.send_message(
        sender_id=sender["id"],
        recipient_id=recipient["id"],
        subject=subject,
        body=body,
    )

    # Fire-and-forget email notification
    notifier.notify_new_message(
        recipient_email=recipient.get("email", ""),
        sender_username=sender["username"],
        subject=subject or body[:60],
    )

    return jsonify({"data": message}), 201


@messages_bp.route("/api/messages/<int:message_id>", methods=["GET"])
def messages_get(message_id: int):
    """Fetch a message by ID.  Marks it as read if the requester is the recipient."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    msg = db.get_message(message_id)
    if not msg:
        return jsonify({"error": "Message not found"}), 404
    if msg["sender_id"] != user_id and msg["recipient_id"] != user_id:
        return jsonify({"error": "Access denied"}), 403

    if msg["recipient_id"] == user_id and not msg["read"]:
        db.mark_message_read(message_id)
        msg["read"] = 1

    return jsonify({"data": msg})


@messages_bp.route("/api/messages/<int:message_id>", methods=["DELETE"])
def messages_delete(message_id: int):
    """Delete a message.  Allowed if the requester is sender or recipient."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    msg = db.get_message(message_id)
    if not msg:
        return jsonify({"error": "Message not found"}), 404
    if msg["sender_id"] != user_id and msg["recipient_id"] != user_id:
        return jsonify({"error": "Access denied"}), 403

    db.delete_message(message_id, user_id)
    return jsonify({"success": True})
