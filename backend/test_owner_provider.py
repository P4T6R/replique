"""Hosted-owner contract with synthetic encrypted credentials and provider calls."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx

from backend.accounts import create_invitation
from backend.app import app
from backend.oauth import Session, load_persistent_session, oauth, save_persistent_session
from backend.operations import report
from backend.owner_provider import unavailable
from backend.test_app import BASE_REQUEST, PROVIDER_ANSWER

ORIGIN = "https://replique.duckdns.org"
HEADERS = {"Origin": ORIGIN, "X-Replique-Request": "1"}


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
                   return_value=json.dumps(PROVIDER_ANSWER)) as stream:
            response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["mode"], "hosted")
        self.assertNotIn("private-owner@example.test", response.text)
        self.assertEqual(stream.await_args.args[0:2], ("owner-browser", "owner-model"))
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        with patch("backend.owner_provider.stream_text", new_callable=AsyncMock,
                   side_effect=HTTPException(429, "quota reached")):
            self.assertEqual(self.generate().status_code, 503)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        self.assertEqual(report(1)["outcomes"], {"success": 1, "quota": 1})

    def test_server_model_must_be_selected_before_opening(self):
        self.provision()
        with patch.dict(os.environ, {"REPLIQUE_MODEL": ""}):
            self.assertEqual(self.client.get("/api/health").status_code, 503)
            self.register()
            self.assertEqual(self.generate().status_code, 503)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)
        self.assertEqual(report(1)["outcomes"], {"configuration": 1})

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
                    "delta": json.dumps(PROVIDER_ANSWER)}) + "\n\n"
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
