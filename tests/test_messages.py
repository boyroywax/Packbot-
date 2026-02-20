"""Tests for /api/messages and /api/messages/unread-count."""

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


class TestMessageRoutes(_AppTestMixin, unittest.TestCase):
    """Tests for /api/messages and /api/messages/unread-count."""

    def _send(self, sender_api_key, to_username, body="Hello!", subject=""):
        return self.client.post(
            "/api/messages",
            json={"to": to_username, "body": body, "subject": subject},
            headers={"X-Api-Key": sender_api_key},
        )

    # ------------------------------------------------------------------
    # POST /api/messages
    # ------------------------------------------------------------------

    def test_send_requires_auth(self):
        resp = self.client.post("/api/messages", json={"to": "x", "body": "hi"})
        self.assertEqual(resp.status_code, 401)

    def test_send_to_unknown_user_returns_404(self):
        ash = self._make_user("ash")
        resp = self._send(ash["api_key"], "nobody_here")
        self.assertEqual(resp.status_code, 404)

    def test_send_missing_body_returns_400(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        resp = self.client.post("/api/messages",
                                json={"to": misty["username"]},
                                headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 400)

    def test_send_missing_to_returns_400(self):
        ash = self._make_user("ash")
        resp = self.client.post("/api/messages",
                                json={"body": "hello"},
                                headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 400)

    def test_cannot_message_self(self):
        ash = self._make_user("ash")
        resp = self._send(ash["api_key"], "ash")
        self.assertEqual(resp.status_code, 400)

    def test_send_success(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        resp = self._send(ash["api_key"], "misty", "Want to trade?", subject="Trade offer")
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()["data"]
        self.assertEqual(data["body"], "Want to trade?")
        self.assertEqual(data["subject"], "Trade offer")

    # ------------------------------------------------------------------
    # GET /api/messages  (inbox)
    # ------------------------------------------------------------------

    def test_inbox_requires_auth(self):
        resp = self.client.get("/api/messages")
        self.assertEqual(resp.status_code, 401)

    def test_inbox_empty(self):
        ash = self._make_user("ash")
        resp = self.client.get("/api/messages", headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"], [])

    def test_inbox_receives_messages(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        self._send(ash["api_key"], "misty", "msg 1")
        self._send(ash["api_key"], "misty", "msg 2")
        resp = self.client.get("/api/messages", headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["data"]), 2)

    def test_inbox_scoped_to_user(self):
        """Messages sent to ash must not appear in misty's inbox."""
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        brock = self._make_user("brock")
        self._send(brock["api_key"], "ash", "For ash only")
        resp = self.client.get("/api/messages", headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.get_json()["data"], [])

    # ------------------------------------------------------------------
    # GET /api/messages/<id>
    # ------------------------------------------------------------------

    def test_get_message_marks_read(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        resp = self.client.get(f"/api/messages/{msg_id}",
                               headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["read"], 1)

    def test_sender_can_get_their_own_message(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        resp = self.client.get(f"/api/messages/{msg_id}",
                               headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 200)

    def test_get_message_wrong_user_returns_403(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        brock = self._make_user("brock")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        resp = self.client.get(f"/api/messages/{msg_id}",
                               headers={"X-Api-Key": brock["api_key"]})
        self.assertEqual(resp.status_code, 403)

    # ------------------------------------------------------------------
    # DELETE /api/messages/<id>
    # ------------------------------------------------------------------

    def test_delete_as_recipient(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        resp = self.client.delete(f"/api/messages/{msg_id}",
                                  headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

    def test_delete_as_sender(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        resp = self.client.delete(f"/api/messages/{msg_id}",
                                  headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 200)

    def test_delete_wrong_user_returns_403(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        brock = self._make_user("brock")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        resp = self.client.delete(f"/api/messages/{msg_id}",
                                  headers={"X-Api-Key": brock["api_key"]})
        self.assertEqual(resp.status_code, 403)

    # ------------------------------------------------------------------
    # GET /api/messages/unread-count
    # ------------------------------------------------------------------

    def test_unread_count_requires_auth(self):
        resp = self.client.get("/api/messages/unread-count")
        self.assertEqual(resp.status_code, 401)

    def test_unread_count_starts_at_zero(self):
        ash = self._make_user("ash")
        resp = self.client.get("/api/messages/unread-count",
                               headers={"X-Api-Key": ash["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["count"], 0)

    def test_unread_count_increments(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        self._send(ash["api_key"], "misty", "msg 1")
        self._send(ash["api_key"], "misty", "msg 2")
        resp = self.client.get("/api/messages/unread-count",
                               headers={"X-Api-Key": misty["api_key"]})
        self.assertEqual(resp.get_json()["data"]["count"], 2)

    def test_unread_count_decreases_after_read(self):
        ash = self._make_user("ash")
        misty = self._make_user("misty")
        msg_id = self._send(ash["api_key"], "misty", "Hi").get_json()["data"]["id"]
        # Before reading
        before = self.client.get("/api/messages/unread-count",
                                 headers={"X-Api-Key": misty["api_key"]}).get_json()["data"]["count"]
        self.assertEqual(before, 1)
        # Read it
        self.client.get(f"/api/messages/{msg_id}", headers={"X-Api-Key": misty["api_key"]})
        after = self.client.get("/api/messages/unread-count",
                                headers={"X-Api-Key": misty["api_key"]}).get_json()["data"]["count"]
        self.assertEqual(after, 0)


if __name__ == "__main__":
    unittest.main()
