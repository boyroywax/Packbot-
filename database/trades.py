"""Trade matching functions for Packbot database."""

from database.connection import _exec, get_db


# ---------------------------------------------------------------------------
# Trade matching
# ---------------------------------------------------------------------------

def get_trade_matches(user_id: int) -> dict:
    """Return trade opportunities for *user_id*.

    Returns a dict with two keys:

    ``you_have_they_want``
        Your ``for_trade`` listings where another user's wishlist contains the
        same card.

    ``they_have_you_want``
        Other users' ``for_trade`` listings where you have the card on your
        wishlist.
    """
    _CARD_COLS = """
        c.id AS card_id, c.name AS card_name, c.set_id, c.set_name,
        c.number, c.rarity, c.image_small
    """
    with get_db() as conn:
        yours = _exec(
            conn,
            f"""
            SELECT {_CARD_COLS},
                   col.id AS col_id, col.condition, col.asking_price, col.listing_type,
                   u.id   AS match_user_id, u.username AS match_username,
                   w.id   AS wishlist_id,  w.notes    AS wishlist_notes
            FROM   collection col
            JOIN   cards c        ON c.id      = col.card_id
            JOIN   wishlist w     ON w.card_id = col.card_id
            JOIN   users u        ON u.id      = w.user_id
            WHERE  col.user_id    = ?
              AND  col.listing_type = 'for_trade'
              AND  w.user_id       != ?
            ORDER BY c.name
            """,
            (user_id, user_id),
        ).fetchall()

        theirs = _exec(
            conn,
            f"""
            SELECT {_CARD_COLS},
                   col.id AS col_id, col.condition, col.asking_price, col.listing_type,
                   u.id   AS match_user_id, u.username AS match_username,
                   w.id   AS wishlist_id,  w.notes    AS wishlist_notes
            FROM   wishlist w
            JOIN   cards c        ON c.id      = w.card_id
            JOIN   collection col ON col.card_id = w.card_id
            JOIN   users u        ON u.id       = col.user_id
            WHERE  w.user_id      = ?
              AND  col.listing_type = 'for_trade'
              AND  col.user_id     != ?
            ORDER BY c.name
            """,
            (user_id, user_id),
        ).fetchall()

    return {
        "you_have_they_want": [dict(r) for r in yours],
        "they_have_you_want": [dict(r) for r in theirs],
    }
