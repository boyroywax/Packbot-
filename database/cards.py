"""Card and collection functions for Packbot database."""

import json
from typing import Optional

from database.connection import _exec, get_db


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

def upsert_card(card_data: dict) -> str:
    """Insert or update a card record from API data. Returns card id."""
    card_id = card_data["id"]
    with get_db() as conn:
        _exec(
            conn,
            """
            INSERT INTO cards (id, name, set_id, set_name, number, rarity,
                               image_small, image_large, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name        = excluded.name,
                set_name    = excluded.set_name,
                rarity      = excluded.rarity,
                image_small = excluded.image_small,
                image_large = excluded.image_large,
                data_json   = excluded.data_json
            """,
            (
                card_id,
                card_data.get("name", ""),
                card_data.get("set", {}).get("id", ""),
                card_data.get("set", {}).get("name", ""),
                card_data.get("number", ""),
                card_data.get("rarity"),
                card_data.get("images", {}).get("small"),
                card_data.get("images", {}).get("large"),
                json.dumps(card_data),
            ),
        )
    return card_id


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def add_to_collection(
    card_id: str,
    condition: str = "NM",
    foil: bool = False,
    quantity: int = 1,
    notes: str = "",
    user_id: Optional[int] = None,
) -> dict:
    """Add or increment a card in the collection.

    When *user_id* is provided the entry is scoped to that user, otherwise it
    goes into the shared (anonymous) pool.  Returns the updated row.
    """
    with get_db() as conn:
        if user_id is None:
            _exec(
                conn,
                """
                INSERT INTO collection (card_id, condition, foil, quantity, notes, user_id)
                VALUES (?, ?, ?, ?, ?, NULL)
                ON CONFLICT(card_id, condition, foil) WHERE user_id IS NULL
                DO UPDATE SET
                    quantity = quantity + excluded.quantity,
                    notes    = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE notes END
                """,
                (card_id, condition, int(foil), quantity, notes or ""),
            )
            row = _exec(
                conn,
                "SELECT * FROM collection WHERE card_id=? AND condition=? AND foil=? AND user_id IS NULL",
                (card_id, condition, int(foil)),
            ).fetchone()
        else:
            _exec(
                conn,
                """
                INSERT INTO collection (card_id, condition, foil, quantity, notes, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id, condition, foil, user_id) WHERE user_id IS NOT NULL
                DO UPDATE SET
                    quantity = quantity + excluded.quantity,
                    notes    = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE notes END
                """,
                (card_id, condition, int(foil), quantity, notes or "", user_id),
            )
            row = _exec(
                conn,
                "SELECT * FROM collection WHERE card_id=? AND condition=? AND foil=? AND user_id=?",
                (card_id, condition, int(foil), user_id),
            ).fetchone()
    return dict(row) if row else {}


def get_collection(
    search: str = "",
    set_id: str = "",
    user_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Fetch collection with optional filtering and pagination.

    When *user_id* is provided the results are scoped to that user.
    When omitted (anonymous request) only the shared pool (user_id IS NULL) is returned.
    """
    offset = (page - 1) * page_size
    filters: list = []
    params: list = []

    if search:
        filters.append("c.name LIKE ?")
        params.append(f"%{search}%")
    if set_id:
        filters.append("c.set_id = ?")
        params.append(set_id)
    if user_id is not None:
        filters.append("col.user_id = ?")
        params.append(user_id)
    else:
        filters.append("col.user_id IS NULL")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_db() as conn:
        total_row = _exec(
            conn,
            f"SELECT COUNT(*) AS cnt FROM collection col JOIN cards c ON c.id=col.card_id {where}",
            params,
        ).fetchone()
        total = (total_row["cnt"] if isinstance(total_row, dict) else total_row[0]) if total_row else 0

        rows = _exec(
            conn,
            f"""
            SELECT col.id, col.card_id, col.user_id, col.condition, col.foil, col.quantity,
                   col.notes, col.added_at,
                   c.name, c.set_id, c.set_name, c.number, c.rarity,
                   c.image_small, c.image_large
            FROM collection col
            JOIN cards c ON c.id = col.card_id
            {where}
            ORDER BY col.added_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


def remove_from_collection(collection_id: int) -> bool:
    """Remove a collection entry by its row id."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM collection WHERE id=?", (collection_id,))
        return cur.rowcount > 0


def get_collection_stats(user_id: Optional[int] = None) -> dict:
    """Return aggregate stats scoped to *user_id*, or to the anonymous pool when omitted."""
    where = "WHERE col.user_id = ?" if user_id is not None else "WHERE col.user_id IS NULL"
    params = (user_id,) if user_id is not None else ()
    with get_db() as conn:
        row = _exec(
            conn,
            f"""
            SELECT
                COUNT(DISTINCT col.card_id)    AS unique_cards,
                COALESCE(SUM(col.quantity), 0) AS total_cards,
                COUNT(DISTINCT c.set_id)       AS unique_sets
            FROM collection col
            JOIN cards c ON c.id = col.card_id
            {where}
            """,
            params,
        ).fetchone()
    return dict(row) if row else {"unique_cards": 0, "total_cards": 0, "unique_sets": 0}


def update_collection_entry(entry_id: int, user_id: int, **kwargs) -> Optional[dict]:
    """Update allowed fields of a collection entry owned by *user_id*.

    Accepted keyword arguments: listing_type, asking_price, notes, condition, quantity.
    Returns the updated row dict, or None if the entry doesn't exist / isn't owned by user_id.
    """
    _UPDATABLE = {"listing_type", "asking_price", "notes", "condition", "quantity"}
    updates = {k: v for k, v in kwargs.items() if k in _UPDATABLE}
    if not updates:
        return None
    # Column names are validated against _UPDATABLE so f-string interpolation is safe
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [entry_id, user_id]
    with get_db() as conn:
        cur = _exec(
            conn,
            f"UPDATE collection SET {set_clause} WHERE id = ? AND user_id = ?",
            values,
        )
        if cur.rowcount == 0:
            return None
        row = _exec(
            conn,
            "SELECT * FROM collection WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()
    return dict(row) if row else None
