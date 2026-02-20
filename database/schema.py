"""Schema DDL and initialisation for Packbot database."""

from database.connection import _exec, _is_pg, get_db


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
    """CREATE TABLE IF NOT EXISTS messages (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        subject      TEXT NOT NULL DEFAULT '',
        body         TEXT NOT NULL,
        read         INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_sender    ON messages(sender_id)",
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
    """CREATE TABLE IF NOT EXISTS messages (
        id           SERIAL PRIMARY KEY,
        sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        subject      TEXT NOT NULL DEFAULT '',
        body         TEXT NOT NULL,
        read         INTEGER NOT NULL DEFAULT 0,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_sender    ON messages(sender_id)",
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
