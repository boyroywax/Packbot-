"""Database layer for Packbot – supports SQLite (dev) and PostgreSQL (production).

Backend is selected automatically:
  • Set DATABASE_URL=postgresql://... to use PostgreSQL
  • Otherwise SQLite is used (DATABASE_PATH, default packbot.db)
"""

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash


DATABASE_URL: str = os.getenv("DATABASE_URL", "")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "packbot.db")


# ---------------------------------------------------------------------------
# Backend detection & helpers
# ---------------------------------------------------------------------------

def _is_pg() -> bool:
    return bool(DATABASE_URL and DATABASE_URL.startswith(("postgres://", "postgresql://")))


def _q(query: str) -> str:
    """Adapt ? placeholders to %s for PostgreSQL."""
    return query.replace("?", "%s") if _is_pg() else query


def _exec(conn, query: str, params=()):
    """Execute *query* against *conn*, adapting placeholders automatically.

    Returns a cursor whose .fetchone() / .fetchall() / .rowcount work the
    same way regardless of the underlying driver.
    """
    if _is_pg():
        cur = conn.cursor()
        cur.execute(_q(query), params)
        return cur
    return conn.execute(query, params)


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    """Yield a live database connection; commit on success, rollback on error."""
    if _is_pg():
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
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


# ---------------------------------------------------------------------------
# Schema DDL  (separate lists so we avoid SQLite-only / PG-only syntax)
# ---------------------------------------------------------------------------

