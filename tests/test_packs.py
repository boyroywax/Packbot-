"""Tests for POST/GET/DELETE /api/pack-sessions and related sub-routes."""

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


class TestPackSessionRoutes(_AppTestMixin, unittest.TestCase):
    """Tests for POST/GET/DELETE /api/pack-sessions and related sub-routes."""

    # ------------------------------------------------------------------
    # POST /api/pack-sessions  (create)
    # ------------------------------------------------------------------

    def test_create_session_anonymous(self):
        """Pack sessions can be created without authentication."""
        resp = self.client.post("/api/pack-sessions", json={
            "set_id": "base1", "set_name": "Base Set", "pack_name": "Booster",
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertEqual(data["set_id"], "base1")
        self.assertEqual(data["status"], "active")
        self.assertIsNone(data["user_id"])

    def test_create_session_authenticated(self):
        """Authenticated session stores user_id."""
        user = self._make_user("ash")
        resp = self.client.post("/api/pack-sessions",
                                json={"set_id": "sv1"},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["data"]["user_id"], user["id"])

    def test_create_session_no_body(self):
        """Empty body is fine – all fields optional."""
        resp = self.client.post("/api/pack-sessions", json={})
        self.assertEqual(resp.status_code, 201)

    # ------------------------------------------------------------------
    # GET /api/pack-sessions/<id>  (fetch)
    # ------------------------------------------------------------------

    def test_get_session(self):
        sid = self.client.post("/api/pack-sessions", json={"set_id": "xy1"}).get_json()["data"]["id"]
        resp = self.client.get(f"/api/pack-sessions/{sid}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["id"], sid)
        self.assertIn("cards", data)
        self.assertEqual(data["cards"], [])

    def test_get_session_not_found(self):
        resp = self.client.get("/api/pack-sessions/99999")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # GET /api/pack-sessions  (list)
    # ------------------------------------------------------------------

    def test_list_sessions_requires_auth(self):
        resp = self.client.get("/api/pack-sessions")
        self.assertEqual(resp.status_code, 401)

    def test_list_sessions_for_user(self):
        user = self._make_user("misty")
        self.client.post("/api/pack-sessions", json={"set_id": "base1"},
                         headers={"X-Api-Key": user["api_key"]})
        self.client.post("/api/pack-sessions", json={"set_id": "sv1"},
                         headers={"X-Api-Key": user["api_key"]})
        sessions = self.client.get("/api/pack-sessions",
                                   headers={"X-Api-Key": user["api_key"]}).get_json()["data"]
        self.assertEqual(len(sessions), 2)

    # ------------------------------------------------------------------
    # POST /api/pack-sessions/<id>/cards  (add card)
    # ------------------------------------------------------------------

    def _new_session(self, set_id="base1"):
        return self.client.post("/api/pack-sessions", json={"set_id": set_id}).get_json()["data"]

    def test_add_card_to_session(self):
        sid = self._new_session()["id"]
        resp = self.client.post(f"/api/pack-sessions/{sid}/cards", json={
            "card_id": "base1-4", "card_name": "Charizard", "number": "4",
            "set_name": "Base Set", "rarity": "Rare Holo", "confidence": 0.95,
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertEqual(data["card_name"], "Charizard")
        self.assertEqual(data["session_id"], sid)

    def test_add_card_missing_card_id_returns_400(self):
        sid = self._new_session()["id"]
        resp = self.client.post(f"/api/pack-sessions/{sid}/cards", json={"card_name": "Pikachu"})
        self.assertEqual(resp.status_code, 400)

    def test_add_card_to_nonexistent_session_returns_404(self):
        resp = self.client.post("/api/pack-sessions/99999/cards", json={"card_id": "base1-4"})
        self.assertEqual(resp.status_code, 404)

    def test_session_get_includes_cards(self):
        sid = self._new_session()["id"]
        self.client.post(f"/api/pack-sessions/{sid}/cards",
                         json={"card_id": "base1-4", "card_name": "Charizard"})
        self.client.post(f"/api/pack-sessions/{sid}/cards",
                         json={"card_id": "base1-58", "card_name": "Potion"})
        data = self.client.get(f"/api/pack-sessions/{sid}").get_json()["data"]
        self.assertEqual(len(data["cards"]), 2)

    # ------------------------------------------------------------------
    # DELETE /api/pack-sessions/<id>/cards/<card_id>  (remove card)
    # ------------------------------------------------------------------

    def test_remove_card_from_session(self):
        sid = self._new_session()["id"]
        cid = self.client.post(f"/api/pack-sessions/{sid}/cards",
                               json={"card_id": "base1-4"}).get_json()["data"]["id"]
        resp = self.client.delete(f"/api/pack-sessions/{sid}/cards/{cid}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            len(self.client.get(f"/api/pack-sessions/{sid}").get_json()["data"]["cards"]), 0
        )

    def test_remove_nonexistent_card_returns_404(self):
        sid = self._new_session()["id"]
        resp = self.client.delete(f"/api/pack-sessions/{sid}/cards/99999")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # POST /api/pack-sessions/<id>/scan  (detect frame)
    # ------------------------------------------------------------------

    @patch("app.scanner.scan_from_image")
    def test_scan_frame_uses_session_set_context(self, mock_scan):
        """The session's set_id should be forwarded as set_code to the scanner."""
        mock_scan.return_value = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}
        sid = self._new_session(set_id="sv1")["id"]
        self.client.post(f"/api/pack-sessions/{sid}/scan", json={"image": ""})
        _, kwargs = mock_scan.call_args
        self.assertEqual(kwargs.get("set_code") or mock_scan.call_args[0][2] if mock_scan.call_args[0] else kwargs.get("set_code"), "sv1")

    @patch("app.scanner.scan_from_image")
    def test_scan_frame_explicit_set_code_overrides_session(self, mock_scan):
        """Caller-supplied set_code wins over session default."""
        mock_scan.return_value = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}
        sid = self._new_session(set_id="base1")["id"]
        self.client.post(f"/api/pack-sessions/{sid}/scan",
                         json={"image": "", "set_code": "sv1"})
        args, kwargs = mock_scan.call_args
        supplied = kwargs.get("set_code") if kwargs.get("set_code") is not None else (args[2] if len(args) > 2 else None)
        self.assertEqual(supplied, "sv1")

    @patch("app.scanner.scan_from_image")
    @patch("app.db.upsert_card")
    def test_scan_frame_upserts_matched_card(self, mock_upsert, mock_scan):
        mock_scan.return_value = {
            "card": FAKE_CARD, "method": "set_number", "confidence": 1.0, "candidates": [],
        }
        sid = self._new_session()["id"]
        resp = self.client.post(f"/api/pack-sessions/{sid}/scan", json={"image": ""})
        self.assertEqual(resp.status_code, 200)
        mock_upsert.assert_called_once_with(FAKE_CARD)

    def test_scan_frame_on_nonexistent_session_returns_404(self):
        resp = self.client.post("/api/pack-sessions/99999/scan", json={"image": ""})
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # POST /api/pack-sessions/<id>/complete
    # ------------------------------------------------------------------

    def test_complete_session_without_collection(self):
        sid = self._new_session()["id"]
        self.client.post(f"/api/pack-sessions/{sid}/cards", json={"card_id": "base1-4"})
        resp = self.client.post(f"/api/pack-sessions/{sid}/complete",
                                json={"add_to_collection": False})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["cards_added"], 0)
        # Session is now completed – cannot add more cards
        r2 = self.client.post(f"/api/pack-sessions/{sid}/cards", json={"card_id": "base1-4"})
        self.assertEqual(r2.status_code, 400)

    @patch("app.tcg_api.get_card")
    def test_complete_session_adds_cards_to_collection(self, mock_get):
        mock_get.return_value = FAKE_CARD
        user = self._make_user("red2")
        # Seed the card in DB first via collection add so FK exists
        self.client.post("/api/collection",
                         json={"card_id": "base1-4"},
                         headers={"X-Api-Key": user["api_key"]})

        sid = self.client.post("/api/pack-sessions",
                               json={"set_id": "base1"},
                               headers={"X-Api-Key": user["api_key"]}).get_json()["data"]["id"]
        self.client.post(f"/api/pack-sessions/{sid}/cards",
                         json={"card_id": "base1-4", "card_name": "Charizard"})
        resp = self.client.post(f"/api/pack-sessions/{sid}/complete",
                                json={"add_to_collection": True, "condition": "NM"},
                                headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["cards_added"], 1)

    def test_complete_already_completed_session_returns_400(self):
        sid = self._new_session()["id"]
        self.client.post(f"/api/pack-sessions/{sid}/complete", json={})
        resp = self.client.post(f"/api/pack-sessions/{sid}/complete", json={})
        self.assertEqual(resp.status_code, 400)

    def test_complete_nonexistent_session_returns_404(self):
        resp = self.client.post("/api/pack-sessions/99999/complete", json={})
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # DELETE /api/pack-sessions/<id>  (cancel)
    # ------------------------------------------------------------------

    def test_cancel_session(self):
        sid = self._new_session()["id"]
        resp = self.client.delete(f"/api/pack-sessions/{sid}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get(f"/api/pack-sessions/{sid}").status_code, 404)

    def test_cancel_nonexistent_session_returns_404(self):
        resp = self.client.delete("/api/pack-sessions/99999")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # POST /api/packs/scan-barcode
    # ------------------------------------------------------------------

    def test_scan_barcode_empty_image_returns_null(self):
        """With no image (or pyzbar not installed) the endpoint returns gracefully."""
        resp = self.client.post("/api/packs/scan-barcode", json={"image": ""})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data["barcode"])

    def test_scan_barcode_missing_image_returns_null(self):
        resp = self.client.post("/api/packs/scan-barcode", json={})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["barcode"])


if __name__ == "__main__":
    unittest.main()
