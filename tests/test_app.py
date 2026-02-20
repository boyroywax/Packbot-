"""Integration tests for the Flask API routes in app.py."""

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


class TestSessionRoutes(unittest.TestCase):
    """Tests for POST/GET/DELETE /api/sessions and the Bearer-token auth flow."""

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
    # Helper
    # ------------------------------------------------------------------

    def _register(self, username="ash", password="pikachu123", email=None):
        """Register a user with a password and return their data."""
        resp = self.client.post("/api/users", json={
            "username": username, "password": password, "email": email,
        })
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["data"]

    def _login(self, username="ash", password="pikachu123"):
        """Login and return the session payload."""
        resp = self.client.post("/api/sessions", json={
            "username": username, "password": password,
        })
        return resp

    # ------------------------------------------------------------------
    # POST /api/sessions  (login)
    # ------------------------------------------------------------------

    def test_login_success(self):
        self._register()
        resp = self._login()
        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json()["data"]
        self.assertIn("token", payload)
        self.assertIn("expires_at", payload)
        self.assertIn("user", payload)
        self.assertEqual(payload["user"]["username"], "ash")
        # Sensitive fields must not be exposed
        self.assertNotIn("password_hash", payload["user"])
        self.assertNotIn("api_key", payload["user"])

    def test_login_wrong_password_returns_401(self):
        self._register()
        resp = self._login(password="wrongpass")
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_user_returns_401(self):
        resp = self._login(username="nobody")
        self.assertEqual(resp.status_code, 401)

    def test_login_missing_fields_returns_400(self):
        resp = self.client.post("/api/sessions", json={"username": "ash"})
        self.assertEqual(resp.status_code, 400)

    def test_login_no_password_set_returns_401(self):
        """A user registered without a password cannot log in."""
        self.client.post("/api/users", json={"username": "nopassuser"})
        resp = self._login(username="nopassuser", password="anything")
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # GET /api/sessions/me
    # ------------------------------------------------------------------

    def test_sessions_me_with_bearer_token(self):
        self._register()
        token = self._login().get_json()["data"]["token"]
        resp = self.client.get("/api/sessions/me",
                               headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["username"], "ash")

    def test_sessions_me_with_api_key(self):
        """GET /api/sessions/me also works with X-Api-Key."""
        user = self._register()
        # Re-fetch to get api_key (registration returns it)
        resp = self.client.get("/api/sessions/me",
                               headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["username"], "ash")

    def test_sessions_me_unauthenticated_returns_401(self):
        resp = self.client.get("/api/sessions/me")
        self.assertEqual(resp.status_code, 401)

    def test_sessions_me_invalid_token_returns_401(self):
        resp = self.client.get("/api/sessions/me",
                               headers={"Authorization": "Bearer totally-fake-token"})
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # GET /api/sessions  (list active sessions)
    # ------------------------------------------------------------------

    def test_sessions_list_shows_active(self):
        self._register()
        # Login twice → 2 sessions
        self._login()
        self._login()
        token = self._login().get_json()["data"]["token"]
        resp = self.client.get("/api/sessions",
                               headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["data"]), 3)

    def test_sessions_list_requires_auth(self):
        resp = self.client.get("/api/sessions")
        self.assertEqual(resp.status_code, 401)

    def test_sessions_list_does_not_expose_token_of_other_sessions(self):
        """Tokens returned are still present (we don't hide them in the list)
        but other users' sessions must not appear."""
        self._register("ash", "pikachu123")
        self._register("misty", "staryu123")
        ash_token = self._login("ash", "pikachu123").get_json()["data"]["token"]
        self._login("misty", "staryu123")

        sessions = self.client.get("/api/sessions",
                                   headers={"Authorization": f"Bearer {ash_token}"}
                                   ).get_json()["data"]
        # Only ash's sessions
        self.assertEqual(len(sessions), 1)

    # ------------------------------------------------------------------
    # DELETE /api/sessions  (logout current)
    # ------------------------------------------------------------------

    def test_logout_invalidates_token(self):
        self._register()
        token = self._login().get_json()["data"]["token"]

        logout = self.client.delete("/api/sessions",
                                    headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout.status_code, 200)

        # Token is now invalid
        me = self.client.get("/api/sessions/me",
                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 401)

    def test_logout_without_bearer_returns_400(self):
        user = self._register()
        resp = self.client.delete("/api/sessions",
                                  headers={"X-Api-Key": user["api_key"]})
        self.assertEqual(resp.status_code, 400)

    def test_logout_other_sessions_remain(self):
        self._register()
        t1 = self._login().get_json()["data"]["token"]
        t2 = self._login().get_json()["data"]["token"]

        # Logout session 1
        self.client.delete("/api/sessions",
                           headers={"Authorization": f"Bearer {t1}"})

        # Session 2 still works
        me = self.client.get("/api/sessions/me",
                             headers={"Authorization": f"Bearer {t2}"})
        self.assertEqual(me.status_code, 200)

    # ------------------------------------------------------------------
    # DELETE /api/sessions/all  (logout all)
    # ------------------------------------------------------------------

    def test_logout_all_invalidates_every_session(self):
        self._register()
        t1 = self._login().get_json()["data"]["token"]
        t2 = self._login().get_json()["data"]["token"]
        t3 = self._login().get_json()["data"]["token"]

        resp = self.client.delete("/api/sessions/all",
                                  headers={"Authorization": f"Bearer {t1}"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["sessions_revoked"], 3)

        for token in (t1, t2, t3):
            me = self.client.get("/api/sessions/me",
                                 headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 401)

    def test_logout_all_requires_auth(self):
        resp = self.client.delete("/api/sessions/all")
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # Bearer token scopes collection data
    # ------------------------------------------------------------------

    @patch("app.tcg_api.get_card")
    def test_bearer_token_scopes_collection(self, mock_get):
        """Bearer session tokens scope the collection just like api_key."""
        mock_get.return_value = FAKE_CARD
        self._register()
        token = self._login().get_json()["data"]["token"]

        self.client.post("/api/collection",
                         json={"card_id": "base1-4", "quantity": 2},
                         headers={"Authorization": f"Bearer {token}"})

        col = self.client.get("/api/collection",
                              headers={"Authorization": f"Bearer {token}"}
                              ).get_json()
        self.assertEqual(col["total"], 1)
        self.assertEqual(col["items"][0]["quantity"], 2)

    # ------------------------------------------------------------------
    # Registration with password
    # ------------------------------------------------------------------

    def test_register_with_password_hides_hash(self):
        """password_hash must never appear in the registration response."""
        resp = self.client.post("/api/users",
                                json={"username": "brock", "password": "onix4ever"})
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertNotIn("password_hash", data)

    def test_multiple_logins_create_independent_sessions(self):
        self._register()
        t1 = self._login().get_json()["data"]["token"]
        t2 = self._login().get_json()["data"]["token"]
        self.assertNotEqual(t1, t2)

        # Both valid simultaneously
        for tok in (t1, t2):
            self.assertEqual(
                self.client.get("/api/sessions/me",
                                headers={"Authorization": f"Bearer {tok}"}
                                ).status_code, 200
            )


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
