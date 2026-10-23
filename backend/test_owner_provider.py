"""Hosted-owner contract with synthetic encrypted credentials and provider calls."""

import asyncio
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
from PIL import Image

from backend.accounts import create_invitation
from backend.app import app
from backend.oauth import Session, load_persistent_session, oauth, save_persistent_session
from backend.operations import report
from backend.owner_provider import OwnerProviderError, unavailable
from backend.test_app import BASE_REQUEST, PROVIDER_ANSWER, image_bytes, heic_bytes

ORIGIN = "https://replique.duckdns.org"
HEADERS = {"Origin": ORIGIN, "X-Replique-Request": "1"}
HOSTED_TEXT_ANSWER = {**PROVIDER_ANSWER, "sparse_followup": False}


class OwnerProviderTests(unittest.TestCase):
    def test_stream_limit_event_has_private_quota_category(self):
        error = HTTPException(502, {"code": "subscription_sharing_usage_limit_exceeded"})
        classified = unavailable(error)
        self.assertEqual(classified.reason, "quota")
        self.assertEqual(classified.status_code, 503)

    def setUp(self):
        self.private = tempfile.TemporaryDirectory()
        self.key = Path(self.private.name) / "credential.key"
        self.key.write_bytes(Fernet.generate_key())
        self.key.chmod(0o600)
        self.environment = patch.dict(os.environ, {
            "REPLIQUE_MODE": "owner_chatgpt", "REPLIQUE_PUBLIC_ORIGIN": ORIGIN,
            "REPLIQUE_OAUTH_ENABLED": "1", "REPLIQUE_DATA_DIR": self.private.name,
            "REPLIQUE_CREDENTIAL_KEY_FILE": str(self.key), "REPLIQUE_MODEL": "owner-model",
        })
        self.environment.start()
        self.previous = (oauth.session, oauth.error, oauth.lock)
        oauth.session = oauth.error = None
        oauth.lock = asyncio.Lock()
        self.client = TestClient(app, base_url=ORIGIN)

    def tearDown(self):
        self.client.close()
        oauth.session, oauth.error, oauth.lock = self.previous
        self.environment.stop()
        self.private.cleanup()

    def provision(self):
        save_persistent_session(Session("owner-browser", "issued-client", "owner-sub",
            "private-owner@example.test", "", "synthetic-refresh",
            {"openid", "resource.invoke", "chatgpt.tokens.use.direct"}, 0))

    def register(self):
        response = self.client.post("/api/account/register", headers=HEADERS, json={
            "email": "visitor@example.test", "password": "a long visitor password",
            "invitation": create_invitation(),
        })
        self.assertEqual(response.status_code, 200, response.text)

    def generate(self):
        return self.client.post("/api/generate", headers=HEADERS,
                                json={**BASE_REQUEST, "consent": True, "model": "visitor-cannot-select"})

    def test_owner_session_is_private_and_meters_only_success(self):
        self.provision()
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["mode"], "hosted")
        self.assertNotIn("private-owner@example.test", health.text)
        self.assertEqual(self.client.get("/api/auth/status").status_code, 403)
        self.assertEqual(self.generate().status_code, 401)
        self.register()
        with patch("backend.owner_provider.stream_text", new_callable=AsyncMock,
                   return_value=json.dumps(HOSTED_TEXT_ANSWER)) as stream:
            response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["mode"], "hosted")
        self.assertNotIn("private-owner@example.test", response.text)
        self.assertEqual(stream.await_args.args[0:2], ("owner-browser", "owner-model"))
        self.assertIn("LIEN ET CONVERSATION", stream.await_args.args[2])
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        with patch("backend.owner_provider.stream_text", new_callable=AsyncMock,
                   side_effect=HTTPException(429, "quota reached")):
            self.assertEqual(self.generate().status_code, 503)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        self.assertEqual(report(1)["outcomes"], {"success": 1, "quota": 1})

    def test_sparse_text_followup_returns_one_reply_and_one_credit(self):
        self.provision()
        self.register()
        answer = {"sparse_followup": True,
                  "insight": "Les nouvelles ont déjà été échangées ; aucun autre sujet concret n'est visible.",
                  "replies": [{"title": "Simple", "text": "Quoi de neuf depuis la dernière fois ?",
                               "why": "Une ouverture courte, sans supposer ses activités."}]}
        payload = {**BASE_REQUEST, "conversation": "Autre personne : Ça va merci.\nMoi : Tant mieux !",
                   "intent": "relancer", "consent": True}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps(answer)) as provider:
            response = self.client.post("/api/generate", headers=HEADERS, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["replies"]), 1)
        self.assertIn("Proposition générée", response.json()["notice"])
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        self.assertIn("RÈGLE PRIORITAIRE POUR LE TEXTE HÉBERGÉ", provider.await_args.args[0])
        self.assertIn("ANTI-RÉPÉTITION PRIORITAIRE", provider.await_args.args[0])

    def test_sparse_text_followup_rejects_three_replies_without_charging(self):
        self.provision()
        self.register()
        answer = {**PROVIDER_ANSWER, "sparse_followup": True}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps(answer)):
            response = self.client.post("/api/generate", headers=HEADERS,
                                        json={**BASE_REQUEST, "intent": "relancer", "consent": True})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_server_model_must_be_selected_before_opening(self):
        self.provision()
        with patch.dict(os.environ, {"REPLIQUE_MODEL": ""}):
            self.assertEqual(self.client.get("/api/health").status_code, 503)
            self.register()
            self.assertEqual(self.generate().status_code, 503)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)
        self.assertEqual(report(1)["outcomes"], {"configuration": 1})

    def test_hosted_photo_uses_private_model_with_image_consent_and_keeps_credit(self):
        self.provision()
        self.register()
        upload = {"file": ("capture.png", image_bytes(), "image/png")}
        denied = self.client.post("/api/ocr", headers=HEADERS, files=upload)
        self.assertEqual(denied.status_code, 403)
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value="Autre personne : Bonjour") as vision:
            accepted = self.client.post("/api/ocr", headers=HEADERS, files=upload,
                                        data={"consent": "true", "model": "visitor-cannot-select"})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["text"], "Autre personne : Bonjour")
        self.assertEqual(accepted.json()["language"], "openai")
        self.assertTrue(vision.await_args.args[1][1]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)
        self.assertNotIn("private-owner@example.test", accepted.text)
        with Image.open(io.BytesIO(image_bytes())) as source:
            jpeg = io.BytesIO()
            source.convert("RGB").save(jpeg, format="JPEG")
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value="Autre personne : Salut"):
            photo = self.client.post("/api/ocr", headers=HEADERS,
                                     files={"file": ("photo.jpg", jpeg.getvalue(), "image/jpeg")},
                                     data={"consent": "true"})
        self.assertEqual(photo.status_code, 200, photo.text)
        self.assertEqual(photo.json()["text"], "Autre personne : Salut")

        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value="Autre personne : Salut depuis la photo") as vision:
            heic = self.client.post("/api/ocr", headers=HEADERS,
                                    files={"file": ("photo.HEIC", heic_bytes(), "application/octet-stream")},
                                    data={"consent": "true"})
        self.assertEqual(heic.status_code, 200, heic.text)
        self.assertTrue(vision.await_args.args[1][1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_direct_image_generation_uses_one_call_and_one_credit(self):
        self.provision()
        self.register()
        options = {"intent": "répondre naturellement", "tone": "naturel", "conversation": "Répondre avec douceur.",
                   "consent": True, "context_confirmed": True}
        upload = {"file": ("capture.png", image_bytes(), "image/png")}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps({**PROVIDER_ANSWER, "context_clear": True, "sparse_followup": False})) as vision:
            response = self.client.post("/api/generate-image", headers=HEADERS, files=upload,
                                        data={"options": json.dumps(options)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["mode"], "hosted")
        self.assertNotIn("OpenAI", response.text)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        vision.assert_awaited_once()
        self.assertIn('QUALITÉ CONVERSATIONNELLE', vision.await_args.args[0])
        self.assertIn('LIEN ET CONVERSATION', vision.await_args.args[0])
        self.assertIn('RELANCE APRÈS UNE RÉPONSE ENVOYÉE', vision.await_args.args[0])
        content = vision.await_args.args[1]
        self.assertEqual(len(content), 2)
        self.assertEqual(content[1]["type"], "input_image")
        self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(json.loads(content[0]["text"])["note"], "Répondre avec douceur.")
        self.assertIsInstance(date.fromisoformat(json.loads(content[0]["text"])["current_date_utc"]), date)

    def test_sparse_photo_followup_returns_one_natural_suggestion(self):
        self.provision()
        self.register()
        options = {"intent": "relancer", "tone": "léger", "conversation": "Son prénom est Audrey.",
                   "consent": True, "context_confirmed": True}
        answer = {"context_clear": True, "sparse_followup": True,
                  "insight": "Les nouvelles ont déjà été échangées ; aucun autre sujet concret n'est visible.",
                  "replies": [{"title": "Simple", "text": "Salut Audrey, quoi de neuf ?",
                               "why": "Une reprise légère, sans insister."}]}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps(answer)) as vision:
            response = self.client.post("/api/generate-image", headers=HEADERS,
                                        files={"file": ("capture.png", image_bytes(), "image/png")},
                                        data={"options": json.dumps(options)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["replies"]), 1)
        self.assertEqual(response.json()["replies"][0]["text"], "Salut Audrey, quoi de neuf ?")
        self.assertIn("Proposition générée", response.json()["notice"])
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        self.assertIn("sparse_followup", vision.await_args.args[0])

    def test_sparse_photo_followup_rejects_three_filler_replies_without_charging(self):
        self.provision()
        self.register()
        answer = {**PROVIDER_ANSWER, "context_clear": True, "sparse_followup": True}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps(answer)):
            response = self.client.post("/api/generate-image", headers=HEADERS,
                                        files={"file": ("capture.png", image_bytes(), "image/png")},
                                        data={"options": json.dumps({"intent": "relancer", "consent": True,
                                                                     "context_confirmed": True})})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_direct_image_requires_consent_and_releases_credit_on_uncertainty(self):
        self.provision()
        self.register()
        upload = {"file": ("capture.png", image_bytes(), "image/png")}
        options = {"intent": "répondre naturellement", "consent": False, "context_confirmed": False}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock) as vision:
            denied = self.client.post("/api/generate-image", headers=HEADERS, files=upload,
                                      data={"options": json.dumps(options)})
            self.assertEqual(denied.status_code, 403)
            vision.assert_not_called()
        options.update(consent=True, context_confirmed=True)
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps({**PROVIDER_ANSWER, "context_clear": False, "sparse_followup": False})):
            uncertain = self.client.post("/api/generate-image", headers=HEADERS, files=upload,
                                         data={"options": json.dumps(options)})
        self.assertEqual(uncertain.status_code, 422, uncertain.text)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_direct_image_blocks_foreign_origin_and_invalid_image(self):
        self.provision()
        self.register()
        options = json.dumps({"intent": "répondre naturellement", "consent": True, "context_confirmed": True})
        upload = {"file": ("capture.png", image_bytes(), "image/png")}
        foreign = self.client.post("/api/generate-image", headers={"Origin": "https://foreign.example", "X-Replique-Request": "1"},
                                   files=upload, data={"options": options})
        self.assertEqual(foreign.status_code, 403)
        invalid = self.client.post("/api/generate-image", headers=HEADERS,
                                   files={"file": ("fake.png", b"not an image", "image/png")}, data={"options": options})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_hosted_plain_message_needs_no_speaker_prefix(self):
        self.provision()
        self.register()
        payload = {**BASE_REQUEST, "conversation": "Tu viens samedi ?", "consent": True, "context_confirmed": True}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps(HOSTED_TEXT_ANSWER)) as provider:
            response = self.client.post("/api/generate", headers=HEADERS, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        sent = json.loads(provider.await_args.args[1])
        self.assertEqual(sent["messages"], [{"speaker": "other", "text": "Tu viens samedi ?"}])
        self.assertIn('QUALITÉ CONVERSATIONNELLE', provider.await_args.args[0])
    def test_hosted_photo_has_daily_limit_and_releases_credit_after_failure(self):
        self.provision()
        self.register()
        upload = {"file": ("capture.png", image_bytes(), "image/png")}
        with patch("backend.accounts.REQUEST_LIMITS", {"generate": 6, "ocr": 10, "ocr_daily": 1}), \
             patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   side_effect=OwnerProviderError("quota")):
            failure = self.client.post("/api/ocr", headers=HEADERS, files=upload,
                                       data={"consent": "true"})
            limited = self.client.post("/api/ocr", headers=HEADERS, files=upload,
                                       data={"consent": "true"})
        self.assertEqual(failure.status_code, 503)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_hosted_memory_is_private_to_each_account_and_only_sent_with_consent(self):
        self.provision()
        self.register()
        body = {"reply": "Salut, ça me ferait plaisir.", "intent": "répondre naturellement",
                "rating": "positive", "validated": True, "consent": True, "reviewed": True}
        saved = self.client.post("/api/memory/items", headers=HEADERS, json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        preview = self.client.get("/api/memory/preview", params={"intent": "répondre naturellement"},
                                  headers=HEADERS).json()
        self.assertEqual([item["id"] for item in preview["examples"]], [saved.json()["id"]])
        with TestClient(app, base_url=ORIGIN) as other:
            self.assertEqual(other.get("/api/memory", headers=HEADERS).status_code, 401)
            registered = other.post("/api/account/register", headers=HEADERS, json={
                "email": "other@example.test", "password": "another long visitor password",
                "invitation": create_invitation()})
            self.assertEqual(registered.status_code, 200, registered.text)
            self.assertEqual(other.get("/api/memory", headers=HEADERS).json()["items"], [])
            self.assertEqual(other.get("/api/memory/preview", headers=HEADERS,
                                       params={"intent": "répondre naturellement"}).json()["examples"], [])
            self.assertEqual(other.get("/api/memory/export", headers=HEADERS).json()["items"], [])
        payload = {**BASE_REQUEST, "intent": "répondre naturellement", "consent": False,
                   "use_memory": True, "memory_revision": preview["revision"]}
        with patch("backend.app.owner_generate_text", new_callable=AsyncMock,
                   return_value=json.dumps(HOSTED_TEXT_ANSWER)) as provider:
            self.assertEqual(self.client.post("/api/generate", headers=HEADERS, json=payload).status_code, 403)
            provider.assert_not_called()
            payload["consent"] = True
            answer = self.client.post("/api/generate", headers=HEADERS, json=payload)
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.json()["memory_used"]["item_ids"], [saved.json()["id"]])
        sent = json.loads(provider.await_args.args[1])
        self.assertEqual(sent["saved_context"]["examples"][0]["id"], saved.json()["id"])

    def test_codex_auth_file_does_not_activate_public_provider(self):
        (Path(self.private.name) / "auth.json").write_text('{"tokens":{"access_token":"fake"}}')
        self.assertEqual(self.client.get("/api/health").status_code, 503)
        self.register()
        self.assertEqual(self.generate().status_code, 503)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)

    def test_encrypted_session_refreshes_and_uses_responses(self):
        self.provision()
        self.register()
        paths = []

        def handler(request):
            paths.append(request.url.path)
            if request.url.path == "/api/accounts/oauth/token":
                self.assertIn(b"synthetic-refresh", request.content)
                return httpx.Response(200, json={"access_token": "renewed-access",
                    "refresh_token": "rotated-refresh", "scope": "openid resource.invoke chatgpt.tokens.use.direct",
                    "token_type": "Bearer", "expires_in": 3600})
            self.assertEqual(request.headers.get("authorization"), "Bearer renewed-access")
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"models": [{"slug": "owner-model",
                    "display_name": "Owner model", "visibility": "list"}]})
            if request.url.path == "/v1/responses":
                payload = json.loads(request.content)
                self.assertEqual(payload["model"], "owner-model")
                self.assertFalse(payload["store"])
                body = ("data: " + json.dumps({"type": "response.output_text.delta",
                    "delta": json.dumps(HOSTED_TEXT_ANSWER)}) + "\n\n"
                    + "data: " + json.dumps({"type": "response.completed",
                    "response": {"status": "completed"}}) + "\n\n")
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)
            raise AssertionError(request.url.path)

        transport = httpx.MockTransport(handler)
        factory = lambda: httpx.AsyncClient(transport=transport, trust_env=False)
        with patch("backend.oauth.client", side_effect=factory), \
             patch("backend.chatgpt_provider.client", side_effect=factory):
            response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["mode"], "hosted")
        self.assertEqual(paths.count("/api/accounts/oauth/token"), 1)
        self.assertEqual(paths.count("/v1/responses"), 1)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        self.assertEqual(load_persistent_session("", owner=True).refresh, "rotated-refresh")
