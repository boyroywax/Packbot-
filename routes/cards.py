"""Card search / lookup endpoints."""

from flask import Blueprint, jsonify, request

import tcg_api

cards_bp = Blueprint("cards", __name__)


@cards_bp.route("/api/cards/search")
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


@cards_bp.route("/api/cards/<card_id>")
def card_detail(card_id: str):
    """Fetch a single card by ID."""
    card = tcg_api.get_card(card_id)
    if not card:
        return jsonify({"error": "Card not found"}), 404
    return jsonify({"data": card})


@cards_bp.route("/api/cards/<card_id>/price")
def card_price(card_id: str):
    """Fetch market price data for a card."""
    prices = tcg_api.get_card_price(card_id)
    if prices is None:
        return jsonify({"error": "Card not found or no pricing data"}), 404
    return jsonify({"data": prices})


@cards_bp.route("/api/sets")
def sets_list():
    """Return list of all TCG sets."""
    result = tcg_api.get_sets()
    return jsonify(result)