_SQLITE_DDL = [
    """CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL UNIQUE,
        email         TEXT UNIQUE,
        api_key       TEXT NOT NULL UNIQUE,
        password_hash TEXT,
        created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS cards (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        set_id      TEXT NOT NULL,
        set_name    TEXT NOT NULL,
        number      TEXT NOT NULL,
        rarity      TEXT,
        image_small TEXT,
        image_large TEXT,
        data_json   TEXT,
        created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS collection (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id      TEXT NOT NULL REFERENCES cards(id),
        user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
        condition    TEXT NOT NULL DEFAULT 'NM',
        foil         INTEGER NOT NULL DEFAULT 0,
        quantity     INTEGER NOT NULL DEFAULT 1,
        notes        TEXT,
        listing_type TEXT,
        asking_price REAL,
        added_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    # Partial unique indexes so anonymous and per-user entries coexist
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_col_no_user
        ON collection(card_id, condition, foil) WHERE user_id IS NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_col_user
        ON collection(card_id, condition, foil, user_id) WHERE user_id IS NOT NULL""",
    "CREATE INDEX IF NOT EXISTS idx_collection_card_id ON collection(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_collection_user_id ON collection(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name)",
    "CREATE INDEX IF NOT EXISTS idx_cards_set_id ON cards(set_id)",
    """CREATE TABLE IF NOT EXISTS scan_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id     TEXT REFERENCES cards(id),
        user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
        method      TEXT,
        confidence  REAL,
        raw_input   TEXT,
        scanned_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token       TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at  TEXT NOT NULL,
        last_seen   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS wishlist (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        card_id     TEXT NOT NULL REFERENCES cards(id),
        notes       TEXT,
        added_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_wishlist_user_card ON wishlist(user_id, card_id)",
    "CREATE INDEX IF NOT EXISTS idx_wishlist_user_id ON wishlist(user_id)",
    """CREATE TABLE IF NOT EXISTS pack_sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
        barcode      TEXT,
        set_id       TEXT,
        set_name     TEXT,
        pack_name    TEXT,
        status       TEXT NOT NULL DEFAULT 'active',
        started_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ps_user_id ON pack_sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS pack_session_cards (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  INTEGER NOT NULL REFERENCES pack_sessions(id) ON DELETE CASCADE,
        card_id     TEXT,
        card_name   TEXT,
        number      TEXT,
        set_name    TEXT,
        image_small TEXT,
        rarity      TEXT,
        confidence  REAL,
        detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_psc_session_id ON pack_session_cards(session_id)",
]

_PG_DDL = [
    """CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE,
        email         TEXT UNIQUE,
        api_key       TEXT NOT NULL UNIQUE,
        password_hash TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS cards (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        set_id      TEXT NOT NULL,
        set_name    TEXT NOT NULL,
        number      TEXT NOT NULL,
        rarity      TEXT,
        image_small TEXT,
        image_large TEXT,
        data_json   TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS collection (
        id           SERIAL PRIMARY KEY,
        card_id      TEXT NOT NULL REFERENCES cards(id),
        user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
        condition    TEXT NOT NULL DEFAULT 'NM',
        foil         INTEGER NOT NULL DEFAULT 0,
        quantity     INTEGER NOT NULL DEFAULT 1,
        notes        TEXT,
        listing_type TEXT,
        asking_price REAL,
        added_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_col_no_user
        ON collection(card_id, condition, foil) WHERE user_id IS NULL""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_col_user
        ON collection(card_id, condition, foil, user_id) WHERE user_id IS NOT NULL""",
    "CREATE INDEX IF NOT EXISTS idx_collection_card_id ON collection(card_id)",
    "CREATE INDEX IF NOT EXISTS idx_collection_user_id ON collection(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name)",
    "CREATE INDEX IF NOT EXISTS idx_cards_set_id ON cards(set_id)",
    """CREATE TABLE IF NOT EXISTS scan_history (
        id          SERIAL PRIMARY KEY,
        card_id     TEXT REFERENCES cards(id),
        user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
        method      TEXT,
        confidence  REAL,
        raw_input   TEXT,
        scanned_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token       TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at  TIMESTAMPTZ NOT NULL,
        last_seen   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS wishlist (
        id          SERIAL PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        card_id     TEXT NOT NULL REFERENCES cards(id),
        notes       TEXT,
        added_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_wishlist_user_card ON wishlist(user_id, card_id)",
    "CREATE INDEX IF NOT EXISTS idx_wishlist_user_id ON wishlist(user_id)",
    """CREATE TABLE IF NOT EXISTS pack_sessions (
        id           SERIAL PRIMARY KEY,
        user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
        barcode      TEXT,
        set_id       TEXT,
        set_name     TEXT,
        pack_name    TEXT,
        status       TEXT NOT NULL DEFAULT 'active',
        started_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ps_user_id ON pack_sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS pack_session_cards (
        id          SERIAL PRIMARY KEY,
        session_id  INTEGER NOT NULL REFERENCES pack_sessions(id) ON DELETE CASCADE,
        card_id     TEXT REFERENCES cards(id),
        card_name   TEXT,
        number      TEXT,
        set_name    TEXT,
        image_small TEXT,
        rarity      TEXT,
        confidence  REAL,
        detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_psc_session_id ON pack_session_cards(session_id)",
]


def init_db():
    """Create all tables and indexes if they don't exist yet.

    Also runs additive migrations for columns added after the initial schema.
    """
    ddl = _PG_DDL if _is_pg() else _SQLITE_DDL
    with get_db() as conn:
        for stmt in ddl:
            _exec(conn, stmt)
        # Additive migrations – safe to run on existing installs
        for col, typ in [
            ("password_hash", "TEXT"),
            ("listing_type",  "TEXT"),
            ("asking_price",  "REAL"),
        ]:
            table = "users" if col == "password_hash" else "collection"
            try:
                _exec(conn, f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            except Exception:
                pass  # Column already exists


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(
    username: str,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> dict:
    """Create a new user and return the full row (including generated api_key).

    If *password* is provided it is bcrypt-hashed before storage.
    """
    api_key = secrets.token_urlsafe(32)
    pw_hash = generate_password_hash(password) if password else None
    with get_db() as conn:
        if _is_pg():
            cur = _exec(
                conn,
                "INSERT INTO users (username, email, api_key, password_hash) VALUES (?, ?, ?, ?) RETURNING *",
                (username, email, api_key, pw_hash),
            )
            row = cur.fetchone()
        else:
            _exec(
                conn,
                "INSERT INTO users (username, email, api_key, password_hash) VALUES (?, ?, ?, ?)",
                (username, email, api_key, pw_hash),
            )
            row = _exec(conn, "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else {}


def verify_password(username: str, password: str) -> Optional[dict]:
    """Return the user dict if *username* + *password* are valid, else None."""
    user = get_user_by_username(username)
    if not user or not user.get("password_hash"):
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def get_user(user_id: int) -> Optional[dict]:
    """Fetch a user by primary key."""
    with get_db() as conn:
        row = _exec(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[dict]:
    """Fetch a user by username."""
    with get_db() as conn:
        row = _exec(conn, "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_api_key(api_key: str) -> Optional[dict]:
    """Fetch a user by their API key."""
    with get_db() as conn:
        row = _exec(conn, "SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    return dict(row) if row else None


def delete_user(user_id: int) -> bool:
    """Delete a user (collection entries cascade-delete via FK)."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

_SESSION_DURATION_DAYS: int = int(os.getenv("SESSION_DURATION_DAYS", 30))


def _utc_str(dt: datetime) -> str:
    """Format a datetime as a UTC string that sorts correctly in SQLite."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def create_session(user_id: int, duration_days: Optional[int] = None) -> dict:
    """Create a new session for *user_id* and return the session row."""
    duration_days = duration_days if duration_days is not None else _SESSION_DURATION_DAYS
    token = secrets.token_urlsafe(32)
    expires_at = _utc_str(datetime.now(timezone.utc) + timedelta(days=duration_days))
    with get_db() as conn:
        _exec(
            conn,
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        row = _exec(conn, "SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
    return dict(row) if row else {}


def get_session(token: str) -> Optional[dict]:
    """Return the session row if the token is valid and not expired.

    Also bumps *last_seen* to the current time.
    """
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        row = _exec(
            conn,
            "SELECT * FROM sessions WHERE token = ? AND expires_at > ?",
            (token, now),
        ).fetchone()
        if row:
            _exec(
                conn,
                "UPDATE sessions SET last_seen = ? WHERE token = ?",
                (now, token),
            )
    return dict(row) if row else None


def delete_session(token: str) -> bool:
    """Invalidate a single session token (logout)."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM sessions WHERE token = ?", (token,))
        return cur.rowcount > 0


def delete_all_user_sessions(user_id: int) -> int:
    """Invalidate all sessions for *user_id*. Returns number of rows deleted."""
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return cur.rowcount


def get_user_sessions(user_id: int) -> list:
    """Return all active (non-expired) sessions for *user_id*."""
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        rows = _exec(
            conn,
            """
            SELECT token, user_id, created_at, expires_at, last_seen
            FROM sessions
            WHERE user_id = ? AND expires_at > ?
            ORDER BY last_seen DESC
            """,
            (user_id, now),
        ).fetchall()
    return [dict(r) for r in rows]


def cleanup_expired_sessions() -> int:
    """Delete all expired sessions. Returns number of rows removed."""
    now = _utc_str(datetime.now(timezone.utc))
    with get_db() as conn:
        cur = _exec(conn, "DELETE FROM sessions WHERE expires_at <= ?", (now,))
        return cur.rowcount


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
