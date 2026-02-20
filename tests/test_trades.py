"""Tests for GET /api/trade-matches."""

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


class TestTradeMatchRoutes(_AppTestMixin, unittest.TestCase):
    """Tests for GET /api/trade-matches."""

    def _col_add(self, api_key, card_id="base1-4"):
        with patch("app.tcg_api.get_card", return_value=FAKE_CARD):
            r = self.client.post("/api/collection",
                                 json={"card_id": card_id},
                                 headers={"X-Api-Key": api_key})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["data"]

    def _mark_for_trade(self, entry_id, api_key):
        r = self.client.patch(f"/api/collection/{entry_id}",
                              json={"listing_type": "for_trade"},
                              headers={"X-Api-Key": api_key})
        self.assertEqual(r.status_code, 200)

    def _add_wishlist(self, api_key, card_id="base1-4"):
        with patch("app.tcg_api.get_card", return_value=FAKE_CARD):
            r = self.client.post("/api/wishlist",
                                 json={"card_id": card_id},
                                 headers={"X-Api-Key": api_key})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["data"]

    def test_trade_matches_requires_auth(self):
        resp = self.client.get("/api/trade-matches")
        self.assertEqual(resp.status_code, 401)

    def test_trade_matches_empty_when_no_data(self):
        user = self._make_user("ash")
        resp = self.client.get("/api/trade-matches", headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["you_have_they_want"], [])
        self.assertEqual(data["they_have_you_want"], [])

    def test_you_have_they_want(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        entry = self._col_add(ash["api_key"])
        self._mark_for_trade(entry["id"], ash["api_key"])
        self._add_wishlist(misty["api_key"])
        resp = self.client.get("/api/trade-matches", headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 200)
        matches = resp.get_json()["data"]["you_have_they_want"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["match_username"], "misty")
        self.assertEqual(matches[0]["card_name"], FAKE_CARD["name"])

    def test_they_have_you_want(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        entry = self._col_add(misty["api_key"])
        self._mark_for_trade(entry["id"], misty["api_key"])
        self._add_wishlist(ash["api_key"])
        resp = self.client.get("/api/trade-matches", headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 200)
        matches = resp.get_json()["data"]["they_have_you_want"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["match_username"], "misty")

    def test_no_self_match(self):
        ash = self._make_user("ash")
        entry = self._col_add(ash["api_key"])
        self._mark_for_trade(entry["id"], ash["api_key"])
        self._add_wishlist(ash["api_key"])
        resp = self.client.get("/api/trade-matches", headers={"X-Api-Key": ash["api_key"]})
        data = resp.get_json()["data"]
        self.assertEqual(data["you_have_they_want"], [])
        self.assertEqual(data["they_have_you_want"], [])


if __name__ == "__main__":
    unittest.main()
