"""Message functions for Packbot database."""

from typing import Optional

from database.connection import _exec, _is_pg, get_db


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def send_message(
    sender_id: int,
    recipient_id: int,
    body: str,
    subject: str = "",
) -> dict:
    """Insert a message and return the new row."""
    with get_db() as conn:
        _exec(
            conn,
            "INSERT INTO messages (sender_id, recipient_id, subject, body) VALUES (?,?,?,?)",
            (sender_id, recipient_id, subject or "", body),
        )
        if _is_pg():
            row = _exec(conn, "SELECT * FROM messages WHERE id = lastval()").fetchone()
        else:
            row = _exec(conn, "SELECT * FROM messages WHERE id = last_insert_rowid()").fetchone()
    return dict(row) if row else {}


def get_message(message_id: int) -> Optional[dict]:
    """Return a single message row with sender/recipient usernames, or None."""
    with get_db() as conn:
        row = _exec(
            conn,
            """
            SELECT m.*,
                   s.username AS sender_username,
                   r.username AS recipient_username
            FROM   messages m
            JOIN   users s ON s.id = m.sender_id
            JOIN   users r ON r.id = m.recipient_id
            WHERE  m.id = ?
            """,
            (message_id,),
        ).fetchone()
    return dict(row) if row else None


def get_inbox(user_id: int, limit: int = 50) -> list:
    """Return messages where *user_id* is the recipient, newest first."""
    with get_db() as conn:
        rows = _exec(
            conn,
            """
            SELECT m.*,
                   s.username AS sender_username,
                   r.username AS recipient_username
            FROM   messages m
            JOIN   users s ON s.id = m.sender_id
            JOIN   users r ON r.id = m.recipient_id
            WHERE  m.recipient_id = ?
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_unread_count(user_id: int) -> int:
    """Return the number of unread messages for *user_id*."""
    with get_db() as conn:
        row = _exec(
            conn,
            "SELECT COUNT(*) AS cnt FROM messages WHERE recipient_id = ? AND read = 0",
            (user_id,),
        ).fetchone()
    return dict(row)["cnt"] if row else 0


def mark_message_read(message_id: int) -> None:
    """Set read=1 on a message."""
    with get_db() as conn:
        _exec(conn, "UPDATE messages SET read = 1 WHERE id = ?", (message_id,))


def delete_message(message_id: int, user_id: int) -> bool:
    """Delete a message if *user_id* is the sender or recipient."""
    with get_db() as conn:
        cur = _exec(
            conn,
            "DELETE FROM messages WHERE id = ? AND (sender_id = ? OR recipient_id = ?)",
            (message_id, user_id, user_id),
        )
        return cur.rowcount > 0
