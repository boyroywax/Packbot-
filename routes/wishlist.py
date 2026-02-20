"""Wishlist endpoints (auth required)."""

from flask import Blueprint, jsonify, request

import database as db
import tcg_api
from routes.auth import _current_user_id

wishlist_bp = Blueprint("wishlist", __name__)


@wishlist_bp.route("/api/wishlist", methods=["GET"])
def wishlist_list():
    """Return the authenticated user's wishlist."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": db.get_wishlist(user_id)})


@wishlist_bp.route("/api/wishlist", methods=["POST"])
def wishlist_add():
    """Add a card to the authenticated user's wishlist.

    Expects JSON:
      card_id – required (fetched from TCG API if not already cached)
      notes   – optional
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    card_id = data.get("card_id", "").strip()
    if not card_id:
        return jsonify({"error": "card_id is required"}), 400

    card = tcg_api.get_card(card_id)
    if not card:
        return jsonify({"error": f"Card '{card_id}' not found"}), 404
    db.upsert_card(card)

    entry = db.add_to_wishlist(user_id=user_id, card_id=card_id, notes=data.get("notes", ""))
    return jsonify({"data": entry}), 201


@wishlist_bp.route("/api/wishlist/<int:wishlist_id>", methods=["DELETE"])
def wishlist_remove(wishlist_id: int):
    """Remove a wishlist entry owned by the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    if not db.remove_from_wishlist(wishlist_id, user_id):
        return jsonify({"error": "Wishlist entry not found"}), 404
    return jsonify({"success": True})
