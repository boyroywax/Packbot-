"""Pack opening session functions for Packbot database."""

from datetime import datetime, timezone
from typing import Optional

from database.connection import _exec, _is_pg, get_db
from database.sessions import _utc_str


# ---------------------------------------------------------------------------
# Pack opening sessions
# ---------------------------------------------------------------------------

def create_pack_session(
    user_id: Optional[int] = None,
    barcode: Optional[str] = None,
    set_id: Optional[str] = None,
    set_name: Optional[str] = None,
    pack_name: Optional[str] = None,
) -> dict:
    """Create a new pack opening session and return the row."""
    with get_db() as conn:
        _exec(
            conn,
            """
            INSERT INTO pack_sessions (user_id, barcode, set_id, set_name, pack_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, barcode, set_id, set_name, pack_name),
        )
        if _is_pg():
            row = _exec(conn, "SELECT * FROM pack_sessions WHERE id = lastval()").fetchone()
        else:
            row = _exec(conn, "SELECT * FROM pack_sessions WHERE id = last_insert_rowid()").fetchone()
    return dict(row) if row else {}


def get_pack_session(session_id: int) -> Optional[dict]:
    """Return a pack session row by id, or None."""
    with get_db() as conn:
        row = _exec(
            conn,
            "SELECT * FROM pack_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def get_user_pack_sessions(user_id: int, limit: int = 20) -> list:
    """Return recent pack sessions for *user_id*, newest first, with card counts."""
    with get_db() as conn:
        rows = _exec(
            conn,
            """
            SELECT ps.*,
                   COUNT(psc.id) AS card_count
            FROM pack_sessions ps
            LEFT JOIN pack_session_cards psc ON psc.session_id = ps.id
            WHERE ps.user_id = ?
            GROUP BY ps.id
            ORDER BY ps.started_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_card_to_session(
    session_id: int,
    card_id: str,
    card_name: str = "",
    number: str = "",
    set_name: str = "",
    image_small: str = "",
    rarity: str = "",
    confidence: float = 1.0,
) -> dict:
    """Append a card to a pack session and return the inserted row."""
    with get_db() as conn:
        _exec(
            conn,
            """
            INSERT INTO pack_session_cards
                (session_id, card_id, card_name, number, set_name, image_small, rarity, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, card_id, card_name, number, set_name, image_small, rarity, confidence),
        )
        if _is_pg():
            row = _exec(conn, "SELECT * FROM pack_session_cards WHERE id = lastval()").fetchone()
        else:
            row = _exec(
                conn,
                "SELECT * FROM pack_session_cards WHERE id = last_insert_rowid()",
            ).fetchone()
    return dict(row) if row else {}


def remove_card_from_session(session_card_id: int, session_id: int) -> bool:
    """Remove a single card entry from a session. Returns True if deleted."""
    with get_db() as conn:
        cur = _exec(
            conn,
            "DELETE FROM pack_session_cards WHERE id = ? AND session_id = ?",
            (session_card_id, session_id),
        )
        return cur.rowcount > 0


def get_session_cards(session_id: int) -> list:
    """Return all cards in a pack session, oldest-first."""
    with get_db() as conn:
        rows = _exec(
            conn,
            """
            SELECT * FROM pack_session_cards
            WHERE session_id = ?
            ORDER BY detected_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def complete_pack_session(session_id: int) -> None:
    """Mark a pack session as completed with the current timestamp."""
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        _exec(
            conn,
            "UPDATE pack_sessions SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, session_id),
        )


def cancel_pack_session(session_id: int) -> None:
    """Delete a pack session (cascades to pack_session_cards)."""
    with get_db() as conn:
        _exec(conn, "DELETE FROM pack_sessions WHERE id = ?", (session_id,))
