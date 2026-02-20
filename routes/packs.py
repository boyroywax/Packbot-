"""Pack opening session endpoints."""

from flask import Blueprint, jsonify, request

import database as db
import scanner
from routes.auth import _current_user_id

packs_bp = Blueprint("packs", __name__)


@packs_bp.route("/api/packs/scan-barcode", methods=["POST"])
def packs_scan_barcode():
    """Detect a barcode from a camera frame.

    Accepts JSON: { "image": "data:image/jpeg;base64,..." }
    Returns: { "barcode": "...", "barcode_type": "EAN13" }

    Requires pyzbar + libzbar0.  Returns null barcode gracefully if unavailable.
    """
    data = request.get_json(force=True, silent=True) or {}
    result = scanner.scan_barcode(data.get("image", ""))
    return jsonify(result)


@packs_bp.route("/api/pack-sessions", methods=["GET"])
def pack_sessions_list():
    """List recent pack sessions for the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": db.get_user_pack_sessions(user_id)})


@packs_bp.route("/api/pack-sessions", methods=["POST"])
def pack_sessions_create():
    """Create a new pack opening session.

    Accepts JSON (all optional): barcode, set_id, set_name, pack_name
    Works without authentication (anonymous sessions allowed).
    """
    data = request.get_json(force=True, silent=True) or {}
    session = db.create_pack_session(
        user_id=_current_user_id(),
        barcode=data.get("barcode"),
        set_id=data.get("set_id"),
        set_name=data.get("set_name"),
        pack_name=data.get("pack_name"),
    )
    return jsonify({"data": session}), 201


@packs_bp.route("/api/pack-sessions/<int:session_id>", methods=["GET"])
def pack_sessions_get(session_id: int):
    """Get a pack session including its detected cards."""
    session = db.get_pack_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    session["cards"] = db.get_session_cards(session_id)
    return jsonify({"data": session})


@packs_bp.route("/api/pack-sessions/<int:session_id>/scan", methods=["POST"])
def pack_sessions_scan(session_id: int):
    """Submit a video frame for card detection during a pack opening.

    Accepts JSON:
      image        – base64 data URL (optional – omit for hints-only lookup)
      pokemon_name – optional hint
      set_code     – optional; defaults to the session's set_id
      card_number  – optional hint
    Returns the scan result dict (same as /api/scan/image).
    """
    session = db.get_pack_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "active":
        return jsonify({"error": "Session is not active"}), 400

    data = request.get_json(force=True, silent=True) or {}
    set_code = data.get("set_code") or session.get("set_id") or ""

    result = scanner.scan_from_image(
        data_url=data.get("image", ""),
        pokemon_name=data.get("pokemon_name", ""),
        set_code=set_code,
        card_number=data.get("card_number", ""),
    )

    if result.get("card"):
        db.upsert_card(result["card"])

    return jsonify(result)


@packs_bp.route("/api/pack-sessions/<int:session_id>/cards", methods=["POST"])
def pack_sessions_add_card(session_id: int):
    """Add a confirmed card to a pack session.

    Accepts JSON:
      card_id     – required
      card_name, number, set_name, image_small, rarity, confidence – optional
    """
    session = db.get_pack_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "active":
        return jsonify({"error": "Session is not active"}), 400

    data = request.get_json(force=True, silent=True) or {}
    card_id = data.get("card_id", "").strip()
    if not card_id:
        return jsonify({"error": "card_id is required"}), 400

    entry = db.add_card_to_session(
        session_id=session_id,
        card_id=card_id,
        card_name=data.get("card_name", ""),
        number=data.get("number", ""),
        set_name=data.get("set_name", ""),
        image_small=data.get("image_small", ""),
        rarity=data.get("rarity", ""),
        confidence=float(data.get("confidence", 1.0)),
    )
    return jsonify({"data": entry}), 201


@packs_bp.route("/api/pack-sessions/<int:session_id>/cards/<int:session_card_id>", methods=["DELETE"])
def pack_sessions_remove_card(session_id: int, session_card_id: int):
    """Remove a card entry from an active pack session."""
    session = db.get_pack_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "active":
        return jsonify({"error": "Session is not active"}), 400
    if not db.remove_card_from_session(session_card_id, session_id):
        return jsonify({"error": "Card entry not found"}), 404
    return jsonify({"success": True})


@packs_bp.route("/api/pack-sessions/<int:session_id>/complete", methods=["POST"])
def pack_sessions_complete(session_id: int):
    """Complete a pack session, optionally adding all cards to the collection.

    Accepts JSON:
      add_to_collection – boolean (default false)
      condition         – NM / LP / MP / HP / DMG (default NM)
    """
    session = db.get_pack_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "active":
        return jsonify({"error": "Session is not active"}), 400

    data = request.get_json(force=True, silent=True) or {}
    user_id = _current_user_id()
    added = 0

    if data.get("add_to_collection"):
        condition = data.get("condition", "NM")
        for card in db.get_session_cards(session_id):
            if card.get("card_id"):
                db.add_to_collection(card_id=card["card_id"], condition=condition, user_id=user_id)
                added += 1

    db.complete_pack_session(session_id)
    return jsonify({"success": True, "cards_added": added})


@packs_bp.route("/api/pack-sessions/<int:session_id>", methods=["DELETE"])
def pack_sessions_cancel(session_id: int):
    """Cancel and delete a pack session (cascades to its cards)."""
    if not db.get_pack_session(session_id):
        return jsonify({"error": "Session not found"}), 404
    db.cancel_pack_session(session_id)
    return jsonify({"success": True})
