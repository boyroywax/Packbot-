"""Public profile routes (no auth required)."""

from flask import Blueprint, jsonify, request, send_from_directory

import database as db

profiles_bp = Blueprint("profiles", __name__)


@profiles_bp.route("/u/<username>")
def public_profile_page(username: str):
    """Serve the public profile SPA page."""
    return send_from_directory("static", "profile.html")


@profiles_bp.route("/api/users/<username>/profile")
def users_public_profile(username: str):
    """Return the public profile summary for *username*."""
    profile = db.get_public_profile(username)
    if not profile:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"data": profile})


@profiles_bp.route("/api/users/<username>/collection")
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


@profiles_bp.route("/api/users/<username>/listings")
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


@profiles_bp.route("/api/users/<username>/wishlist")
def users_public_wishlist(username: str):
    """Return the public wishlist for *username*."""
    if not db.get_public_profile(username):
        return jsonify({"error": "User not found"}), 404
    return jsonify({"data": db.get_public_wishlist(username)})
