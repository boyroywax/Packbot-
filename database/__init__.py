"""Database layer for Packbot – supports SQLite (dev) and PostgreSQL (production).

Backend is selected automatically:
  • Set DATABASE_URL=postgresql://... to use PostgreSQL
  • Otherwise SQLite is used (DATABASE_PATH, default packbot.db)
"""

# Connection & helpers
from database.connection import (
    DATABASE_PATH,
    DATABASE_URL,
    _exec,
    _is_pg,
    _q,
    get_db,
)

# Schema
from database.schema import (
    _PG_DDL,
    _SQLITE_DDL,
    init_db,
)

# Users
from database.users import (
    create_user,
    delete_user,
    get_user,
    get_user_by_api_key,
    get_user_by_username,
    verify_password,
)

# Sessions
from database.sessions import (
    _utc_str,
    cleanup_expired_sessions,
    create_session,
    delete_all_user_sessions,
    delete_session,
    get_session,
    get_user_sessions,
)

# Cards & Collection
from database.cards import (
    add_to_collection,
    get_collection,
    get_collection_stats,
    remove_from_collection,
    update_collection_entry,
    upsert_card,
)

# Public profiles
from database.profiles import (
    get_public_collection,
    get_public_profile,
)

# Wishlist
from database.wishlist import (
    _wishlist_rows,
    add_to_wishlist,
    get_public_wishlist,
    get_wishlist,
    remove_from_wishlist,
)

# Pack sessions
from database.packs import (
    add_card_to_session,
    cancel_pack_session,
    complete_pack_session,
    create_pack_session,
    get_pack_session,
    get_session_cards,
    get_user_pack_sessions,
    remove_card_from_session,
)

# Scan history
from database.scans import (
    get_scan_history,
    log_scan,
)

# Trade matching
from database.trades import (
    get_trade_matches,
)

# Messages
from database.messages import (
    delete_message,
    get_inbox,
    get_message,
    get_unread_count,
    mark_message_read,
    send_message,
)

__all__ = [
    # connection
    "DATABASE_URL",
    "DATABASE_PATH",
    "_is_pg",
    "_q",
    "_exec",
    "get_db",
    # schema
    "_SQLITE_DDL",
    "_PG_DDL",
    "init_db",
    # users
    "create_user",
    "verify_password",
    "get_user",
    "get_user_by_username",
    "get_user_by_api_key",
    "delete_user",
    # sessions
    "_utc_str",
    "create_session",
    "get_session",
    "delete_session",
    "delete_all_user_sessions",
    "get_user_sessions",
    "cleanup_expired_sessions",
    # cards & collection
    "upsert_card",
    "add_to_collection",
    "get_collection",
    "remove_from_collection",
    "get_collection_stats",
    "update_collection_entry",
    # profiles
    "get_public_profile",
    "get_public_collection",
    # wishlist
    "add_to_wishlist",
    "remove_from_wishlist",
    "_wishlist_rows",
    "get_wishlist",
    "get_public_wishlist",
    # packs
    "create_pack_session",
    "get_pack_session",
    "get_user_pack_sessions",
    "add_card_to_session",
    "remove_card_from_session",
    "get_session_cards",
    "complete_pack_session",
    "cancel_pack_session",
    # scans
    "log_scan",
    "get_scan_history",
    # trades
    "get_trade_matches",
    # messages
    "send_message",
    "get_message",
    "get_inbox",
    "get_unread_count",
    "mark_message_read",
    "delete_message",
]
