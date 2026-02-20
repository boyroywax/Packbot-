"""Tests for PATCH /api/collection/<id> – listing_type, asking_price."""

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


class TestCollectionListingRoutes(_AppTestMixin, unittest.TestCase):
    """Tests for PATCH /api/collection/<id> – listing_type, asking_price."""

    def _add(self, api_key, **kw):
        with patch("app.tcg_api.get_card", return_value=FAKE_CARD):
            r = self.client.post("/api/collection",
                                 json={"card_id": "base1-4", **kw},
                                 headers={"X-Api-Key": api_key})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["data"]

    def test_mark_for_trade(self):
        user = self._make_user("ash")
        entry = self._add(user["api_key"])
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": "for_trade"},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["listing_type"], "for_trade")

    def test_mark_for_sale_with_price(self):
        user = self._make_user("brock")
        entry = self._add(user["api_key"])
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": "for_sale", "asking_price": 42.50},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["listing_type"], "for_sale")
        self.assertAlmostEqual(data["asking_price"], 42.50)

    def test_for_sale_without_price_returns_400(self):
        user = self._make_user("misty")
        entry = self._add(user["api_key"])
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": "for_sale"},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_remove_listing_with_null(self):
        user = self._make_user("gary")
        entry = self._add(user["api_key"])
        self.client.patch(f"/api/collection/{entry['id']}",
                          json={"listing_type": "for_trade"},
                          headers={"X-Api-Key": user["api_key"]})
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": None},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["data"]["listing_type"])

    def test_invalid_listing_type_returns_400(self):
        user = self._make_user("red")
        entry = self._add(user["api_key"])
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": "for_free"},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_update_other_users_entry(self):
        ash = self._make_user("ash2")
        misty = self._make_user("misty2")
        entry = self._add(ash["api_key"])
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": "for_trade"},
            headers={"X-Api-Key": misty["api_key"]},
        )
        self.assertEqual(resp.status_code, 404)

    def test_patch_requires_auth(self):
        user = self._make_user("blue")
        entry = self._add(user["api_key"])
        resp = self.client.patch(f"/api/collection/{entry['id']}",
                                 json={"listing_type": "for_trade"})
        self.assertEqual(resp.status_code, 401)

    def test_update_notes_and_quantity(self):
        user = self._make_user("dawn")
        entry = self._add(user["api_key"])
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"notes": "signed by artist", "quantity": 5},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["notes"], "signed by artist")
        self.assertEqual(data["quantity"], 5)

    def test_asking_price_cleared_when_switching_to_trade(self):
        user = self._make_user("lucas")
        entry = self._add(user["api_key"])
        # First mark for sale with price
        self.client.patch(f"/api/collection/{entry['id']}",
                          json={"listing_type": "for_sale", "asking_price": 9.99},
                          headers={"X-Api-Key": user["api_key"]})
        # Switch to for_trade → asking_price should be cleared
        resp = self.client.patch(
            f"/api/collection/{entry['id']}",
            json={"listing_type": "for_trade"},
            headers={"X-Api-Key": user["api_key"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["data"]["asking_price"])


if __name__ == "__main__":
    unittest.main()
