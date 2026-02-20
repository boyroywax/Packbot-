"""Wishlist functions for Packbot database."""

from database.connection import _exec, get_db


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------

def add_to_wishlist(user_id: int, card_id: str, notes: str = "") -> dict:
    """Add *card_id* to the wishlist for *user_id*.

    If the card is already on the list the notes field is updated (upsert).
    """
    with get_db() as conn:
        _exec(
            conn,
            """
            INSERT INTO wishlist (user_id, card_id, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, card_id) DO UPDATE SET notes = excluded.notes
            """,
            (user_id, card_id, notes or ""),
        )
        row = _exec(
            conn,
            "SELECT * FROM wishlist WHERE user_id = ? AND card_id = ?",
            (user_id, card_id),
        ).fetchone()
    return dict(row) if row else {}


def remove_from_wishlist(wishlist_id: int, user_id: int) -> bool:
    """Delete a wishlist entry owned by *user_id*."""
    with get_db() as conn:
        cur = _exec(
            conn,
            "DELETE FROM wishlist WHERE id = ? AND user_id = ?",
            (wishlist_id, user_id),
        )
        return cur.rowcount > 0


def _wishlist_rows(conn, where: str, params) -> list:
    rows = _exec(
        conn,
        f"""
        SELECT w.id, w.card_id, w.notes, w.added_at,
               c.name, c.set_id, c.set_name, c.number, c.rarity,
               c.image_small, c.image_large
        FROM wishlist w
        JOIN cards c ON c.id = w.card_id
        {where}
        ORDER BY w.added_at DESC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_wishlist(user_id: int) -> list:
    """Return all wishlist items for *user_id*."""
    with get_db() as conn:
        return _wishlist_rows(conn, "WHERE w.user_id = ?", (user_id,))


def get_public_wishlist(username: str) -> list:
    """Return wishlist items for a user identified by *username*."""
    with get_db() as conn:
        return _wishlist_rows(
            conn,
            "JOIN users u ON u.id = w.user_id WHERE u.username = ?",
            (username,),
        )
