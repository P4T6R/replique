"""Account-scoped conversation history for the hosted workspace."""

from __future__ import annotations

import json
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .accounts import database, request_account

router = APIRouter(prefix="/api/conversations")


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            intent TEXT NOT NULL DEFAULT 'répondre naturellement',
            tone TEXT NOT NULL DEFAULT 'naturel',
            style TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 0,
            suggestions TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
    db.execute("CREATE INDEX IF NOT EXISTS conversations_owner_updated ON conversations(account_id, updated_at DESC)")
    db.execute("""CREATE TABLE IF NOT EXISTS conversation_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sender TEXT NOT NULL CHECK(sender IN ('me', 'other')),
            body TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""")
    db.execute("CREATE INDEX IF NOT EXISTS conversation_messages_order ON conversation_messages(conversation_id, created_at)")


def owned(db, account_id: str, conversation_id: str):
    row = db.execute("SELECT * FROM conversations WHERE id=? AND account_id=?", (conversation_id, account_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Conversation introuvable.")
    return row


def present(db, row):
    messages = db.execute(
        "SELECT id, sender, body, created_at FROM conversation_messages WHERE conversation_id=? ORDER BY created_at, rowid",
        (row["id"],),
    ).fetchall()
    return {"id": row["id"], "title": row["title"], "intent": row["intent"], "tone": row["tone"],
            "style": row["style"], "revision": row["revision"], "updated_at": row["updated_at"],
            "suggestions": json.loads(row["suggestions"]) if row["suggestions"] else None,
            "messages": [dict(message) for message in messages]}


class NewConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Nouvelle conversation", min_length=1, max_length=80)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    intent: str = Field(max_length=60)
    tone: str = Field(max_length=30)
    style: str = Field(default="", max_length=500)


class NewMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender: str
    body: str = Field(min_length=1, max_length=2000)


class ImportText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    messages: list[NewMessage] = Field(min_length=1, max_length=80)


@router.get("")
def list_conversations(request: Request):
    account_id = request_account(request)["id"]
    with database() as db:
        initialize(db)
        rows = db.execute("SELECT id, title, updated_at FROM conversations WHERE account_id=? ORDER BY updated_at DESC LIMIT 100", (account_id,)).fetchall()
        return {"conversations": [dict(row) for row in rows]}


@router.post("")
def create_conversation(payload: NewConversation, request: Request):
    account_id = request_account(request)["id"]
    if not payload.title.strip():
        raise HTTPException(422, "Donnez un nom à la conversation.")
    with database(write=True) as db:
        initialize(db)
        count = db.execute("SELECT COUNT(*) FROM conversations WHERE account_id=?", (account_id,)).fetchone()[0]
        if count >= 100:
            raise HTTPException(409, "Limite de 100 conversations atteinte. Supprimez une ancienne conversation.")
        conversation_id = uuid4().hex
        now = int(time.time())
        db.execute("INSERT INTO conversations(id, account_id, title, created_at, updated_at) VALUES(?,?,?,?,?)",
                   (conversation_id, account_id, payload.title.strip(), now, now))
        return present(db, owned(db, account_id, conversation_id))


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, request: Request):
    account_id = request_account(request)["id"]
    with database() as db:
        initialize(db)
        return present(db, owned(db, account_id, conversation_id))


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: str, payload: Settings, request: Request):
    account_id = request_account(request)["id"]
    if not payload.title.strip():
        raise HTTPException(422, "Donnez un nom à la conversation.")
    if payload.intent not in {"relancer", "répondre naturellement", "proposer de se voir", "clarifier", "poser une limite", "décliner"}:
        raise HTTPException(422, "Objectif invalide.")
    if payload.tone not in {"naturel", "chaleureux", "direct", "léger"}:
        raise HTTPException(422, "Ton invalide.")
    with database(write=True) as db:
        initialize(db)
        owned(db, account_id, conversation_id)
        db.execute("UPDATE conversations SET title=?, intent=?, tone=?, style=?, revision=revision+1, suggestions=NULL, updated_at=? WHERE id=? AND account_id=?",
                   (payload.title.strip(), payload.intent, payload.tone, payload.style.strip(), int(time.time()), conversation_id, account_id))
        return present(db, owned(db, account_id, conversation_id))


