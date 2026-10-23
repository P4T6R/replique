"""Hosted conversation lifecycle without a provider call."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.accounts import create_invitation
from backend.app import app
from backend.test_app import PROVIDER_ANSWER


ORIGIN = "https://replique.duckdns.org"
HEADERS = {"Origin": ORIGIN, "X-Replique-Request": "1"}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "REPLIQUE_MODE": "owner_chatgpt", "REPLIQUE_PUBLIC_ORIGIN": ORIGIN,
            "REPLIQUE_DATA_DIR": self.data.name, "REPLIQUE_MODEL": "mock-model",
        })
        self.environment.start()
        self.metrics = patch("backend.app.record_generation")
        self.metrics.start()
        self.client = TestClient(app, base_url=ORIGIN)
        self.other = TestClient(app, base_url=ORIGIN)
        self.register(self.client, "one@example.test")
        self.register(self.other, "two@example.test")

    def tearDown(self):
        self.client.close()
        self.other.close()
        self.metrics.stop()
        self.environment.stop()
        self.data.cleanup()

    def register(self, client, email):
        response = client.post("/api/account/register", headers=HEADERS,
                               json={"email": email, "password": "a long beta password", "invitation": create_invitation()})
        self.assertEqual(response.status_code, 200, response.text)

    def create(self):
        response = self.client.post("/api/conversations", headers=HEADERS, json={"title": "Audrey"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_workspace_page_and_account_gate(self):
        page = self.client.get("/app")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("/assets/", page.text)
        stranger = TestClient(app, base_url=ORIGIN)
        try:
            self.assertEqual(stranger.get("/api/conversations").status_code, 401)
            self.assertEqual(stranger.post("/api/conversations", headers=HEADERS,
                                           json={"title": "Privée"}).status_code, 401)
        finally:
            stranger.close()

    def test_history_is_private_and_suggestions_are_not_sent(self):
        conversation = self.create()
        url = f"/api/conversations/{conversation['id']}"
        self.assertEqual(self.other.get(url).status_code, 404)
        self.assertEqual(self.other.post(url + "/messages", headers=HEADERS,
                                         json={"sender": "other", "body": "Bonjour"}).status_code, 404)
        added = self.client.post(url + "/messages", headers=HEADERS,
                                 json={"sender": "other", "body": "Coucou, tu fais quoi ?"})
        self.assertEqual(added.status_code, 200, added.text)
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps({**PROVIDER_ANSWER, "sparse_followup": False})) as provider:
            generated = self.client.post(url + "/generate", headers=HEADERS)
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertIn("Coucou, tu fais quoi ?", str(provider.await_args.args[1]))
        saved = self.client.get(url).json()
        self.assertEqual(len(saved["messages"]), 1)
        self.assertEqual(len(saved["suggestions"]["replies"]), 3)
        sent = self.client.post(url + "/messages", headers=HEADERS,
                                json={"sender": "me", "body": "Je lis un peu. Et toi ?"})
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual([m["sender"] for m in sent.json()["messages"]], ["other", "me"])
        self.assertIsNone(sent.json()["suggestions"])
        message_id = sent.json()["messages"][0]["id"]
        self.assertEqual(self.other.patch(url + "/messages/" + message_id, headers=HEADERS,
                                          json={"sender": "me", "body": "usurpation"}).status_code, 404)
        corrected = self.client.patch(url + "/messages/" + message_id, headers=HEADERS,
                                      json={"sender": "other", "body": "Coucou, tu fais quoi ce soir ?"})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        self.assertEqual(corrected.json()["messages"][0]["body"], "Coucou, tu fais quoi ce soir ?")
        self.assertEqual(self.other.get("/api/conversations").json()["conversations"], [])

    def test_text_import_deduplicates_overlapping_history(self):
        conversation = self.create()
        url = f"/api/conversations/{conversation['id']}"
        first = self.client.post(url + "/import-text", headers=HEADERS, json={"revision": 0, "messages": [
            {"sender": "me", "body": "Salut"}, {"sender": "other", "body": "Coucou"}]})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["added"], 2)
        second = self.client.post(url + "/import-text", headers=HEADERS, json={"revision": 1, "messages": [
            {"sender": "me", "body": "Salut"}, {"sender": "other", "body": "Coucou"},
            {"sender": "other", "body": "Ça va ?"}]})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["added"], 1)
        self.assertEqual(len(second.json()["conversation"]["messages"]), 3)
        repeated = self.client.post(url + "/import-text", headers=HEADERS, json={"revision": 2, "messages": [
            {"sender": "other", "body": "Ça va ?"}, {"sender": "other", "body": "Ça va ?"}]})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["added"], 1)
        stale = self.client.post(url + "/import-text", headers=HEADERS,
                                 json={"revision": 1, "messages": [{"sender": "other", "body": "Encore"}]})
        self.assertEqual(stale.status_code, 409)

    def test_image_import_extracts_bubbles_and_does_not_store_image(self):
        conversation = self.create()
        picture = io.BytesIO()
        Image.new("RGB", (100, 60), "white").save(picture, format="PNG")
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps({"context_clear": True, "messages": [
                       {"sender": "me", "body": "Salut"}, {"sender": "other", "body": "Oui salut"}]})):
            response = self.client.post(f"/api/conversations/{conversation['id']}/import-image", headers=HEADERS,
                                        files={"file": ("chat.png", picture.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["added"], 2)
        self.assertEqual(len(response.json()["conversation"]["messages"]), 2)
        self.assertEqual(self.other.get(f"/api/conversations/{conversation['id']}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
