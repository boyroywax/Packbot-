"""Scan history functions for Packbot database."""

from typing import Optional

from database.connection import _exec, get_db


# ---------------------------------------------------------------------------
# Scan history
# ---------------------------------------------------------------------------

def log_scan(
    card_id: Optional[str],
    method: str,
    confidence: float = 0.0,
    raw_input: str = "",
    user_id: Optional[int] = None,
):
    """Log a scan event to history."""
    with get_db() as conn:
        _exec(
            conn,
            "INSERT INTO scan_history (card_id, method, confidence, raw_input, user_id) VALUES (?,?,?,?,?)",
            (card_id, method, confidence, raw_input, user_id),
        )


def get_scan_history(limit: int = 50, user_id: Optional[int] = None) -> list:
    """Return recent scan history scoped to *user_id*, or the anonymous pool when omitted."""
    where = "WHERE sh.user_id = ?" if user_id is not None else "WHERE sh.user_id IS NULL"
    params: tuple = (user_id, limit) if user_id is not None else (limit,)
    with get_db() as conn:
        rows = _exec(
            conn,
            f"""
            SELECT sh.id, sh.card_id, sh.user_id, sh.method, sh.confidence, sh.scanned_at,
                   c.name, c.set_name, c.number, c.image_small
            FROM scan_history sh
            LEFT JOIN cards c ON c.id = sh.card_id
            {where}
            ORDER BY sh.scanned_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]
