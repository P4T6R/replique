"""Local SIWC public-client flow. Credentials exist only in process memory.

Independent implementation of OpenAI's published protocol; no devkit code.
One browser session, one worker. No auth/network operation at module import.
"""
from __future__ import annotations
import asyncio
import base64
import ctypes
import hashlib
import json
import os
import secrets
import time
import tempfile
import uuid
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
COOKIE = "replique_session"
MAX_JSON_RESPONSE = 128 * 1024
SESSION_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
CREDENTIAL_MAX_BYTES = 16 * 1024
CREDENTIAL_ENTROPY = b"Replique OAuth session v1"
KEYRING_SERVICE = "Replique"
KEYRING_USERNAME = "chatgpt-oauth-session-v1"
router = APIRouter(prefix="/api/auth")


class CredentialStoreError(Exception):
    """The operating-system-protected credential store is unavailable."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("DPAPI is only available on Windows.")
    data_buffer = ctypes.create_string_buffer(data)
    entropy_buffer = ctypes.create_string_buffer(CREDENTIAL_ENTROPY)
    source = _DataBlob(len(data), ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_byte)))
    entropy = _DataBlob(len(CREDENTIAL_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_byte)))
    result = _DataBlob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(result)):
        raise CredentialStoreError("Windows could not access the protected local session.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        local_free = ctypes.WinDLL("kernel32", use_last_error=True).LocalFree
        local_free.argtypes = [ctypes.c_void_p]
        local_free.restype = ctypes.c_void_p
        local_free(ctypes.cast(result.pbData, ctypes.c_void_p))


def _keyring_backend():
    try:
        import keyring
        backend = keyring.get_keyring()
    except Exception as exc:
        raise CredentialStoreError("No operating-system credential store is available.") from exc
    module = type(backend).__module__
    allowed = ("keyring.backends.SecretService", "keyring.backends.macOS", "keyring.backends.Windows",
               "keyring.backends.kwallet", "keyring.backends.libsecret")
    if not any(module.startswith(prefix) for prefix in allowed):
        raise CredentialStoreError("The selected credential backend is not an operating-system keychain.")
    return keyring


def _credential_path() -> Path:
    return Path(os.getenv("REPLIQUE_DATA_DIR", str(Path.home() / ".local/share/replique"))) / "oauth-session.dpapi"


def _encrypted_credential_path() -> Path:
    return _credential_path().with_suffix(".enc")


def _file_cipher():
    configured = os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE", "")
    key_path = Path(configured)
    if not configured or not key_path.is_absolute() or key_path.is_symlink():
        raise CredentialStoreError("A protected absolute credential key file is required.")
    try:
        key = key_path.read_bytes()
        if len(key) != 44:
            raise ValueError()
        return Fernet(key)
    except (OSError, ValueError) as exc:
        raise CredentialStoreError("The protected credential key is unavailable or invalid.") from exc


def _save_encrypted_session(raw: bytes):
    path = _encrypted_credential_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise CredentialStoreError("The protected credential path is invalid.")
    fd, temporary = tempfile.mkstemp(prefix=".oauth-session-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(_file_cipher().encrypt(raw))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _credential_record(session) -> bytes:
    record = {"version": 1, "browser": session.browser, "client_id": session.client_id,
              "subject": session.subject, "email": session.email, "refresh": session.refresh,
              "scopes": sorted(session.scopes)}
    raw = json.dumps(record, separators=(",", ":")).encode("utf-8")
    if len(raw) > CREDENTIAL_MAX_BYTES:
        raise CredentialStoreError("The protected local session is too large.")
    return raw


def save_persistent_session(session):
    raw = _credential_record(session)
    if os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE"):
        _save_encrypted_session(raw)
        return
    if os.name == "nt":
        path = _credential_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".oauth-session-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(_dpapi(raw, decrypt=False))
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return
    try:
        _keyring_backend().set_password(KEYRING_SERVICE, KEYRING_USERNAME, raw.decode("utf-8"))
    except CredentialStoreError:
        raise
    except Exception as exc:
        raise CredentialStoreError("The operating-system credential store could not save the session.") from exc


def load_persistent_session(browser, *, owner=False):
    if owner and not os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE"):
        raise CredentialStoreError("A protected owner credential key file is required.")
    if os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE"):
        path = _encrypted_credential_path()
        if path.is_symlink() or path.parent.is_symlink():
            raise CredentialStoreError("The protected credential path is invalid.")
        try:
            encrypted = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CredentialStoreError("The protected session could not be read.") from exc
        if not encrypted or len(encrypted) > CREDENTIAL_MAX_BYTES * 4:
            raise CredentialStoreError("The protected session is invalid.")
        try:
            raw = _file_cipher().decrypt(encrypted)
        except InvalidToken as exc:
            raise CredentialStoreError("The protected session could not be decrypted.") from exc
    elif os.name == "nt":
        path = _credential_path()
        try:
            encrypted = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CredentialStoreError("The protected local session could not be read.") from exc
        if not encrypted or len(encrypted) > CREDENTIAL_MAX_BYTES * 4:
            raise CredentialStoreError("The protected local session is invalid.")
        raw = _dpapi(encrypted, decrypt=True)
    else:
        try:
            serialized = _keyring_backend().get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except CredentialStoreError:
            raise
        except Exception as exc:
            raise CredentialStoreError("The operating-system credential store could not read the session.") from exc
        if serialized is None:
            return None
        raw = serialized.encode("utf-8")
    if len(raw) > CREDENTIAL_MAX_BYTES:
        raise CredentialStoreError("The protected local session is invalid.")
    try:
        record = json.loads(raw)
        if (record.get("version") != 1 or not isinstance(record.get("browser"), str) or not record["browser"]
                or (not owner and not safe_equal(record["browser"], browser or ""))
                or not all(isinstance(record.get(key), str) and record[key]
                           for key in ("client_id", "subject", "refresh"))
                or (record.get("email") is not None and not isinstance(record["email"], str))
                or not isinstance(record.get("scopes"), list)
                or not all(isinstance(scope, str) for scope in record["scopes"])):
            return None
        return Session(record["browser"] if owner else browser, record["client_id"], record["subject"], record["email"], "",
                       record["refresh"], set(record["scopes"]), 0)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise CredentialStoreError("The protected local session is invalid.") from exc


def delete_persistent_session():
    if os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE"):
        try:
            _encrypted_credential_path().unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise CredentialStoreError("The protected session could not be deleted.") from exc
        return
    if os.name == "nt":
        try:
            _credential_path().unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise CredentialStoreError("The protected local session could not be deleted.") from exc
        return
    try:
        _keyring_backend().delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception as exc:
        # The key may already be absent; only the OS keyring's explicit missing
        # credential exception should be ignored by its caller.
        if type(exc).__name__ not in {"PasswordDeleteError", "PasswordNotFoundException"}:
            raise CredentialStoreError("The operating-system credential store could not delete the session.") from exc


def safe_equal(left, right):
    return isinstance(left, str) and isinstance(right, str) and secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def enabled():
    return os.getenv("REPLIQUE_OAUTH_ENABLED") == "1"


def client():
    return httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False)


def fail(code, message, status=400):
    raise HTTPException(status, {"code": code, "message": message})


def same_origin(request: Request):
    # Require the exact IPv4 loopback origin; no CORS/development exception here.
    if (request.url.scheme != "http" or request.url.hostname != "127.0.0.1"
            or request.headers.get("origin") != str(request.base_url).rstrip("/")
            or request.headers.get("x-replique-request") != "1"):
        fail("invalid_origin", "Ouvrez Réplique sur http://127.0.0.1:8000.", 403)


def host_id():
    # Non-secret installation ID only; deliberately separate from credentials.
    path = Path(os.getenv("REPLIQUE_DATA_DIR", str(Path.home() / ".local/share/replique"))) / "host-id"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        value = path.read_text().strip()
        if not value.startswith("urn:uuid:"):
            fail("invalid_host", "Identifiant local invalide.", 503)
        uuid.UUID(value[9:], version=4)
        return value
    value = "urn:uuid:" + str(uuid.uuid4())
    with os.fdopen(fd, "w") as stream:
        stream.write(value)
    return value


def registration_path():
    return Path(os.getenv("REPLIQUE_DATA_DIR", str(Path.home() / ".local/share/replique"))) / "registration.json"


def load_registration():
    path = registration_path()
    try:
        with path.open("rb") as source:
            raw = source.read(8193)
        if len(raw) > 8192:
            raise ValueError()
        data = json.loads(raw)
        issued, subject = data["client_id"], data["subject"]
        if not isinstance(issued, str) or not issued or issued == "dynamic_agent_client" or not isinstance(subject, str) or not subject:
            raise ValueError()
        return issued, subject
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError):
        fail("invalid_registration", "L’inscription locale est illisible. Consultez le guide de récupération.", 503)


def save_registration(issued, subject):
    # Non-secret client/verified-sub mapping only. NEVER persist any token here.
    path = registration_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".registration-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as target:
            json.dump({"client_id": issued, "subject": subject}, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(repr=False)
class Pending:
    state: str
    nonce: str
    verifier: str
    redirect: str
    browser: str
    client_id: str
    subject: str | None
    expires: float = field(default_factory=lambda: time.time() + 300)


@dataclass(repr=False)
class Session:
    browser: str
    client_id: str
    subject: str
    email: str | None
    access: str
    refresh: str
    scopes: set[str]
    expires: float


class OAuth:
    def __init__(self):
        self.pending: Pending | None = None
        self.session: Session | None = None
        self.registration: tuple[str, str] | None = None  # non-secret mapping, loaded on explicit sign-in
        self.error = None
        self.lock = asyncio.Lock()
        self.generations = set()

    def restore_session(self, browser):
        if self.session or not browser:
            return
        if self.error and self.error.get("code") == "reauth_required":
            return
        try:
            self.session = load_persistent_session(browser)
        except CredentialStoreError:
            self.error = {"code": "reauth_required", "message": "Le stockage local protégé est inaccessible. Reconnectez votre compte ChatGPT."}

    def status(self, browser):
        # A pending login has no stored session to restore yet. An unavailable
        # keychain must not turn an expired first attempt into "reauth_required".
        if self.pending is None:
            self.restore_session(browser)
        owned = self.session if self.session and safe_equal(browser or "", self.session.browser) else None
        pending = self.pending and self.pending.expires > time.time() and safe_equal(browser or "", self.pending.browser)
        return {"enabled": enabled(), "status": "connected" if owned else "connecting" if pending else "reauth_required" if self.error and self.error.get("code") == "reauth_required" and browser else "disconnected",
                "sharing": bool(owned and "chatgpt.tokens.use.direct" in owned.scopes),
                "identity": {"email": owned.email} if owned else None,
                "error": self.error if pending or owned or browser else None}

    async def json_request(self, method, url, *, max_bytes=MAX_JSON_RESPONSE, **kwargs):
        async with asyncio.timeout(20), client() as http:
            async with http.stream(method, url, **kwargs) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        fail("invalid_response", "Réponse de connexion trop volumineuse.", 502)
                if response.status_code == 429:
                    fail("usage_limit", "La limite d’utilisation est atteinte. Réessayez plus tard.", 429)
                if response.status_code == 403:
                    fail("unsupported_plan", "Ce compte ou cette autorisation ne permet pas cette utilisation.", 403)
                if response.status_code >= 300:
                    fail("authorization_failed", "La connexion a été refusée ou a expiré. Recommencez.", 401 if response.status_code in {400, 401} else 502)
        try:
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError:
            fail("invalid_response", "Réponse de connexion invalide.", 502)

    async def metadata(self):
        data = await self.json_request("GET", DISCOVERY)
        if data.get("issuer") != ISSUER:
            fail("invalid_issuer", "L’identité du service n’a pas pu être vérifiée.", 502)
        for key in ("jwks_uri", "revocation_endpoint"):
            try:
                url = urlsplit(data.get(key, ""))
                port = url.port
            except (TypeError, ValueError):
                fail("invalid_metadata", "Configuration de connexion non reconnue.", 502)
            if url.scheme != "https" or url.hostname != "auth.openai.com" or port not in (None, 443) or url.username or url.password or url.fragment:
                fail("invalid_metadata", "Configuration de connexion non reconnue.", 502)
        return data

    async def validate_identity(self, token, pending, issued):
        metadata = await self.metadata()
        jwks = await self.json_request("GET", metadata["jwks_uri"])
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise ValueError()
            matches = [key for key in jwks.get("keys", []) if isinstance(key, dict) and key.get("kid") == header["kid"] and key.get("kty") == "RSA" and key.get("use", "sig") == "sig"]
            if len(matches) != 1:
                raise ValueError()
            key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256")
            claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=issued, issuer=ISSUER,
                                options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]})
            if not isinstance(claims["sub"], str) or not claims["sub"] or not safe_equal(claims["nonce"], pending.nonce):
                raise ValueError()
            if pending.subject and claims["sub"] != pending.subject:
                raise ValueError()
            if claims.get("azp", issued) != issued:
                raise ValueError()
            if claims.get("email") is not None and not isinstance(claims["email"], str):
                raise ValueError()
            if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != issued:
                raise ValueError()
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            fail("invalid_identity", "L’identité de connexion n’a pas pu être vérifiée.", 401)

    def tokens(self, data, previous=None):
        access, refresh = data.get("access_token"), data.get("refresh_token", previous.refresh if previous else None)
        scope = data.get("scope", " ".join(previous.scopes) if previous else "")
        token_type = data.get("token_type", "")
        if not isinstance(scope, str) or not isinstance(token_type, str):
            fail("invalid_tokens", "La session reçue est invalide.", 401)
        scopes = set(scope.split())
        expiry = data.get("expires_in")
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh or token_type.lower() != "bearer" or not isinstance(expiry, (int, float)) or isinstance(expiry, bool) or not 0 < expiry <= 86400:
            fail("invalid_tokens", "La session reçue est invalide.", 401)
        if not {"openid", "resource.invoke", "chatgpt.tokens.use.direct"} <= scopes:
            fail("consent_required", "L’utilisation du forfait ChatGPT n’a pas été autorisée.", 403)
        return access, refresh, scopes, time.time() + expiry

    async def access(self, browser):
        if not enabled():
            fail("oauth_disabled", "La connexion OAuth est désactivée.", 503)
        async with self.lock:
            self.restore_session(browser)
            session = self.session
            if not session or not safe_equal(browser or "", session.browser):
                fail("sign_in_required", "Connectez votre compte ChatGPT avant de générer.", 401)
            if session.expires <= time.time() + 60:
                try:
                    data = await self.json_request("POST", TOKEN, data={"grant_type": "refresh_token", "client_id": session.client_id,
                        "refresh_token": session.refresh, "resource": RESOURCE})
                    access, refresh, scopes, expires = self.tokens(data, session)
                    renewed = Session(session.browser, session.client_id, session.subject, session.email, access, refresh, scopes, expires)
                    save_persistent_session(renewed)
                    self.session = renewed
                except Exception:
                    self.session = None
                    self.error = {"code": "reauth_required", "message": "La session doit être reconnectée."}
                    raise
            return self.session.access


oauth = OAuth()


@router.get("/status")
async def status(request: Request):
    return oauth.status(request.cookies.get(COOKIE))


@router.post("/login")
async def login(request: Request):
    same_origin(request)
    if not enabled():
        fail("oauth_disabled", "La connexion OAuth est préparée mais désactivée. Consultez le guide local.", 503)
    async with oauth.lock:
        if oauth.pending and oauth.pending.expires > time.time():
            fail("sign_in_pending", "Une connexion est déjà en cours. Annulez-la avant de recommencer.", 409)
        if oauth.session:
            fail("already_connected", "Déconnectez le compte actuel avant de changer de compte.", 409)
        browser = secrets.token_urlsafe(32)
        oauth.registration = oauth.registration or load_registration()
        issued, subject = oauth.registration or ("dynamic_agent_client", None)
        pending = Pending(secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64),
                          str(request.base_url).rstrip("/") + "/api/auth/callback", browser, issued, subject)
        params = {"client_id": issued, "ext_agent_host_id": host_id(), "response_type": "code", "redirect_uri": pending.redirect,
                  "scope": SCOPES, "resource": RESOURCE, "state": pending.state, "nonce": pending.nonce,
                  "code_challenge_method": "S256", "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(pending.verifier.encode()).digest()).decode().rstrip("=")}
        if issued == "dynamic_agent_client":
            params["agent_name_hint"] = "Réplique"
        oauth.pending, oauth.error = pending, None
        response = JSONResponse({"authorization_url": AUTHORIZE + "?" + urlencode(params)})
        # HTTP-only loopback application: Secure is unavailable on plain HTTP.
        # Host-only, Lax permits the top-level OAuth return; no token in cookie.
        response.set_cookie(COOKIE, browser, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/")
        return response


@router.get("/callback")
async def callback(request: Request):
    async with oauth.lock:
        pending = oauth.pending
        if (not enabled() or not pending or time.time() > pending.expires
                or str(request.url).split("?")[0] != pending.redirect
                or not safe_equal(request.cookies.get(COOKIE, ""), pending.browser)
                or not safe_equal(request.query_params.get("state", ""), pending.state)):
            fail("invalid_state", "Cette tentative de connexion est invalide ou expirée.", 400)
        oauth.pending = None  # one-shot, including denied/error callbacks
        try:
            if any(len(request.query_params.getlist(key)) > 1 for key in ("state", "code", "client_id", "error")):
                fail("invalid_callback", "Retour de connexion invalide.")
            if request.query_params.get("error"):
                fail("consent_declined", "Connexion annulée ou autorisation refusée.")
            issued = request.query_params.get("client_id", pending.client_id)
            if not issued or issued == "dynamic_agent_client" or (pending.client_id != "dynamic_agent_client" and issued != pending.client_id):
                fail("invalid_client", "L’inscription du client n’a pas été validée.")
            code = request.query_params.get("code")
            if not code or len(code) > 8192 or len(issued) > 256:
                fail("invalid_callback", "Retour de connexion invalide.")
            data = await oauth.json_request("POST", TOKEN, data={"grant_type": "authorization_code", "client_id": issued,
                "code": code, "code_verifier": pending.verifier, "redirect_uri": pending.redirect, "resource": RESOURCE})
            claims = await oauth.validate_identity(data.get("id_token", ""), pending, issued)
            access, refresh, scopes, expires = oauth.tokens(data)
            save_registration(issued, claims["sub"])
            session = Session(pending.browser, issued, claims["sub"], claims.get("email"), access, refresh, scopes, expires)
            save_persistent_session(session)
            oauth.session = session
            oauth.registration = (issued, claims["sub"])
            oauth.error = None
            return RedirectResponse("/?auth=connected", status_code=303)
        except CredentialStoreError:
            oauth.error = {"code": "credential_store_unavailable", "message": "La connexion est valide, mais le stockage protégé du système est indisponible. Aucun jeton n’a été conservé."}
        except HTTPException as exc:
            oauth.error = exc.detail if isinstance(exc.detail, dict) else {"code": "auth_error", "message": "Connexion impossible."}
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, OSError):
            oauth.error = {"code": "auth_unavailable", "message": "Le service de connexion est indisponible. Réessayez."}
        return RedirectResponse("/?auth=error", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    same_origin(request)
    async with oauth.lock:
        browser = request.cookies.get(COOKIE, "")
        oauth.restore_session(browser)
        session = oauth.session
        if session and not safe_equal(browser, session.browser):
            fail("invalid_session", "La session locale n’est pas valide.", 403)
        if oauth.pending and not safe_equal(browser, oauth.pending.browser):
            fail("invalid_session", "La tentative locale n’est pas valide.", 403)
        oauth.pending = None
        for task in tuple(oauth.generations):
            task.cancel()
        oauth.session = None
        oauth.error = None
        revoked = False
        if session:
            try:
                metadata = await oauth.metadata()
                async with asyncio.timeout(20), client() as http:
                    async with http.stream("POST", metadata["revocation_endpoint"], data={"token": session.refresh,
                        "token_type_hint": "refresh_token", "client_id": session.client_id}) as result:
                        revoked = result.status_code == 200
            except (httpx.HTTPError, HTTPException, TimeoutError, ValueError, TypeError):
                pass
        try:
            delete_persistent_session()
        except CredentialStoreError:
            oauth.error = {"code": "credential_store_unavailable", "message": "La session est fermée dans Réplique, mais le stockage protégé n’a pas pu être effacé."}
        response = JSONResponse({"status": "disconnected", "remote_revoked": revoked})
        response.delete_cookie(COOKIE, path="/")
        return response
