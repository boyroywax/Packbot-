"""Integration tests for basic Flask API routes (scan, search, cards, collection, history)."""

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


class TestAppRoutes(unittest.TestCase):
    """Tests for all Flask API endpoints using Flask's test client."""

    def setUp(self):
        # Use a temporary file as the database for each test
        self._db_fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.environ["DATABASE_PATH"] = self._db_path

        # Import app fresh with the temp DB path in place
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
    # Health
    # ------------------------------------------------------------------

    def test_health_returns_ok(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)

    # ------------------------------------------------------------------
    # POST /api/scan/image
    # ------------------------------------------------------------------

    @patch("app.scanner.scan_from_image")
    @patch("app.db.upsert_card")
    @patch("app.db.log_scan")
    def test_scan_image_with_card_found(self, mock_log, mock_upsert, mock_scan):
        mock_scan.return_value = {
            "card": FAKE_CARD,
            "method": "set_number",
            "confidence": 1.0,
            "candidates": [],
        }
        payload = {"image": "", "set_code": "base1", "card_number": "4"}
        resp = self.client.post("/api/scan/image", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["card"]["id"], "base1-4")
        self.assertEqual(data["method"], "set_number")
        mock_upsert.assert_called_once_with(FAKE_CARD)
        mock_log.assert_called_once()

    @patch("app.scanner.scan_from_image")
    def test_scan_image_no_card_found(self, mock_scan):
        mock_scan.return_value = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}
        resp = self.client.post("/api/scan/image", json={"image": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["card"])

    @patch("app.scanner.scan_from_image")
    def test_scan_image_empty_body_is_ok(self, mock_scan):
        mock_scan.return_value = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}
        resp = self.client.post("/api/scan/image", data="", content_type="application/json")
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # POST /api/scan/text
    # ------------------------------------------------------------------

    def test_scan_text_missing_field_returns_400(self):
        resp = self.client.post("/api/scan/text", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_scan_text_blank_text_returns_400(self):
        resp = self.client.post("/api/scan/text", json={"text": "   "})
        self.assertEqual(resp.status_code, 400)

    @patch("app.scanner.scan_from_text")
    @patch("app.db.upsert_card")
    @patch("app.db.log_scan")
    def test_scan_text_success(self, mock_log, mock_upsert, mock_scan):
        mock_scan.return_value = {
            "card": FAKE_CARD,
            "method": "text_set_number",
            "confidence": 0.9,
            "candidates": [],
        }
        resp = self.client.post("/api/scan/text", json={"text": "base1/4"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["card"]["name"], "Charizard")
        mock_upsert.assert_called_once()
        mock_log.assert_called_once()

    @patch("app.scanner.scan_from_text")
    def test_scan_text_no_match(self, mock_scan):
        mock_scan.return_value = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}
        resp = self.client.post("/api/scan/text", json={"text": "xyzzy123"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["card"])

    # ------------------------------------------------------------------
    # GET /api/cards/search
    # ------------------------------------------------------------------

    def test_cards_search_no_params_returns_400(self):
        resp = self.client.get("/api/cards/search")
        self.assertEqual(resp.status_code, 400)

    @patch("app.tcg_api.search_cards")
    def test_cards_search_with_q(self, mock_search):
        mock_search.return_value = {"data": [FAKE_CARD], "totalCount": 1}
        resp = self.client.get("/api/cards/search?q=name:Charizard")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["data"]), 1)
        mock_search.assert_called_once_with("name:Charizard", page=1, page_size=20)

    @patch("app.tcg_api.search_cards")
    def test_cards_search_name_alias(self, mock_search):
        mock_search.return_value = {"data": [FAKE_CARD], "totalCount": 1}
        resp = self.client.get("/api/cards/search?name=Charizard")
        self.assertEqual(resp.status_code, 200)
        # name param is converted to a q query
        called_q = mock_search.call_args[0][0]
        self.assertIn("Charizard", called_q)

    @patch("app.tcg_api.search_cards")
    def test_cards_search_page_size_capped_at_250(self, mock_search):
        mock_search.return_value = {"data": [], "totalCount": 0}
        self.client.get("/api/cards/search?q=name:Pikachu&page_size=9999")
        _, kwargs = mock_search.call_args
        self.assertLessEqual(kwargs["page_size"], 250)

    # ------------------------------------------------------------------
    # GET /api/cards/<card_id>
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_card_detail_found(self, mock_get):
        mock_get.return_value = FAKE_CARD
        resp = self.client.get("/api/cards/base1-4")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["id"], "base1-4")

    @patch("app.tcg_api.get_card")
    def test_card_detail_not_found(self, mock_get):
        mock_get.return_value = None
        resp = self.client.get("/api/cards/bad-id")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # GET /api/cards/<card_id>/price
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card_price")
    def test_card_price_found(self, mock_price):
        mock_price.return_value = {"holofoil": {"market": 320.0}}
        resp = self.client.get("/api/cards/base1-4/price")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("data", resp.get_json())

    @patch("app.tcg_api.get_card_price")
    def test_card_price_not_found(self, mock_price):
        mock_price.return_value = None
        resp = self.client.get("/api/cards/bad-id/price")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # GET /api/sets
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_sets")
    def test_sets_list(self, mock_sets):
        mock_sets.return_value = {"data": [{"id": "base1", "name": "Base Set"}]}
        resp = self.client.get("/api/sets")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"][0]["id"], "base1")

    # ------------------------------------------------------------------
    # GET /api/collection
    # ------------------------------------------------------------------

    def test_collection_empty_initially(self):
        resp = self.client.get("/api/collection")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])

    # ------------------------------------------------------------------
    # POST /api/collection
    # ------------------------------------------------------------------

    def test_collection_add_missing_card_id_returns_400(self):
        resp = self.client.post("/api/collection", json={})
        self.assertEqual(resp.status_code, 400)

    @patch("app.tcg_api.get_card")
    def test_collection_add_card_not_in_api_returns_404(self, mock_get):
        mock_get.return_value = None
        resp = self.client.post("/api/collection", json={"card_id": "bad-id"})
        self.assertEqual(resp.status_code, 404)

    @patch("app.tcg_api.get_card")
    def test_collection_add_success(self, mock_get):
        mock_get.return_value = FAKE_CARD
        resp = self.client.post("/api/collection", json={
            "card_id": "base1-4",
            "condition": "NM",
            "foil": False,
            "quantity": 2,
        })
        self.assertEqual(resp.status_code, 201)
        entry = resp.get_json()["data"]
        self.assertEqual(entry["card_id"], "base1-4")
        self.assertEqual(entry["quantity"], 2)

    @patch("app.tcg_api.get_card")
    def test_collection_add_increments_quantity(self, mock_get):
        mock_get.return_value = FAKE_CARD
        self.client.post("/api/collection", json={"card_id": "base1-4", "quantity": 1})
        self.client.post("/api/collection", json={"card_id": "base1-4", "quantity": 3})
        resp = self.client.get("/api/collection")
        items = resp.get_json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 4)

    # ------------------------------------------------------------------
    # DELETE /api/collection/<id>
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_collection_remove_success(self, mock_get):
        mock_get.return_value = FAKE_CARD
        add_resp = self.client.post("/api/collection", json={"card_id": "base1-4"})
        entry_id = add_resp.get_json()["data"]["id"]

        del_resp = self.client.delete(f"/api/collection/{entry_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.get_json()["success"])

    def test_collection_remove_nonexistent_returns_404(self):
        resp = self.client.delete("/api/collection/99999")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # GET /api/collection/stats
    # ------------------------------------------------------------------

    def test_collection_stats_empty(self):
        resp = self.client.get("/api/collection/stats")
        self.assertEqual(resp.status_code, 200)
        stats = resp.get_json()["data"]
        self.assertEqual(stats["unique_cards"], 0)
        self.assertEqual(stats["total_cards"], 0)

    @patch("app.tcg_api.get_card")
    def test_collection_stats_after_add(self, mock_get):
        mock_get.return_value = FAKE_CARD
        self.client.post("/api/collection", json={"card_id": "base1-4", "quantity": 3})
        resp = self.client.get("/api/collection/stats")
        stats = resp.get_json()["data"]
        self.assertEqual(stats["unique_cards"], 1)
        self.assertEqual(stats["total_cards"], 3)

    # ------------------------------------------------------------------
    # GET /api/scans
    # ------------------------------------------------------------------

    def test_scan_history_empty(self):
        resp = self.client.get("/api/scans")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"], [])

    @patch("app.scanner.scan_from_text")
    def test_scan_history_populated_after_scan(self, mock_scan):
        mock_scan.return_value = {
            "card": FAKE_CARD,
            "method": "text_set_number",
            "confidence": 0.9,
            "candidates": [],
        }
        # Real upsert_card runs so the FK constraint in scan_history is satisfied
        self.client.post("/api/scan/text", json={"text": "base1/4"})
        resp = self.client.get("/api/scans")
        self.assertEqual(resp.status_code, 200)
        history = resp.get_json()["data"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["card_id"], "base1-4")


if __name__ == "__main__":
    unittest.main()
