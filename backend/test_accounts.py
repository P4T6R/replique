"""Hosted beta contract with a simulated local model; no paid provider calls."""

import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException

from backend.accounts import create_invitation, database, reserve, finish
from backend.app import app
from backend.test_app import BASE_REQUEST, PROVIDER_ANSWER

ORIGIN = "https://replique.duckdns.org"
HEADERS = {"Origin": ORIGIN, "X-Replique-Request": "1"}


class ModelHandler(BaseHTTPRequestHandler):
    fail = False
    calls = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            self.reply(200, {"models": [{"name": "qwen2.5:3b"}]})
        else:
            self.reply(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        assert self.path == "/v1/chat/completions"
        assert payload["model"] == "qwen2.5:3b"
        assert payload["response_format"]["type"] == "json_schema"
        assert "Authorization" not in self.headers
        type(self).calls += 1
        if type(self).fail:
            self.reply(503, {"error": "offline"})
        else:
            self.reply(200, {"choices": [{"message": {"content": json.dumps(PROVIDER_ANSWER)}}]})

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.model = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        self.server = threading.Thread(target=self.model.serve_forever, daemon=True)
        self.server.start()
        ModelHandler.fail = False
        ModelHandler.calls = 0
        self.environment = patch.dict(os.environ, {
            "REPLIQUE_MODE": "local", "REPLIQUE_PUBLIC_ORIGIN": ORIGIN,
            "REPLIQUE_LOCAL_MODEL_URL": f"http://127.0.0.1:{self.model.server_port}/v1",
            "REPLIQUE_MODEL": "qwen2.5:3b", "REPLIQUE_DATA_DIR": self.data.name,
            "REPLIQUE_API_KEY": "",
        })
        self.environment.start()
        self.client = TestClient(app, base_url=ORIGIN)

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        self.model.shutdown()
        self.model.server_close()
        self.server.join(timeout=2)
        self.data.cleanup()

    def register(self, email="first@example.test"):
        code = create_invitation()
        response = self.client.post("/api/account/register", headers=HEADERS,
                                    json={"email": email, "password": "a long beta password", "invitation": code})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Secure", response.headers["set-cookie"])
        return code

    def generate(self):
        return self.client.post("/api/generate", headers=HEADERS, json={**BASE_REQUEST, "consent": True})

    def test_trial_charges_only_success_and_stops_at_twenty(self):
        self.assertEqual(self.client.get("/api/health").json()["mode"], "local")
        code = self.register()
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)
        duplicate = self.client.post("/api/account/register", headers=HEADERS,
                                     json={"email": "other@example.test", "password": "a long beta password", "invitation": code})
        self.assertEqual(duplicate.status_code, 403)
        ModelHandler.fail = True
        self.assertEqual(self.generate().status_code, 502)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 20)
        ModelHandler.fail = False
        for remaining in range(19, -1, -1):
            result = self.generate()
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["mode"], "local")
            self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], remaining)
        self.assertEqual(self.generate().status_code, 402)
        self.assertEqual(ModelHandler.calls, 21)

    def test_public_routes_require_account_origin_and_keep_memory_private(self):
        self.assertEqual(self.generate().status_code, 401)
        self.assertEqual(self.client.get("/api/memory").status_code, 403)
        self.assertEqual(self.client.get("/api/auth/status").status_code, 403)
        self.assertEqual(self.client.post("/api/account/register", json={}).status_code, 403)
        self.assertEqual(self.client.get("/api/health", headers={"Host": "evil.example"}).status_code, 403)
        self.register()
        self.assertEqual(self.client.get("/api/account/status").status_code, 200)
        self.assertEqual(self.client.post("/api/account/logout", headers=HEADERS).status_code, 200)
        self.assertEqual(self.client.get("/api/account/status").status_code, 401)

    def test_accounts_have_independent_balances_and_password_login(self):
        self.register()
        self.assertEqual(self.generate().status_code, 200)
        with TestClient(app, base_url=ORIGIN) as second:
            response = second.post("/api/account/register", headers=HEADERS, json={
                "email": "second@example.test", "password": "second long password",
                "invitation": create_invitation(),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(second.get("/api/account/status").json()["trial_remaining"], 20)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 19)
        self.client.post("/api/account/logout", headers=HEADERS)
        self.assertEqual(self.client.get("/api/account/status").status_code, 401)
        login = self.client.post("/api/account/login", headers=HEADERS,
                                 json={"email": "first@example.test", "password": "a long beta password"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["trial_remaining"], 19)

    def test_reservations_prevent_parallel_overspend(self):
        self.register()
        with database() as db:
            account = db.execute("SELECT id FROM accounts WHERE email=?", ("first@example.test",)).fetchone()
        def attempt(_):
            try:
                return reserve(account["id"])
            except Exception as error:
                return error
        with ThreadPoolExecutor(max_workers=8) as pool:
            attempts = list(pool.map(attempt, range(25)))
        reservations = [item for item in attempts if isinstance(item, str)]
        self.assertEqual(len(reservations), 20)
        self.assertTrue(all(isinstance(item, HTTPException) and item.status_code == 402
                            for item in attempts if not isinstance(item, str)))
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 0)
        self.assertEqual(self.generate().status_code, 402)
        finish(reservations[0], False)
        self.assertEqual(self.client.get("/api/account/status").json()["trial_remaining"], 1)
        for reservation in reservations[1:]:
            finish(reservation, False)
