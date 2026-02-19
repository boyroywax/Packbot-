"""Packbot - Pokemon TCG Card Scanner

Flask web application serving both the REST API and the frontend SPA.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import database as db
import scanner
import tcg_api

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

CORS(app, resources={r"/api/*": {"origins": "*"}})


# ---------------------------------------------------------------------------
# Initialise DB on startup
# ---------------------------------------------------------------------------

with app.app_context():
    db.init_db()


# ---------------------------------------------------------------------------
# Frontend static file serving
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ---------------------------------------------------------------------------
# Card scan endpoints
# ---------------------------------------------------------------------------

@app.route("/api/scan/image", methods=["POST"])
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
        )

    return jsonify(result)


@app.route("/api/scan/text", methods=["POST"])
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
        )

    return jsonify(result)


# ---------------------------------------------------------------------------
# Card search / lookup endpoints
# ---------------------------------------------------------------------------

@app.route("/api/cards/search")
def cards_search():
    """Search the TCG API.

    Query params:
      q        – raw TCG API query string
      name     – search by Pokémon name (alias)
      page     – page number (default 1)
      page_size – results per page (default 20, max 250)
    """
    q = request.args.get("q", "")
    name = request.args.get("name", "")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 20)), 250)

    if not q and name:
        q = f'name:"{name}"'
    if not q:
        return jsonify({"error": "q or name parameter required"}), 400

    result = tcg_api.search_cards(q, page=page, page_size=page_size)
    return jsonify(result)


@app.route("/api/cards/<card_id>")
def card_detail(card_id: str):
    """Fetch a single card by ID."""
    card = tcg_api.get_card(card_id)
    if not card:
        return jsonify({"error": "Card not found"}), 404
    return jsonify({"data": card})


@app.route("/api/cards/<card_id>/price")
def card_price(card_id: str):
    """Fetch market price data for a card."""
    prices = tcg_api.get_card_price(card_id)
    if prices is None:
        return jsonify({"error": "Card not found or no pricing data"}), 404
    return jsonify({"data": prices})


@app.route("/api/sets")
def sets_list():
    """Return list of all TCG sets."""
    result = tcg_api.get_sets()
    return jsonify(result)


# ---------------------------------------------------------------------------
# Collection endpoints
# ---------------------------------------------------------------------------

@app.route("/api/collection", methods=["GET"])
def collection_list():
    """Get the user's collection with optional filtering.

    Query params: search, set_id, page, page_size
    """
    search = request.args.get("search", "")
    set_id = request.args.get("set_id", "")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)

    result = db.get_collection(search=search, set_id=set_id, page=page, page_size=page_size)
    return jsonify(result)


@app.route("/api/collection", methods=["POST"])
def collection_add():
    """Add a card to the collection.

    Expects JSON body:
      card_id   – required
      condition – NM / LP / MP / HP / DMG (default NM)
      foil      – boolean (default false)
      quantity  – integer (default 1)
      notes     – optional string
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
    )
    return jsonify({"data": entry}), 201


@app.route("/api/collection/<int:entry_id>", methods=["DELETE"])
def collection_remove(entry_id: int):
    """Remove a collection entry by its row ID."""
    removed = db.remove_from_collection(entry_id)
    if not removed:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"success": True})


@app.route("/api/collection/stats")
def collection_stats():
    """Return aggregate stats for the collection."""
    return jsonify({"data": db.get_collection_stats()})


# ---------------------------------------------------------------------------
# Scan history
# ---------------------------------------------------------------------------

@app.route("/api/scans")
def scan_history():
    """Return recent scan history."""
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"data": db.get_scan_history(limit=limit)})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
