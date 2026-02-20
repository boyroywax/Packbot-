"""Tests for GET|POST|DELETE /api/wishlist."""

import os
import sys
import types
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

from tests.test_helpers import FAKE_CARD, _AppTestMixin


class TestWishlistRoutes(_AppTestMixin, unittest.TestCase):
    """Tests for GET|POST|DELETE /api/wishlist."""

    def _login_user(self, username, password="pass1234"):
        self._make_user(username, password=password)
        r = self.client.post("/api/sessions", json={"username": username, "password": password})
        return r.get_json()["data"]["token"]

    # ------------------------------------------------------------------
    # POST /api/wishlist
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_add_to_wishlist(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("dawn2")
        resp = self.client.post("/api/wishlist",
                                json={"card_id": "base1-4"},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertEqual(data["card_id"], "base1-4")

    @patch("app.tcg_api.get_card")
    def test_add_to_wishlist_with_notes(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("may")
        resp = self.client.post("/api/wishlist",
                                json={"card_id": "base1-4", "notes": "PSA 10 only"},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["data"]["notes"], "PSA 10 only")

    @patch("app.tcg_api.get_card")
    def test_add_duplicate_updates_notes(self, mock_get):
        """Re-adding a card updates its notes (upsert behaviour)."""
        mock_get.return_value = FAKE_CARD
        user = self._make_user("brendan")
        self.client.post("/api/wishlist", json={"card_id": "base1-4", "notes": "first"},
                         headers={"X-Api-Key": user["api_key"]})
        resp = self.client.post("/api/wishlist",
                                json={"card_id": "base1-4", "notes": "updated note"},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["data"]["notes"], "updated note")

    def test_add_wishlist_missing_card_id_returns_400(self):
        user = self._make_user("wally")
        resp = self.client.post("/api/wishlist", json={},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 400)

    @patch("app.tcg_api.get_card")
    def test_add_wishlist_unknown_card_returns_404(self, mock_get):
        mock_get.return_value = None
        user = self._make_user("birch")
        resp = self.client.post("/api/wishlist", json={"card_id": "fake-0"},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 404)

    def test_add_wishlist_requires_auth(self):
        resp = self.client.post("/api/wishlist", json={"card_id": "base1-4"})
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # GET /api/wishlist  (private)
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_get_wishlist(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("steven")
        self.client.post("/api/wishlist", json={"card_id": "base1-4"},
                         headers={"X-Api-Key": user["api_key"]})
        resp = self.client.get("/api/wishlist", headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 200)
        items = resp.get_json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Charizard")

    def test_get_wishlist_requires_auth(self):
        resp = self.client.get("/api/wishlist")
        self.assertEqual(resp.status_code, 401)

    @patch("app.tcg_api.get_card")
    def test_wishlist_scoped_to_user(self, mock_get):
        """Each user sees only their own wishlist items."""
        mock_get.return_value = FAKE_CARD
        ash = self._make_user("ash3")
        misty = self._make_user("misty3")
        self.client.post("/api/wishlist", json={"card_id": "base1-4"},
                         headers={"X-Api-Key": ash["api_key"]})
        resp = self.client.get("/api/wishlist", headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.get_json()["data"], [])

    # ------------------------------------------------------------------
    # DELETE /api/wishlist/<id>
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_remove_from_wishlist(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("wallace")
        add_resp = self.client.post("/api/wishlist", json={"card_id": "base1-4"},
                                    headers={"X-Api-Key": user["api_key"]})
        wid = add_resp.get_json()["data"]["id"]

        del_resp = self.client.delete(f"/api/wishlist/{wid}",
                                      headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(del_resp.status_code, 200)

        items = self.client.get("/api/wishlist",
                                headers={"X-Api-Key": user["api_key"]}).get_json()["data"]
        self.assertEqual(len(items), 0)

    def test_remove_nonexistent_wishlist_entry_returns_404(self):
        user = self._make_user("winona")
        resp = self.client.delete("/api/wishlist/99999",
                                  headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 404)

    @patch("app.tcg_api.get_card")
    def test_cannot_remove_other_users_wishlist_entry(self, mock_get):
        mock_get.return_value = FAKE_CARD
        ash = self._make_user("ash4")
        misty = self._make_user("misty4")
        wid = self.client.post("/api/wishlist", json={"card_id": "base1-4"},
                               headers={"X-Api-Key": ash["api_key"]}
                               ).get_json()["data"]["id"]
        resp = self.client.delete(f"/api/wishlist/{wid}",
                                  headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.status_code, 404)

    def test_remove_wishlist_requires_auth(self):
        resp = self.client.delete("/api/wishlist/1")
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # Public wishlist integration
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_public_wishlist_shows_items(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("flannery")
        self.client.post("/api/wishlist", json={"card_id": "base1-4", "notes": "want one"},
                         headers={"X-Api-Key": user["api_key"]})
        data = self.client.get("/api/users/flannery/wishlist").get_json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Charizard")
        self.assertEqual(data[0]["notes"], "want one")

    @patch("app.tcg_api.get_card")
    def test_wishlist_count_in_profile(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("norman")
        self.client.post("/api/wishlist", json={"card_id": "base1-4"},
                         headers={"X-Api-Key": user["api_key"]})
        profile = self.client.get("/api/users/norman/profile").get_json()["data"]
        self.assertEqual(profile["wishlist_count"], 1)


if __name__ == "__main__":
    unittest.main()
