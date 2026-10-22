"""Mock-only security/protocol tests; never call OpenAI or read credentials."""
import asyncio
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, AsyncMock
from urllib.parse import parse_qs, urlsplit
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import app
from backend.oauth import (OAuth, Pending, Session, COOKIE, ISSUER, RESOURCE, oauth,
                           CredentialStoreError, save_persistent_session, load_persistent_session, delete_persistent_session)
from backend.chatgpt_provider import stream_text, catalog, MAX_MODEL_CATALOG

ORIGIN = "http://127.0.0.1:8000"
HEADERS = {"Origin": ORIGIN, "X-Replique-Request": "1"}


class AuthRoutes(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"REPLIQUE_OAUTH_ENABLED": "1", "REPLIQUE_DATA_DIR": self.directory.name})
        self.env.start()
        oauth.pending = oauth.session = oauth.registration = oauth.error = None
        oauth.lock = asyncio.Lock()
        oauth.generations.clear()
        self.client = TestClient(app, base_url=ORIGIN)
    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.directory.cleanup()
        oauth.pending = oauth.session = oauth.registration = oauth.error = None
    def begin(self):
        response = self.client.post("/api/auth/login", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=31536000", response.headers["set-cookie"])
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        return parse_qs(urlsplit(response.json()["authorization_url"]).query)
    def test_login_pkce_scopes_cookie_host_stability(self):
        params = self.begin()
        self.assertEqual(params["client_id"], ["dynamic_agent_client"])
        self.assertEqual(params["resource"], [RESOURCE])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["redirect_uri"], [ORIGIN + "/api/auth/callback"])
        self.assertIn("chatgpt.tokens.use.direct", params["scope"][0])
        first = params["ext_agent_host_id"]
        self.client.post("/api/auth/logout", headers=HEADERS)
        self.assertEqual(self.begin()["ext_agent_host_id"], first)
    def test_valid_callback_persists_only_registration_and_reuses_after_restart(self):
        params = self.begin()
        tokens = {"id_token": "fake-id", "access_token": "secret-access", "refresh_token": "secret-refresh", "token_type": "Bearer", "expires_in": 3600, "scope": "openid resource.invoke chatgpt.tokens.use.direct"}
        stored_session = {}
        def save_session(session):
            stored_session.update({"browser": session.browser, "client_id": session.client_id, "subject": session.subject,
                                   "email": session.email, "refresh": session.refresh, "scopes": set(session.scopes)})
        def load_session(browser):
            if not stored_session or stored_session["browser"] != browser:
                return None
            return Session(browser, stored_session["client_id"], stored_session["subject"], stored_session["email"],
                           "", stored_session["refresh"], stored_session["scopes"], 0)
        with patch.object(oauth, "json_request", new_callable=AsyncMock, return_value=tokens), \
             patch.object(oauth, "validate_identity", new_callable=AsyncMock, return_value={"sub": "verified-sub", "email": "test@example.invalid"}), \
             patch("backend.oauth.save_persistent_session", side_effect=save_session), \
             patch("backend.oauth.load_persistent_session", side_effect=load_session):
            result = self.client.get("/api/auth/callback", params={"state": params["state"][0], "code": "mock-code", "client_id": "oaiapp_test"}, follow_redirects=False)
            self.assertEqual(result.headers["location"], "/?auth=connected")
            self.assertEqual(self.client.get("/api/auth/status").json()["status"], "connected")
            from pathlib import Path
            stored = (Path(self.directory.name) / "registration.json").read_text()
            self.assertEqual(json.loads(stored), {"client_id": "oaiapp_test", "subject": "verified-sub"})
            self.assertNotIn("secret", stored)
            self.assertEqual(stored_session["refresh"], "secret-refresh")
            oauth.session = oauth.pending = oauth.registration = None
            self.assertEqual(self.client.get("/api/auth/status").json()["status"], "connected")
            self.assertEqual(oauth.session.access if oauth.session else None, "")
            self.assertNotIn("access", stored_session)
            oauth.session = oauth.pending = oauth.registration = None
            restored = self.begin()
            self.assertEqual(restored["client_id"], ["oaiapp_test"])
            self.assertNotIn("agent_name_hint", restored)

    def test_chatgpt_generation_requires_consent_and_validates_output(self):
        from backend.test_app import BASE_REQUEST, PROVIDER_ANSWER
        with patch.dict(os.environ, {"REPLIQUE_MODE": "chatgpt"}), patch("backend.app.stream_text", new_callable=AsyncMock, return_value=json.dumps(PROVIDER_ANSWER)) as stream:
            denied = self.client.post("/api/generate", headers=HEADERS, json={**BASE_REQUEST, "model": "test"})
            self.assertEqual(denied.status_code, 403)
            stream.assert_not_called()
            accepted = self.client.post("/api/generate", headers=HEADERS, json={**BASE_REQUEST, "model": "test", "consent": True})
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.json()["mode"], "chatgpt")
            stream.return_value = "partial invalid JSON"
            malformed = self.client.post("/api/generate", headers=HEADERS, json={**BASE_REQUEST, "model": "test", "consent": True})
            self.assertEqual(malformed.status_code, 502)


    def test_login_disabled(self):
        with patch.dict(os.environ, {"REPLIQUE_OAUTH_ENABLED": "0"}):
            self.assertEqual(self.client.post("/api/auth/login", headers=HEADERS).status_code, 503)
    def test_login_requires_exact_origin_and_header(self):
        for headers in ({}, {"Origin": ORIGIN}, {"Origin": "https://evil.example", "X-Replique-Request": "1"}):
            self.assertEqual(self.client.post("/api/auth/login", headers=headers).status_code, 403)
    def test_repeated_login_no_new_attempt(self):
        self.begin()
        pending = oauth.pending
        self.assertEqual(self.client.post("/api/auth/login", headers=HEADERS).status_code, 409)
        self.assertIs(oauth.pending, pending)
    def test_wrong_state_no_exchange(self):
        self.begin()
        with patch.object(oauth, "json_request", new_callable=AsyncMock) as exchange:
            response = self.client.get("/api/auth/callback?state=wrong&code=anything", follow_redirects=False)
            self.assertEqual(response.status_code, 400)
            exchange.assert_not_called()
    def test_unicode_state_rejected_cleanly(self):
        self.begin()
        self.assertEqual(self.client.get("/api/auth/callback", params={"state": "é", "code": "fake"}).status_code, 400)

    def test_wrong_browser_no_exchange(self):
        params = self.begin()
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/auth/callback", params={"state": params["state"][0], "code": "a"}).status_code, 400)
    def test_consent_declined_cross_site_navigation_allowed_one_shot(self):
        params = self.begin()
        response = self.client.get("/api/auth/callback", params={"state": params["state"][0], "error": "access_denied"},
            headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(oauth.error["code"], "consent_declined")
        self.assertIsNone(oauth.pending)
        self.assertEqual(self.client.get("/api/auth/callback", params={"state": params["state"][0]}).status_code, 400)
    def test_duplicate_callback_rejected(self):
        params = self.begin()
        response = self.client.get("/api/auth/callback?state=" + params["state"][0] + "&code=a&code=b", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(oauth.error["code"], "invalid_callback")
    def test_expired_status_not_connecting(self):
        self.begin()
        oauth.pending.expires = time.time() - 1
        self.assertEqual(self.client.get("/api/auth/status").json()["status"], "disconnected")
    def test_logout_does_not_claim_remote_revocation(self):
        self.begin()
        oauth.session = Session(oauth.pending.browser, "issued", "sub", "mail", "secret", "refresh", {"chatgpt.tokens.use.direct"}, time.time()+300)
        oauth.pending = None
        with patch.object(oauth, "metadata", new_callable=AsyncMock, side_effect=httpx.ConnectError("offline")), \
             patch("backend.oauth.delete_persistent_session") as delete_store:
            response = self.client.post("/api/auth/logout", headers=HEADERS)
        self.assertFalse(response.json()["remote_revoked"])
        delete_store.assert_called_once_with()
        self.assertIsNone(oauth.session)
        self.assertNotIn(COOKIE, self.client.cookies)


class EncryptedCredentialStore(unittest.TestCase):
    def test_encrypted_refresh_token_survives_restart_and_rejects_wrong_key(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "credential.key"
            key_path.write_bytes(Fernet.generate_key())
            environment = {"REPLIQUE_DATA_DIR": directory, "REPLIQUE_CREDENTIAL_KEY_FILE": str(key_path)}
            with patch.dict(os.environ, environment):
                session = Session("browser-id", "issued-client", "subject", None, "access-secret",
                                  "refresh-secret", {"openid", "resource.invoke"}, time.time() + 3600)
                save_persistent_session(session)
                encrypted_path = Path(directory) / "oauth-session.enc"
                encrypted = encrypted_path.read_bytes()
                self.assertNotIn(b"refresh-secret", encrypted)
                self.assertNotIn(b"access-secret", encrypted)
                restored = load_persistent_session("browser-id")
                self.assertEqual(restored.refresh, "refresh-secret")
                self.assertEqual(restored.access, "")
                self.assertIsNone(load_persistent_session("other-browser"))
                key_path.write_bytes(Fernet.generate_key())
                with self.assertRaises(CredentialStoreError):
                    load_persistent_session("browser-id")
                delete_persistent_session()
                self.assertFalse(encrypted_path.exists())


@unittest.skipUnless(os.name == "nt", "Windows DPAPI is unavailable")
class ProtectedCredentialStore(unittest.TestCase):
    def test_refresh_token_is_protected_and_survives_process_restart(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"REPLIQUE_DATA_DIR": directory}):
            session = Session("browser-id", "issued-client", "subject", "test@example.invalid", "access-secret",
                              "refresh-secret", {"openid", "resource.invoke", "chatgpt.tokens.use.direct"}, time.time() + 3600)
            save_persistent_session(session)
            path = __import__("pathlib").Path(directory) / "oauth-session.dpapi"
            protected = path.read_bytes()
            self.assertNotIn(b"refresh-secret", protected)
            self.assertNotIn(b"access-secret", protected)
            restored = load_persistent_session("browser-id")
            self.assertEqual(restored.refresh, "refresh-secret")
            self.assertEqual(restored.access, "")
            self.assertEqual(restored.expires, 0)
            self.assertIsNone(load_persistent_session("different-browser"))
            delete_persistent_session()
            self.assertFalse(path.exists())


class CryptoAndTransport(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"REPLIQUE_OAUTH_ENABLED": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.auth = OAuth()
        self.pending = Pending("state", "nonce", "verifier", ORIGIN+"/api/auth/callback", "browser", "issued", None)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid="test", use="sig")
        self.claims = {"iss": ISSUER, "aud": "issued", "sub": "subject", "iat": int(time.time()), "exp": int(time.time())+300, "nonce": "nonce"}
    async def validate(self, claims=None, key=None):
        token = jwt.encode(claims or self.claims, key or self.key, algorithm="RS256", headers={"kid": "test"})
        with patch.object(self.auth, "metadata", new_callable=AsyncMock, return_value={"jwks_uri": ISSUER+"/jwks"}), patch.object(self.auth, "json_request", new_callable=AsyncMock, return_value={"keys": [self.jwk]}):
            return await self.auth.validate_identity(token, self.pending, "issued")
    async def test_signed_identity_verified(self):
        self.assertEqual((await self.validate())["sub"], "subject")
    async def test_bad_issuer_audience_nonce_expiry_and_subject_rejected(self):
        for key, value in [("iss", "https://evil.example"), ("aud", "wrong"), ("nonce", "wrong"), ("exp", 1)]:
            with self.subTest(key=key), self.assertRaises(HTTPException):
                await self.validate({**self.claims, key: value})
        self.pending.subject = "other"
        with self.assertRaises(HTTPException):
            await self.validate()
    async def test_forged_signature_rejected(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(HTTPException):
            await self.validate(key=key)
    async def test_missing_usage_scope_rejected(self):
        with self.assertRaises(HTTPException):
            self.auth.tokens({"access_token":"a","refresh_token":"r","token_type":"Bearer","expires_in":300,"scope":"openid profile"})
    async def test_malformed_token_types_rejected(self):
        for key, value in [("scope",[]),("token_type",{}),("expires_in",True),("access_token",None)]:
            with self.subTest(key=key), self.assertRaises(HTTPException):
                self.auth.tokens({"access_token":"a","refresh_token":"r","token_type":"Bearer","expires_in":300,"scope":"openid resource.invoke chatgpt.tokens.use.direct",key:value})
    async def test_refresh_singleflight_and_rotation(self):
        self.auth.session = Session("browser","issued","subject",None,"old","r1",{"openid","resource.invoke","chatgpt.tokens.use.direct"},0)
        with patch.object(self.auth,"json_request",new_callable=AsyncMock,return_value={"access_token":"new","refresh_token":"r2","token_type":"Bearer","expires_in":3600}) as refresh, \
             patch("backend.oauth.save_persistent_session") as save_session:
            self.assertEqual(await asyncio.gather(self.auth.access("browser"),self.auth.access("browser")),["new","new"])
            self.assertEqual(refresh.await_count,1)
            self.assertEqual(save_session.call_count,1)
            self.assertEqual(self.auth.session.refresh,"r2")
    async def test_model_catalog_uses_larger_bounded_response_limit(self):
        entries = [{"slug": "test-model", "display_name": "Test model", "visibility": "list"}]
        with patch.object(oauth, "access", new_callable=AsyncMock, return_value="mock-token"), \
             patch.object(oauth, "json_request", new_callable=AsyncMock, return_value={"models": entries}) as request:
            result = await catalog("browser")
        self.assertEqual(result, [{"slug": "test-model", "display_name": "Test model"}])
        request.assert_awaited_once_with("GET", RESOURCE + "/models", max_bytes=MAX_MODEL_CATALOG,
                                         headers={"Authorization": "Bearer mock-token"})
    async def stream(self, events, content_type="text/event-stream"):
        requests=[]
        def handler(request):
            requests.append(request)
            headers={"Content-Type":content_type} if content_type else {}
            body="".join("data: "+json.dumps(event)+"\n\n" for event in events).encode()
            return httpx.Response(200,headers=headers,content=body)
        with patch("backend.chatgpt_provider.catalog",new_callable=AsyncMock,return_value=[{"slug":"test","display_name":"Test"}]), patch.object(oauth,"access",new_callable=AsyncMock,return_value="mock-secret"), patch("backend.chatgpt_provider.client",side_effect=lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler))):
            result=await stream_text("browser","test","instructions","user")
        return result,requests
    async def test_responses_contract_and_completion(self):
        text,requests=await self.stream([{"type":"response.output_text.delta","delta":"ok"},{"type":"response.completed","response":{"status":"completed"}}])
        self.assertEqual(text,"ok")
        request=requests[0]
        self.assertEqual(str(request.url),RESOURCE+"/responses")
        self.assertEqual(request.headers["authorization"],"Bearer mock-secret")
        payload=json.loads(request.content)
        self.assertIs(payload["store"],False)
        self.assertIs(payload["stream"],True)
        self.assertFalse({"temperature","max_output_tokens","previous_response_id","messages"} & payload.keys())
    async def test_valid_stream_without_content_type(self):
        text,_=await self.stream([{"type":"response.output_text.delta","delta":"ok"},
                                  {"type":"response.completed","response":{"status":"completed"}}], content_type="")
        self.assertEqual(text,"ok")
    async def test_incomplete_stream_without_content_type_is_rejected(self):
        with self.assertRaises(HTTPException):
            await self.stream([{"type":"response.output_text.delta","delta":"partial"}], content_type="")
    async def test_partial_failed_and_incomplete_never_success(self):
        for terminal in (None,{"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}},{"type":"response.incomplete"},{"type":"response.completed","response":{"status":"incomplete"}}):
            events=[{"type":"response.output_text.delta","delta":"partial"}]
            if terminal: events.append(terminal)
            with self.subTest(terminal=terminal),self.assertRaises(HTTPException):
                await self.stream(events)
