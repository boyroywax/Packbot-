"""Public profile functions for Packbot database."""

from typing import Optional

from database.connection import _exec, get_db


# ---------------------------------------------------------------------------
# Public profiles
# ---------------------------------------------------------------------------

def get_public_profile(username: str) -> Optional[dict]:
    """Return a public summary for *username*, or None if not found."""
    with get_db() as conn:
        urow = _exec(
            conn,
            "SELECT id, username, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not urow:
            return None
        uid = dict(urow)["id"]
        srow = _exec(
            conn,
            """
            SELECT
                COUNT(*)                                                     AS collection_count,
                COALESCE(SUM(quantity), 0)                                   AS total_cards,
                SUM(CASE WHEN listing_type IS NOT NULL THEN 1 ELSE 0 END)    AS listing_count
            FROM collection
            WHERE user_id = ?
            """,
            (uid,),
        ).fetchone()
        wrow = _exec(
            conn,
            "SELECT COUNT(*) AS wishlist_count FROM wishlist WHERE user_id = ?",
            (uid,),
        ).fetchone()
    profile = dict(urow)
    profile.update(
        dict(srow) if srow else {"collection_count": 0, "total_cards": 0, "listing_count": 0}
    )
    profile.update(dict(wrow) if wrow else {"wishlist_count": 0})
    return profile


def get_public_collection(
    username: str,
    listing_type: Optional[str] = None,
    only_listed: bool = False,
    search: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Return a paginated, public view of *username*'s collection.

    Pass *listing_type* ('for_trade' | 'for_sale') to narrow to a specific
    listing kind.  Pass *only_listed=True* to show all listed entries regardless
    of type (for_trade OR for_sale).
    """
    offset = (page - 1) * page_size
    filters = ["u.username = ?", "col.user_id IS NOT NULL"]
    params: list = [username]

    if listing_type:
        filters.append("col.listing_type = ?")
        params.append(listing_type)
    elif only_listed:
        filters.append("col.listing_type IS NOT NULL")
    if search:
        filters.append("c.name LIKE ?")
        params.append(f"%{search}%")

    where = "WHERE " + " AND ".join(filters)

    with get_db() as conn:
        total_row = _exec(
            conn,
            f"""
            SELECT COUNT(*) AS cnt
            FROM collection col
            JOIN cards c ON c.id = col.card_id
            JOIN users u ON u.id = col.user_id
            {where}
            """,
            params,
        ).fetchone()
        total = dict(total_row)["cnt"] if total_row else 0

        rows = _exec(
            conn,
            f"""
            SELECT col.id, col.card_id, col.condition, col.foil, col.quantity,
                   col.notes, col.added_at, col.listing_type, col.asking_price,
                   c.name, c.set_id, c.set_name, c.number, c.rarity,
                   c.image_small, c.image_large
            FROM collection col
            JOIN cards c ON c.id = col.card_id
            JOIN users u ON u.id = col.user_id
            {where}
            ORDER BY col.added_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    return {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}
