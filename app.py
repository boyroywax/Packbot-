"""Packbot - Pokemon TCG Card Scanner

Flask web application serving both the REST API and the frontend SPA.

Authentication
--------------
Two auth methods are supported (checked in order):

1. Session token (recommended) – obtained from ``POST /api/sessions``:
   ``Authorization: Bearer <token>``

2. Permanent API key – obtained from ``POST /api/users``:
   ``X-Api-Key: <key>``  or  ``?api_key=<key>`` query param

When a valid credential is supplied the request is scoped to that user's
collection and scan history.  Unauthenticated requests see the shared
anonymous pool.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# Keep these top-level imports so existing test mocks (e.g.
# @patch("app.tcg_api.get_card")) continue to resolve.
import database as db  # noqa: F401
import notifier  # noqa: F401
import scanner  # noqa: F401
import tcg_api  # noqa: F401

from routes.scan import scan_bp
from routes.cards import cards_bp
from routes.collection import collection_bp
from routes.users import users_bp
from routes.sessions import sessions_bp
from routes.profiles import profiles_bp
from routes.wishlist import wishlist_bp
from routes.packs import packs_bp
from routes.trades import trades_bp
from routes.messages import messages_bp

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

CORS(app, resources={r"/api/*": {"origins": "*"}})


# ---------------------------------------------------------------------------
# Initialise DB on startup
# ---------------------------------------------------------------------------

with app.app_context():
    db.init_db()


# ---------------------------------------------------------------------------
# Frontend static file serving
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


# ---------------------------------------------------------------------------
# Register blueprints
# ---------------------------------------------------------------------------

app.register_blueprint(scan_bp)
app.register_blueprint(cards_bp)
app.register_blueprint(collection_bp)
app.register_blueprint(users_bp)
app.register_blueprint(sessions_bp)
app.register_blueprint(profiles_bp)
app.register_blueprint(wishlist_bp)
app.register_blueprint(packs_bp)
app.register_blueprint(trades_bp)
app.register_blueprint(messages_bp)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
