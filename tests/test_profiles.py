"""Tests for public profile endpoints and /u/<username> page."""

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


class TestPublicProfileRoutes(_AppTestMixin, unittest.TestCase):
    """Tests for public profile endpoints and /u/<username> page."""

    def _add(self, api_key, **kw):
        with patch("app.tcg_api.get_card", return_value=FAKE_CARD):
            r = self.client.post("/api/collection",
                                 json={"card_id": "base1-4", **kw},
                                 headers={"X-Api-Key": api_key})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["data"]

    # ------------------------------------------------------------------
    # GET /u/<username>
    # ------------------------------------------------------------------

    def test_profile_page_served(self):
        resp = self.client.get("/u/ash")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Packbot", resp.data)

    # ------------------------------------------------------------------
    # GET /api/users/<username>/profile
    # ------------------------------------------------------------------

    def test_profile_summary(self):
        user = self._make_user("ash")
        resp = self.client.get("/api/users/ash/profile")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["username"], "ash")
        self.assertIn("collection_count", data)
        self.assertIn("total_cards", data)
        self.assertIn("listing_count", data)
        self.assertIn("wishlist_count", data)

    def test_profile_not_found_returns_404(self):
        resp = self.client.get("/api/users/nobody/profile")
        self.assertEqual(resp.status_code, 404)

    def test_profile_counts_reflect_collection(self):
        user = self._make_user("gary")
        self._add(user["api_key"], quantity=3)
        resp = self.client.get("/api/users/gary/profile")
        data = resp.get_json()["data"]
        self.assertEqual(data["collection_count"], 1)
        self.assertEqual(data["total_cards"], 3)

    def test_profile_hides_api_key_and_password(self):
        self._make_user("brock", password="onix")
        data = self.client.get("/api/users/brock/profile").get_json()["data"]
        self.assertNotIn("api_key", data)
        self.assertNotIn("password_hash", data)

    # ------------------------------------------------------------------
    # GET /api/users/<username>/collection
    # ------------------------------------------------------------------

    def test_public_collection_empty(self):
        self._make_user("misty")
        resp = self.client.get("/api/users/misty/collection")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["total"], 0)

    def test_public_collection_shows_entries(self):
        user = self._make_user("red")
        self._add(user["api_key"], quantity=2)
        resp = self.client.get("/api/users/red/collection")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["quantity"], 2)
        self.assertEqual(data["items"][0]["name"], "Charizard")

    def test_public_collection_does_not_include_anonymous_entries(self):
        """Anonymous (no user_id) pool must not appear in public collection."""
        user = self._make_user("blue2")
        with patch("app.tcg_api.get_card", return_value=FAKE_CARD):
            self.client.post("/api/collection", json={"card_id": "base1-4"})  # anon
        self._add(user["api_key"])  # user

        resp = self.client.get("/api/users/blue2/collection")
        self.assertEqual(resp.get_json()["total"], 1)  # only user's

    def test_public_collection_not_found_returns_404(self):
        resp = self.client.get("/api/users/nobody/collection")
        self.assertEqual(resp.status_code, 404)

    def test_public_collection_includes_listing_fields(self):
        user = self._make_user("lance")
        entry = self._add(user["api_key"])
        self.client.patch(f"/api/collection/{entry['id']}",
                          json={"listing_type": "for_sale", "asking_price": 25.0},
                          headers={"X-Api-Key": user["api_key"]})
        items = self.client.get("/api/users/lance/collection").get_json()["items"]
        self.assertEqual(items[0]["listing_type"], "for_sale")
        self.assertAlmostEqual(items[0]["asking_price"], 25.0)

    # ------------------------------------------------------------------
    # GET /api/users/<username>/listings
    # ------------------------------------------------------------------

    def test_listings_empty(self):
        self._make_user("erika")
        resp = self.client.get("/api/users/erika/listings")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["total"], 0)

    def test_listings_shows_for_trade(self):
        user = self._make_user("surge")
        entry = self._add(user["api_key"])
        self.client.patch(f"/api/collection/{entry['id']}",
                          json={"listing_type": "for_trade"},
                          headers={"X-Api-Key": user["api_key"]})
        resp = self.client.get("/api/users/surge/listings")
        self.assertEqual(resp.get_json()["total"], 1)
        self.assertEqual(resp.get_json()["items"][0]["listing_type"], "for_trade")

    def test_listings_shows_for_sale(self):
        user = self._make_user("koga")
        entry = self._add(user["api_key"])
        self.client.patch(f"/api/collection/{entry['id']}",
                          json={"listing_type": "for_sale", "asking_price": 5.0},
                          headers={"X-Api-Key": user["api_key"]})
        data = self.client.get("/api/users/koga/listings").get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["asking_price"], 5.0)

    def test_listings_type_filter_for_trade(self):
        user = self._make_user("sabrina")
        entry = self._add(user["api_key"])
        self.client.patch(f"/api/collection/{entry['id']}",
                          json={"listing_type": "for_trade"},
                          headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(
            self.client.get("/api/users/sabrina/listings?type=for_trade").get_json()["total"], 1
        )
        self.assertEqual(
            self.client.get("/api/users/sabrina/listings?type=for_sale").get_json()["total"], 0
        )

    def test_listings_excludes_unlisted_cards(self):
        user = self._make_user("blaine")
        self._add(user["api_key"])  # no listing_type
        self.assertEqual(
            self.client.get("/api/users/blaine/listings").get_json()["total"], 0
        )

    def test_listings_invalid_type_returns_400(self):
        self._make_user("giovanni")
        resp = self.client.get("/api/users/giovanni/listings?type=for_rent")
        self.assertEqual(resp.status_code, 400)

    def test_listings_not_found_returns_404(self):
        resp = self.client.get("/api/users/nobody/listings")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # GET /api/users/<username>/wishlist  (public)
    # ------------------------------------------------------------------

    def test_public_wishlist_empty(self):
        self._make_user("lorelei")
        resp = self.client.get("/api/users/lorelei/wishlist")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"], [])

    def test_public_wishlist_not_found_returns_404(self):
        resp = self.client.get("/api/users/nobody/wishlist")
        self.assertEqual(resp.status_code, 404)

    def test_listing_count_in_profile_reflects_state(self):
        user = self._make_user("oak")
        e1 = self._add(user["api_key"])
        self.client.patch(f"/api/collection/{e1['id']}",
                          json={"listing_type": "for_trade"},
                          headers={"X-Api-Key": user["api_key"]})
        data = self.client.get("/api/users/oak/profile").get_json()["data"]
        self.assertEqual(data["listing_count"], 1)


if __name__ == "__main__":
    unittest.main()
