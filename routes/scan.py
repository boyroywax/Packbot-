"""Card scan endpoints."""

from flask import Blueprint, jsonify, request

import database as db
import scanner
from routes.auth import _current_user_id

scan_bp = Blueprint("scan", __name__)


@scan_bp.route("/api/scan/image", methods=["POST"])
def scan_image():
    """Identify a card from a captured image.

    Expects JSON body:
      image       – base64 data URL from <canvas>
      pokemon_name – optional Pokémon name hint
      set_code    – optional set code hint (e.g. 'SVI', 'base1')
      card_number – optional collector number hint
    """
    data = request.get_json(force=True, silent=True) or {}
    image_data = data.get("image", "")
    pokemon_name = data.get("pokemon_name", "")
    set_code = data.get("set_code", "")
    card_number = data.get("card_number", "")

    result = scanner.scan_from_image(
        data_url=image_data,
        pokemon_name=pokemon_name,
        set_code=set_code,
        card_number=card_number,
    )

    card = result.get("card")
    if card:
        db.upsert_card(card)
        db.log_scan(
            card_id=card["id"],
            method=result["method"],
            confidence=result["confidence"],
            raw_input=f"name={pokemon_name} set={set_code} num={card_number}",
            user_id=_current_user_id(),
        )

    return jsonify(result)


@scan_bp.route("/api/scan/text", methods=["POST"])
def scan_text():
    """Identify a card from free-form text.

    Expects JSON body: { "text": "Charizard base1/4" }
    """
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text field is required"}), 400

    result = scanner.scan_from_text(text)
    card = result.get("card")
    if card:
        db.upsert_card(card)
        db.log_scan(
            card_id=card["id"],
            method=result["method"],
            confidence=result["confidence"],
            raw_input=text,
            user_id=_current_user_id(),
        )

    return jsonify(result)


@scan_bp.route("/api/scans")
def scan_history():
    """Return recent scan history, scoped to authenticated user if key provided."""
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"data": db.get_scan_history(limit=limit, user_id=_current_user_id())})
