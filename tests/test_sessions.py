"""Tests for POST/GET/DELETE /api/sessions and the Bearer-token auth flow."""

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


if __name__ == "__main__":
    unittest.main()