@router.post("/{conversation_id}/messages")
def add_message(conversation_id: str, payload: NewMessage, request: Request):
    account_id = request_account(request)["id"]
    if payload.sender not in {"me", "other"} or not payload.body.strip():
        raise HTTPException(422, "Message invalide.")
    with database(write=True) as db:
        initialize(db)
        owned(db, account_id, conversation_id)
        count = db.execute("SELECT COUNT(*) FROM conversation_messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        if count >= 300:
            raise HTTPException(409, "Cette conversation est trop longue. Créez une nouvelle conversation.")
        db.execute("INSERT INTO conversation_messages VALUES(?,?,?,?,?)", (uuid4().hex, conversation_id, payload.sender, payload.body.strip(), int(time.time())))
        db.execute("UPDATE conversations SET revision=revision+1, suggestions=NULL, updated_at=? WHERE id=? AND account_id=?",
                   (int(time.time()), conversation_id, account_id))
        return present(db, owned(db, account_id, conversation_id))


@router.post("/{conversation_id}/import-text")
def import_text(conversation_id: str, payload: ImportText, request: Request):
    account_id = request_account(request)["id"]
    if any(message.sender not in {"me", "other"} or not message.body.strip() for message in payload.messages):
        raise HTTPException(422, "Vérifiez les auteurs et le texte des messages.")
    return import_messages(account_id, conversation_id, payload.revision,
                           [{"sender": message.sender, "body": message.body.strip()} for message in payload.messages])


@router.patch("/{conversation_id}/messages/{message_id}")
def correct_message(conversation_id: str, message_id: str, payload: NewMessage, request: Request):
    account_id = request_account(request)["id"]
    if payload.sender not in {"me", "other"} or not payload.body.strip():
        raise HTTPException(422, "Message invalide.")
    with database(write=True) as db:
        initialize(db)
        owned(db, account_id, conversation_id)
        changed = db.execute("UPDATE conversation_messages SET sender=?, body=? WHERE id=? AND conversation_id=?",
                             (payload.sender, payload.body.strip(), message_id, conversation_id))
        if changed.rowcount == 0:
            raise HTTPException(404, "Message introuvable.")
        db.execute("UPDATE conversations SET revision=revision+1, suggestions=NULL, updated_at=? WHERE id=? AND account_id=?",
                   (int(time.time()), conversation_id, account_id))
        return present(db, owned(db, account_id, conversation_id))


@router.delete("/{conversation_id}/messages/{message_id}")
def remove_message(conversation_id: str, message_id: str, request: Request):
    account_id = request_account(request)["id"]
    with database(write=True) as db:
        initialize(db)
        owned(db, account_id, conversation_id)
        removed = db.execute("DELETE FROM conversation_messages WHERE id=? AND conversation_id=?", (message_id, conversation_id))
        if removed.rowcount == 0:
            raise HTTPException(404, "Message introuvable.")
        db.execute("UPDATE conversations SET revision=revision+1, suggestions=NULL, updated_at=? WHERE id=? AND account_id=?",
                   (int(time.time()), conversation_id, account_id))
        return present(db, owned(db, account_id, conversation_id))


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request):
    account_id = request_account(request)["id"]
    with database(write=True) as db:
        initialize(db)
        owned(db, account_id, conversation_id)
        db.execute("DELETE FROM conversations WHERE id=? AND account_id=?", (conversation_id, account_id))
    return {"deleted": True}


def save_suggestions(account_id: str, conversation_id: str, revision: int, result: dict):
    with database(write=True) as db:
        initialize(db)
        row = owned(db, account_id, conversation_id)
        if row["revision"] != revision:
            return False
        db.execute("UPDATE conversations SET suggestions=? WHERE id=? AND account_id=?",
                   (json.dumps(result, ensure_ascii=False), conversation_id, account_id))
        return True


def import_messages(account_id: str, conversation_id: str, revision: int, messages: list[dict]):
    """Append only the part after the latest known bubble in an overlapping capture."""
    with database(write=True) as db:
        initialize(db)
        row = owned(db, account_id, conversation_id)
        if row["revision"] != revision:
            raise HTTPException(409, "La conversation a changé pendant la lecture. Réessayez avec la capture.")
        existing = db.execute("SELECT sender, body FROM conversation_messages WHERE conversation_id=? ORDER BY created_at, rowid",
                              (conversation_id,)).fetchall()
        if len(existing) + len(messages) > 300:
            raise HTTPException(409, "Cette conversation est trop longue. Créez une nouvelle conversation.")
        normalized = lambda sender, body: (sender, " ".join(body.split()).casefold())
        known = [normalized(message["sender"], message["body"]) for message in existing]
        incoming = [normalized(message["sender"], message["body"]) for message in messages]
        cut, best_length = 0, 0
        for end in range(len(incoming)):
            length = 0
            while (length <= end and length < len(known)
                   and incoming[end - length] == known[-1 - length]):
                length += 1
            if length > best_length:
                cut, best_length = end + 1, length
        added = messages[cut:]
        now = int(time.time())
        for message in added:
            db.execute("INSERT INTO conversation_messages VALUES(?,?,?,?,?)",
                       (uuid4().hex, conversation_id, message["sender"], message["body"], now))
        if added:
            db.execute("UPDATE conversations SET revision=revision+1, suggestions=NULL, updated_at=? WHERE id=? AND account_id=?",
                       (now, conversation_id, account_id))
        return {"added": len(added), "conversation": present(db, owned(db, account_id, conversation_id))}
