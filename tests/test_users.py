"""Tests for /api/users endpoints and user-scoped collection/scan behaviour."""

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

from tests.test_helpers import FAKE_CARD


class TestUserRoutes(unittest.TestCase):
    """Tests for /api/users endpoints and user-scoped collection/scan behaviour."""

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

    # ------------------------------------------------------------------
    # POST /api/users
    # ------------------------------------------------------------------

    def test_create_user_success(self):
        resp = self.client.post("/api/users", json={"username": "ash", "email": "ash@pallet.town"})
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertEqual(data["username"], "ash")
        self.assertEqual(data["email"], "ash@pallet.town")
        self.assertIn("api_key", data)
        self.assertGreater(len(data["api_key"]), 20)

    def test_create_user_missing_username_returns_400(self):
        resp = self.client.post("/api/users", json={})
        self.assertEqual(resp.status_code, 400)

    def test_create_user_blank_username_returns_400(self):
        resp = self.client.post("/api/users", json={"username": "  "})
        self.assertEqual(resp.status_code, 400)

    def test_create_user_duplicate_username_returns_409(self):
        self.client.post("/api/users", json={"username": "misty"})
        resp = self.client.post("/api/users", json={"username": "misty"})
        self.assertEqual(resp.status_code, 409)

    def test_create_user_without_email(self):
        resp = self.client.post("/api/users", json={"username": "brock"})
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.get_json()["data"]["email"])

    # ------------------------------------------------------------------
    # GET /api/users/<id>
    # ------------------------------------------------------------------

    def test_get_user_found(self):
        created = self.client.post("/api/users", json={"username": "gary"}).get_json()["data"]
        resp = self.client.get(f"/api/users/{created['id']}")
        self.assertEqual(resp.status_code, 200)
        profile = resp.get_json()["data"]
        self.assertEqual(profile["username"], "gary")
        # api_key must not be exposed on GET
        self.assertNotIn("api_key", profile)

    def test_get_user_not_found_returns_404(self):
        resp = self.client.get("/api/users/99999")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # DELETE /api/users/<id>
    # ------------------------------------------------------------------

    def test_delete_user_success(self):
        created = self.client.post("/api/users", json={"username": "giovanni"}).get_json()["data"]
        resp = self.client.delete(f"/api/users/{created['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

    def test_delete_user_not_found_returns_404(self):
        resp = self.client.delete("/api/users/99999")
        self.assertEqual(resp.status_code, 404)

    @patch("app.tcg_api.get_card")
    def test_delete_user_cascades_collection(self, mock_get):
        """Deleting a user removes their collection entries."""
        mock_get.return_value = FAKE_CARD
        user = self.client.post("/api/users", json={"username": "prof_oak"}).get_json()["data"]
        api_key = user["api_key"]

        # Add a card to this user's collection
        self.client.post(
            "/api/collection",
            json={"card_id": "base1-4"},
            headers={"X-Api-Key": api_key},
        )

        # Verify it's there
        col_before = self.client.get(
            "/api/collection", headers={"X-Api-Key": api_key}
        ).get_json()
        self.assertEqual(col_before["total"], 1)

        # Delete the user
        self.client.delete(f"/api/users/{user['id']}")

        # Their collection is gone (anonymous collection is also empty)
        col_after = self.client.get("/api/collection").get_json()
        self.assertEqual(col_after["total"], 0)

    # ------------------------------------------------------------------
    # User-scoped collection
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_collection_scoped_to_user(self, mock_get):
        """Two users' collections are independent."""
        mock_get.return_value = FAKE_CARD
        ash = self.client.post("/api/users", json={"username": "ash2"}).get_json()["data"]
        misty = self.client.post("/api/users", json={"username": "misty2"}).get_json()["data"]

        self.client.post(
            "/api/collection",
            json={"card_id": "base1-4", "quantity": 3},
            headers={"X-Api-Key": ash["api_key"]},
        )
        self.client.post(
            "/api/collection",
            json={"card_id": "base1-4", "quantity": 1},
            headers={"X-Api-Key": misty["api_key"]},
        )

        ash_col = self.client.get(
            "/api/collection", headers={"X-Api-Key": ash["api_key"]}
        ).get_json()
        misty_col = self.client.get(
            "/api/collection", headers={"X-Api-Key": misty["api_key"]}
        ).get_json()

        self.assertEqual(ash_col["items"][0]["quantity"], 3)
        self.assertEqual(misty_col["items"][0]["quantity"], 1)

    @patch("app.tcg_api.get_card")
    def test_anonymous_and_user_collections_are_separate(self, mock_get):
        """Authenticated and anonymous entries do not interfere with each other."""
        mock_get.return_value = FAKE_CARD
        user = self.client.post("/api/users", json={"username": "red"}).get_json()["data"]

        # Add to anonymous pool (no auth)
        self.client.post("/api/collection", json={"card_id": "base1-4", "quantity": 5})
        # Add to user pool (with auth)
        self.client.post(
            "/api/collection",
            json={"card_id": "base1-4", "quantity": 2},
            headers={"X-Api-Key": user["api_key"]},
        )

        anon_total = self.client.get("/api/collection").get_json()["total"]
        user_total = self.client.get(
            "/api/collection", headers={"X-Api-Key": user["api_key"]}
        ).get_json()["total"]

        self.assertEqual(anon_total, 1)
        self.assertEqual(user_total, 1)

    @patch("app.tcg_api.get_card")
    def test_collection_stats_scoped_to_user(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self.client.post("/api/users", json={"username": "blue"}).get_json()["data"]

        self.client.post(
            "/api/collection",
            json={"card_id": "base1-4", "quantity": 7},
            headers={"X-Api-Key": user["api_key"]},
        )

        stats = self.client.get(
            "/api/collection/stats", headers={"X-Api-Key": user["api_key"]}
        ).get_json()["data"]
        self.assertEqual(stats["total_cards"], 7)
        self.assertEqual(stats["unique_cards"], 1)

    # ------------------------------------------------------------------
    # API key auth via query param
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_api_key_as_query_param(self, mock_get):
        """api_key can be passed as a query parameter instead of a header."""
        mock_get.return_value = FAKE_CARD
        user = self.client.post("/api/users", json={"username": "tracey"}).get_json()["data"]
        key = user["api_key"]

        self.client.post(
            "/api/collection",
            json={"card_id": "base1-4"},
            headers={"X-Api-Key": key},
        )

        resp = self.client.get(f"/api/collection?api_key={key}")
        self.assertEqual(resp.get_json()["total"], 1)

    def test_invalid_api_key_returns_empty_collection(self):
        """An unrecognised API key is treated as unauthenticated (returns all anonymous entries)."""
        resp = self.client.get("/api/collection", headers={"X-Api-Key": "bogus-key"})
        self.assertEqual(resp.status_code, 200)
        # Falls through to anonymous pool which is empty
        self.assertEqual(resp.get_json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
