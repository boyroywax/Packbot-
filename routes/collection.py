"""Collection endpoints."""

from flask import Blueprint, jsonify, request

import database as db
import tcg_api
from routes.auth import _current_user_id

collection_bp = Blueprint("collection", __name__)

_VALID_LISTING_TYPES = {"for_trade", "for_sale", None}


@collection_bp.route("/api/collection", methods=["GET"])
def collection_list():
    """Get the collection with optional filtering.

    Query params: search, set_id, page, page_size
    Pass X-Api-Key header to scope results to the authenticated user.
    """
    search = request.args.get("search", "")
    set_id = request.args.get("set_id", "")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)

    result = db.get_collection(
        search=search, set_id=set_id, user_id=_current_user_id(),
        page=page, page_size=page_size,
    )
    return jsonify(result)


@collection_bp.route("/api/collection", methods=["POST"])
def collection_add():
    """Add a card to the collection.

    Expects JSON body:
      card_id   – required
      condition – NM / LP / MP / HP / DMG (default NM)
      foil      – boolean (default false)
      quantity  – integer (default 1)
      notes     – optional string

    Pass X-Api-Key header to associate the entry with a specific user.
    """
    data = request.get_json(force=True, silent=True) or {}
    card_id = data.get("card_id", "").strip()
    if not card_id:
        return jsonify({"error": "card_id is required"}), 400

    # Ensure card is in local DB (fetch from API if needed)
    card = tcg_api.get_card(card_id)
    if not card:
        return jsonify({"error": f"Card '{card_id}' not found in TCG API"}), 404
    db.upsert_card(card)

    entry = db.add_to_collection(
        card_id=card_id,
        condition=data.get("condition", "NM"),
        foil=bool(data.get("foil", False)),
        quantity=int(data.get("quantity", 1)),
        notes=data.get("notes", ""),
        user_id=_current_user_id(),
    )
    return jsonify({"data": entry}), 201


@collection_bp.route("/api/collection/<int:entry_id>", methods=["DELETE"])
def collection_remove(entry_id: int):
    """Remove a collection entry by its row ID."""
    removed = db.remove_from_collection(entry_id)
    if not removed:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"success": True})


@collection_bp.route("/api/collection/<int:entry_id>", methods=["PATCH"])
def collection_update(entry_id: int):
    """Update a collection entry's listing status, asking price, notes, etc.

    Auth required – only the owning user may update their entries.

    Accepts JSON:
      listing_type – "for_trade" | "for_sale" | null (removes listing)
      asking_price – number, required when listing_type is "for_sale"
      condition    – NM / LP / MP / HP / DMG
      quantity     – positive integer
      notes        – free-form string
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}

    listing_type = data.get("listing_type", "__unset__")
    if listing_type != "__unset__" and listing_type not in _VALID_LISTING_TYPES:
        return jsonify({"error": "listing_type must be 'for_trade', 'for_sale', or null"}), 400

    asking_price = data.get("asking_price")
    if listing_type == "for_sale" and (asking_price is None or float(asking_price) <= 0):
        return jsonify({"error": "asking_price must be a positive number for 'for_sale' listings"}), 400

    # Clear asking_price when not for sale
    if listing_type != "for_sale":
        asking_price = None

    update_kwargs = {}
    if listing_type != "__unset__":
        update_kwargs["listing_type"] = listing_type
        update_kwargs["asking_price"] = asking_price
    for field in ("condition", "quantity", "notes"):
        if field in data:
            update_kwargs[field] = data[field]

    if not update_kwargs:
        return jsonify({"error": "No updatable fields provided"}), 400

    entry = db.update_collection_entry(entry_id, user_id, **update_kwargs)
    if entry is None:
        return jsonify({"error": "Entry not found or not owned by you"}), 404
    return jsonify({"data": entry})


@collection_bp.route("/api/collection/stats")
def collection_stats():
    """Return aggregate stats, scoped to the authenticated user if key provided."""
    return jsonify({"data": db.get_collection_stats(user_id=_current_user_id())})
