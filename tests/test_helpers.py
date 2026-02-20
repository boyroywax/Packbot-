"""Shared fixtures and mixins used by multiple test modules."""

import os
import sys
import types
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies before any project import
# ---------------------------------------------------------------------------
for stub in ('cv2', 'numpy', 'imagehash'):
    if stub not in sys.modules:
        sys.modules[stub] = types.ModuleType(stub)

if 'PIL' not in sys.modules:
    pil = types.ModuleType('PIL')
    pil.Image = MagicMock()
    sys.modules['PIL'] = pil
    sys.modules['PIL.Image'] = pil.Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Shared card fixture used across tests
# ---------------------------------------------------------------------------
FAKE_CARD = {
    "id": "base1-4",
    "name": "Charizard",
    "number": "4",
    "rarity": "Rare Holo",
    "set": {"id": "base1", "name": "Base Set"},
    "images": {"small": "https://example.com/small.png", "large": "https://example.com/large.png"},
    "tcgplayer": {
        "url": "https://tcgplayer.com",
        "prices": {
            "holofoil": {"low": 200.0, "mid": 350.0, "high": 500.0, "market": 320.0}
        },
    },
    "cardmarket": {
        "url": "https://cardmarket.com",
        "prices": {"lowPrice": 180.0, "averageSellPrice": 300.0, "trendPrice": 280.0},
    },
}


# ---------------------------------------------------------------------------
# Shared setUp mixin to avoid repeating boilerplate
# ---------------------------------------------------------------------------

class _AppTestMixin:
    def setUp(self):
        self._db_fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DATABASE_PATH"] = self._db_path

        import importlib
        import database
        importlib.reload(database)

        import app as flask_app
        importlib.reload(flask_app)

        self.app = flask_app.app
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    def tearDown(self):
        os.close(self._db_fd)
        os.unlink(self._db_path)

    def _make_user(self, username, password=None):
        resp = self.client.post("/api/users",
                                json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["data"]

    @patch("app.tcg_api.get_card")
    def _add_card(self, mock_get, api_key, card_id="base1-4", **kwargs):
        mock_get.return_value = FAKE_CARD
        r = self.client.post("/api/collection",
                             json={"card_id": card_id, **kwargs},
                             headers={"X-Api-Key": api_key})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["data"]
