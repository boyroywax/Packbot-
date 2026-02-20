"""Packbot - Pokemon TCG Card Scanner

Flask web application serving both the REST API and the frontend SPA.

Authentication
--------------
Two auth methods are supported (checked in order):

1. Session token (recommended) – obtained from ``POST /api/sessions``:
   ``Authorization: Bearer <token>``

2. Permanent API key – obtained from ``POST /api/users``:
   ``X-Api-Key: <key>``  or  ``?api_key=<key>`` query param

When a valid credential is supplied the request is scoped to that user's
collection and scan history.  Unauthenticated requests see the shared
anonymous pool.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from typing import Optional

import database as db
import scanner
import tcg_api

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

CORS(app, resources={r"/api/*": {"origins": "*"}})


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

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
            user_id=_current_user_id(),
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
            user_id=_current_user_id(),
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


@app.route("/api/collection", methods=["POST"])
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


@app.route("/api/collection/<int:entry_id>", methods=["DELETE"])
def collection_remove(entry_id: int):
    """Remove a collection entry by its row ID."""
    removed = db.remove_from_collection(entry_id)
    if not removed:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"success": True})


@app.route("/api/collection/stats")
def collection_stats():
    """Return aggregate stats, scoped to the authenticated user if key provided."""
    return jsonify({"data": db.get_collection_stats(user_id=_current_user_id())})


# ---------------------------------------------------------------------------
# Scan history
# ---------------------------------------------------------------------------

@app.route("/api/scans")
def scan_history():
    """Return recent scan history, scoped to authenticated user if key provided."""
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"data": db.get_scan_history(limit=limit, user_id=_current_user_id())})


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.route("/api/users", methods=["POST"])
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


@app.route("/api/users/<int:user_id>", methods=["GET"])
def users_get(user_id: int):
    """Fetch a user profile by ID."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.pop("api_key", None)
    user.pop("password_hash", None)
    return jsonify({"data": user})


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def users_delete(user_id: int):
    """Delete a user and cascade-delete their collection and scan history."""
    removed = db.delete_user(user_id)
    if not removed:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Sessions  (login / logout / introspection)
# ---------------------------------------------------------------------------

@app.route("/api/sessions", methods=["POST"])
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


@app.route("/api/sessions/me", methods=["GET"])
def sessions_me():
    """Return the authenticated user's public profile.

    Works with both Bearer session tokens and X-Api-Key.
    Returns 401 if not authenticated.
    """
    user = _resolve_auth()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": user})


@app.route("/api/sessions", methods=["GET"])
def sessions_list():
    """List all active sessions for the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": db.get_user_sessions(user_id)})


@app.route("/api/sessions", methods=["DELETE"])
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


@app.route("/api/sessions/all", methods=["DELETE"])
def sessions_logout_all():
    """Invalidate every active session for the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    count = db.delete_all_user_sessions(user_id)
    return jsonify({"success": True, "sessions_revoked": count})


# ---------------------------------------------------------------------------
# Collection listing management  (PATCH /api/collection/<id>)
# ---------------------------------------------------------------------------

_VALID_LISTING_TYPES = {"for_trade", "for_sale", None}


@app.route("/api/collection/<int:entry_id>", methods=["PATCH"])
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


# ---------------------------------------------------------------------------
# Public profile routes  (no auth required)
# ---------------------------------------------------------------------------

@app.route("/u/<username>")
def public_profile_page(username: str):
    """Serve the public profile SPA page."""
    return send_from_directory("static", "profile.html")


@app.route("/api/users/<username>/profile")
def users_public_profile(username: str):
    """Return the public profile summary for *username*."""
    profile = db.get_public_profile(username)
    if not profile:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"data": profile})


@app.route("/api/users/<username>/collection")
def users_public_collection(username: str):
    """Return a user's full public collection (paginated).

    Query params: search, page, page_size
    """
    if not db.get_public_profile(username):
        return jsonify({"error": "User not found"}), 404
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)
    result = db.get_public_collection(
        username=username,
        search=request.args.get("search", ""),
        page=page,
        page_size=page_size,
    )
    return jsonify(result)


@app.route("/api/users/<username>/listings")
def users_public_listings(username: str):
    """Return all for_trade and for_sale entries for *username*.

    Query params: type (for_trade | for_sale), page, page_size
    Omit *type* to return all listings regardless of kind.
    """
    if not db.get_public_profile(username):
        return jsonify({"error": "User not found"}), 404
    listing_type = request.args.get("type") or None
    if listing_type and listing_type not in ("for_trade", "for_sale"):
        return jsonify({"error": "type must be 'for_trade' or 'for_sale'"}), 400
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)
    result = db.get_public_collection(
        username=username,
        listing_type=listing_type,
        only_listed=(listing_type is None),  # no type → show all listings
        page=page,
        page_size=page_size,
    )
    return jsonify(result)


@app.route("/api/users/<username>/wishlist")
def users_public_wishlist(username: str):
    """Return the public wishlist for *username*."""
    if not db.get_public_profile(username):
        return jsonify({"error": "User not found"}), 404
    return jsonify({"data": db.get_public_wishlist(username)})


# ---------------------------------------------------------------------------
# Wishlist  (auth required)
# ---------------------------------------------------------------------------

@app.route("/api/wishlist", methods=["GET"])
def wishlist_list():
    """Return the authenticated user's wishlist."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": db.get_wishlist(user_id)})


@app.route("/api/wishlist", methods=["POST"])
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


@app.route("/api/wishlist/<int:wishlist_id>", methods=["DELETE"])
def wishlist_remove(wishlist_id: int):
    """Remove a wishlist entry owned by the authenticated user."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    if not db.remove_from_wishlist(wishlist_id, user_id):
        return jsonify({"error": "Wishlist entry not found"}), 404
    return jsonify({"success": True})


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
