"""SQLite database layer for Packbot collection management."""

import os
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional


DATABASE_PATH = os.getenv("DATABASE_PATH", "packbot.db")


@contextmanager
def get_db():
    """Context manager that yields a database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create database schema if it doesn't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cards (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                set_id      TEXT NOT NULL,
                set_name    TEXT NOT NULL,
                number      TEXT NOT NULL,
                rarity      TEXT,
                image_small TEXT,
                image_large TEXT,
                data_json   TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS collection (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id     TEXT NOT NULL REFERENCES cards(id),
                condition   TEXT NOT NULL DEFAULT 'NM',
                foil        INTEGER NOT NULL DEFAULT 0,
                quantity    INTEGER NOT NULL DEFAULT 1,
                notes       TEXT,
                added_at    TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(card_id, condition, foil)
            );

            CREATE INDEX IF NOT EXISTS idx_collection_card_id ON collection(card_id);
            CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
            CREATE INDEX IF NOT EXISTS idx_cards_set_id ON cards(set_id);

            CREATE TABLE IF NOT EXISTS scan_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id     TEXT REFERENCES cards(id),
                method      TEXT,
                confidence  REAL,
                raw_input   TEXT,
                scanned_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)


def upsert_card(card_data: dict) -> str:
    """Insert or update a card record from API data. Returns card id."""
    card_id = card_data["id"]
    with get_db() as conn:
        conn.execute(
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


def add_to_collection(
    card_id: str,
    condition: str = "NM",
    foil: bool = False,
    quantity: int = 1,
    notes: str = "",
) -> dict:
    """Add or increment a card in the collection.

    Returns the collection row as a dict.
    """
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO collection (card_id, condition, foil, quantity, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(card_id, condition, foil) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                notes    = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE notes END
            """,
            (card_id, condition, int(foil), quantity, notes or ""),
        )
        row = conn.execute(
            "SELECT * FROM collection WHERE card_id=? AND condition=? AND foil=?",
            (card_id, condition, int(foil)),
        ).fetchone()
    return dict(row) if row else {}


def get_collection(
    search: str = "",
    set_id: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Fetch collection with optional filtering and pagination."""
    offset = (page - 1) * page_size
    filters = []
    params: list = []

    if search:
        filters.append("c.name LIKE ?")
        params.append(f"%{search}%")
    if set_id:
        filters.append("c.set_id = ?")
        params.append(set_id)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM collection col JOIN cards c ON c.id=col.card_id {where}",
            params,
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT col.id, col.card_id, col.condition, col.foil, col.quantity,
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
        cursor = conn.execute(
            "DELETE FROM collection WHERE id=?", (collection_id,)
        )
    return cursor.rowcount > 0


def get_collection_stats() -> dict:
    """Return aggregate stats for the collection."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT col.card_id)        AS unique_cards,
                COALESCE(SUM(col.quantity), 0)     AS total_cards,
                COUNT(DISTINCT c.set_id)           AS unique_sets
            FROM collection col
            JOIN cards c ON c.id = col.card_id
            """
        ).fetchone()
    return dict(row) if row else {"unique_cards": 0, "total_cards": 0, "unique_sets": 0}


def log_scan(
    card_id: Optional[str],
    method: str,
    confidence: float = 0.0,
    raw_input: str = "",
):
    """Log a scan event to history."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO scan_history (card_id, method, confidence, raw_input) VALUES (?,?,?,?)",
            (card_id, method, confidence, raw_input),
        )


def get_scan_history(limit: int = 50) -> list:
    """Return recent scan history."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT sh.id, sh.card_id, sh.method, sh.confidence, sh.scanned_at,
                   c.name, c.set_name, c.number, c.image_small
            FROM scan_history sh
            LEFT JOIN cards c ON c.id = sh.card_id
            ORDER BY sh.scanned_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
