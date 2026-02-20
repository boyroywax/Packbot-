"""Trade matching endpoint."""

from flask import Blueprint, jsonify

import database as db
from routes.auth import _current_user_id

trades_bp = Blueprint("trades", __name__)


@trades_bp.route("/api/trade-matches", methods=["GET"])
def trade_matches():
    """Return trade opportunities for the authenticated user.

    Requires authentication.  Returns:
      you_have_they_want – your for_trade listings that others have wishlisted
      they_have_you_want – others' for_trade listings for cards on your wishlist
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"data": db.get_trade_matches(user_id)})
