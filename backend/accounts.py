"""Private beta accounts and metered hosted generations.

Invitations are single-use so a visitor cannot reset their trial by creating
unlimited accounts. Payment activation must be supplied by a verified provider
webhook; this module never trusts the browser to grant paid access.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

TRIAL_CREDITS = 20
SESSION_SECONDS = 30 * 24 * 3600
RESERVATION_SECONDS = 300
REQUEST_LIMITS = {"generate": 6, "ocr": 10}  # per account, per fixed minute
COOKIE = "replique_account"
router = APIRouter(prefix="/api/account")


def public_origin() -> str:
    return os.getenv("REPLIQUE_PUBLIC_ORIGIN", "").rstrip("/")


def database_path() -> Path:
    root = Path(os.getenv("REPLIQUE_DATA_DIR", str(Path.home() / ".local/share/replique")))
    if not root.is_absolute() or root.is_symlink():
        raise RuntimeError("REPLIQUE_DATA_DIR must be a private absolute directory")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "accounts.sqlite3"
    if not path.exists():
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
        except FileExistsError:
            pass
    return path


@contextmanager
def database(write: bool = False):
    path = database_path()
    if path.is_symlink():
        raise RuntimeError("Account database must not be a symlink")
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL,
                used INTEGER NOT NULL DEFAULT 0 CHECK(used >= 0),
                paid_until INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS invitations (
                code_hash TEXT PRIMARY KEY, used_by TEXT REFERENCES accounts(id)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS request_limits (
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                action TEXT NOT NULL, window_start INTEGER NOT NULL, calls INTEGER NOT NULL,
                PRIMARY KEY (account_id, action)
            );
        """)
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        if write:
            connection.commit()
    except Exception:
        if write:
            connection.rollback()
        raise
    finally:
        connection.close()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)


def request_account(request: Request) -> sqlite3.Row:
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(401, "Connectez-vous à votre compte Réplique.")
    with database() as db:
        row = db.execute("SELECT accounts.* FROM sessions JOIN accounts ON accounts.id=sessions.account_id "
                         "WHERE sessions.token_hash=? AND sessions.expires_at>?", (digest(token), int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401, "Votre session a expiré. Reconnectez-vous.")
    return row


def status_for(account: sqlite3.Row) -> dict:
    with database() as db:
        active = db.execute("SELECT COUNT(*) FROM reservations WHERE account_id=? AND expires_at>?",
                            (account["id"], int(time.time()))).fetchone()[0]
    paid = account["paid_until"] > int(time.time())
    return {"email": account["email"], "trial_remaining": max(0, TRIAL_CREDITS - account["used"] - active),
            "trial_total": TRIAL_CREDITS, "subscription_active": paid,
            "subscription_available": False}


def issue_session(db: sqlite3.Connection, account_id: str) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), account_id, int(time.time()) + SESSION_SECONDS))
    return token


def session_response(token: str, account: sqlite3.Row) -> JSONResponse:
    response = JSONResponse(status_for(account))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=bool(public_origin()), samesite="lax", path="/")
    return response


class Registration(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    invitation: str = Field(min_length=16, max_length=128)


class Login(BaseModel):
    email: str
    password: str


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1 or not email.split("@", 1)[1].count("."):
        raise HTTPException(422, "Saisissez une adresse e-mail valide.")
    return email


@router.get("/status")
def status(request: Request):
    return status_for(request_account(request))


@router.post("/register")
def register(body: Registration):
    email = normalize_email(body.email)
    salt = os.urandom(16)
    account_id = str(uuid4())
    with database(True) as db:
        invitation = db.execute("SELECT used_by FROM invitations WHERE code_hash=?", (digest(body.invitation),)).fetchone()
        if invitation is None or invitation["used_by"] is not None:
            raise HTTPException(403, "Ce code d’invitation est invalide ou déjà utilisé.")
        try:
            db.execute("INSERT INTO accounts (id,email,salt,password_hash) VALUES (?,?,?,?)",
                       (account_id, email, salt, password_digest(body.password, salt)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Ce compte existe déjà.") from None
        db.execute("UPDATE invitations SET used_by=? WHERE code_hash=?", (account_id, digest(body.invitation)))
        token = issue_session(db, account_id)
        account = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return session_response(token, account)


@router.post("/login")
def login(body: Login):
    email = normalize_email(body.email)
    with database() as db:
        account = db.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
    if account is None:
        raise HTTPException(401, "Identifiants incorrects.")
    candidate = password_digest(body.password, account["salt"])
    if not secrets.compare_digest(candidate, account["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects.")
    with database(True) as db:
        token = issue_session(db, account["id"])
    return session_response(token, account)


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE, "")
    if token:
        with database(True) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
    response = JSONResponse({"disconnected": True})
    response.delete_cookie(COOKIE, path="/")
    return response


def reserve(account_id: str) -> str:
    now = int(time.time())
    with database(True) as db:
        db.execute("DELETE FROM reservations WHERE expires_at<=?", (now,))
        account = db.execute("SELECT used,paid_until FROM accounts WHERE id=?", (account_id,)).fetchone()
        if account is None:
            raise HTTPException(401, "Reconnectez-vous à Réplique.")
        active = db.execute("SELECT COUNT(*) FROM reservations WHERE account_id=?", (account_id,)).fetchone()[0]
        if account["paid_until"] <= now and account["used"] + active >= TRIAL_CREDITS:
            raise HTTPException(402, "Vos 20 crédits d’essai sont épuisés. L’abonnement n’est pas encore ouvert.")
        reservation = str(uuid4())
        db.execute("INSERT INTO reservations VALUES (?,?,?)", (reservation, account_id, now + RESERVATION_SECONDS))
    return reservation


def limit_account(account_id: str, action: str) -> None:
    """Bound expensive public requests without locking a victim's account."""
    maximum = REQUEST_LIMITS[action]
    now = int(time.time())
    window = now - now % 60
    with database(True) as db:
        previous = db.execute("SELECT window_start,calls FROM request_limits WHERE account_id=? AND action=?",
                              (account_id, action)).fetchone()
        calls = previous["calls"] if previous and previous["window_start"] == window else 0
        if calls >= maximum:
            raise HTTPException(429, "Trop de demandes. Réessayez dans un instant.",
                                headers={"Retry-After": str(60 - now % 60)})
        db.execute("INSERT INTO request_limits (account_id,action,window_start,calls) VALUES (?,?,?,?) "
                   "ON CONFLICT(account_id,action) DO UPDATE SET window_start=excluded.window_start,calls=excluded.calls",
                   (account_id, action, window, calls + 1))


def finish(reservation: str, success: bool) -> None:
    with database(True) as db:
        row = db.execute("SELECT account_id FROM reservations WHERE id=?", (reservation,)).fetchone()
        if row is not None:
            if success:
                db.execute("UPDATE accounts SET used=used+1 WHERE id=?", (row["account_id"],))
            db.execute("DELETE FROM reservations WHERE id=?", (reservation,))


def create_invitation() -> str:
    code = secrets.token_urlsafe(24)
    with database(True) as db:
        db.execute("INSERT INTO invitations (code_hash) VALUES (?)", (digest(code),))
    return code


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "invite":
        print(create_invitation())
    else:
        raise SystemExit("Usage: python -m backend.accounts invite")
