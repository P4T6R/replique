"""Explicit local single-user memory. Never called to save during generation.

SQLite is not encrypted. Logical deletion cannot erase external backups.
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .accounts import limit_account, public_origin, request_account

def require_local_request(request: Request):
    # An unforgeable-by-HTML custom header complements Host/Origin guards.
    # Cross-origin fetch requires preflight, for which no CORS is enabled.
    if request.headers.get('x-replique-request') != '1':
        raise HTTPException(403, 'Ouvrez la mémoire depuis l’interface Réplique.')


def memory_account(request: Request, write: bool = False) -> str | None:
    account_id = request_account(request)['id'] if public_origin() else None
    if account_id and write:
        limit_account(account_id, 'memory_write')
    return account_id


router = APIRouter(prefix="/api/memory", dependencies=[Depends(require_local_request)])
NOTICE = "Profil local mono-utilisateur, indépendant du compte ChatGPT connecté. Base non chiffrée. Exemples conservés 30 jours ; préférences jusqu’à suppression."
HOSTED_NOTICE = "Mémoire facultative séparée par compte Réplique sur ce serveur. Base non chiffrée. Exemples conservés 30 jours ; préférences jusqu’à suppression."
MAX_ITEMS = 500
SCHEMA_VERSION = 1


def db_path(account_id: str | None = None) -> Path:
    override = os.environ.get("REPLIQUE_DATA_DIR")
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            raise ValueError("REPLIQUE_DATA_DIR must be absolute")
    elif sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Replique"
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support/Replique"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "replique"
    if account_id is not None:
        try:
            if str(UUID(account_id)) != account_id:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Invalid account memory owner") from None
        if root.is_symlink():
            raise ValueError("Memory root must not be a symlink")
        return root / "account-memory" / (account_id + ".sqlite3")
    return root / "memory.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(create=False, account_id: str | None = None):
    path = db_path(account_id)
    if account_id and path.parent.exists() and path.parent.stat().st_mode & 0o077:
        raise ValueError("Account memory directory must be private")
    if not path.exists() and not create:
        return None
    if path.is_symlink() or path.parent.is_symlink() or (account_id and path.parent.parent.is_symlink()):
        raise ValueError("Memory path must not be a symlink")
    if account_id and path.exists() and path.stat().st_mode & 0o077:
        raise ValueError("Account memory database must be private")
    if create:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
    db = sqlite3.connect(str(path), timeout=2)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=2000")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        db.close()
        raise ValueError("Unsupported memory schema")
    if version == 0:
        if not create:
            db.close()
            raise ValueError("Uninitialized memory schema")
        with db:
            db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS items (
              id TEXT PRIMARY KEY, conversation TEXT NOT NULL, reply TEXT NOT NULL,
              intent TEXT NOT NULL, tone TEXT NOT NULL, locale TEXT NOT NULL,
              rating TEXT NOT NULL, feedback TEXT NOT NULL, validated INTEGER NOT NULL CHECK(validated IN (0,1)),
              created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback (
              id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
              rating TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS profile (
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), content TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT OR IGNORE INTO metadata VALUES ('revision','0');
            PRAGMA user_version=1;
            COMMIT;
            ''')
    return db


@contextmanager
def transaction(create=False, account_id: str | None = None):
    db = None
    try:
        db = connect(create, account_id)
        if db is not None:
            db.execute("BEGIN IMMEDIATE" if create else "BEGIN")
        if db is not None:
            purge_expired(db)
        yield db
        if db is not None:
            db.commit()
    except (sqlite3.Error, OSError, ValueError):
        if db is not None:
            db.rollback()
        raise HTTPException(503, "La mémoire locale est indisponible. Aucun enregistrement confirmé ; réessayez ou générez sans mémoire.") from None
    finally:
        if db is not None:
            db.close()


def revision(db):
    return int(db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0]) if db else 0


def bump(db):
    db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def item_dict(row):
    item = dict(row)
    item['validated'] = bool(item['validated'])
    return item


def active_items(db):
    return [item_dict(row) for row in db.execute("SELECT * FROM items WHERE expires_at>? ORDER BY created_at DESC LIMIT ?", (now(), MAX_ITEMS))] if db else []


def read_profile(db):
    row = db.execute("SELECT content FROM profile WHERE singleton=1").fetchone() if db else None
    return json.loads(row[0]) if row else None


class SaveItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    conversation: str = Field(default='', max_length=12000)
    reply: str = Field(min_length=1, max_length=1500)
    intent: Literal['relancer', 'répondre naturellement', 'proposer de se voir', 'clarifier', 'poser une limite', 'décliner']
    tone: Literal['naturel', 'chaleureux', 'direct', 'léger'] = 'naturel'
    locale: Literal['fr_neutre', 'afrique_ouest', 'burkina_faso'] = 'fr_neutre'
    rating: Literal['positive', 'negative', 'edited', 'neutral']
    feedback: Literal['natural','too_formal','out_of_context','too_long','edited','other'] = 'other'
    validated: bool = False
    consent: bool = False
    reviewed: bool = False

    @model_validator(mode='after')
    def explicit(self):
        if not self.reply.strip():
            raise ValueError('Empty reply')
        if self.validated and self.rating not in {'positive','edited'}:
            raise ValueError('Only explicitly positive or edited examples can be validated')
        return self


class StyleProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    length: Literal['short', 'balanced'] = 'short'
    style_register: Literal['neutral', 'familiar'] = Field(default='neutral', alias='register')
    emoji: Literal['none', 'allowed'] = 'none'
    consent: bool = False


@router.get('')
def inspect_memory(request: Request):
    account_id = memory_account(request)
    with transaction(account_id=account_id) as db:
        return {'items': active_items(db), 'profile': read_profile(db), 'revision': revision(db), 'local_only': account_id is None, 'encrypted': False, 'notice': HOSTED_NOTICE if account_id else NOTICE}


@router.post('/items')
def save_item(body: SaveItem, request: Request):
    if not body.consent or not body.reviewed:
        raise HTTPException(403, 'Relisez le contenu et autorisez explicitement sa conservation locale.')
    with transaction(True, memory_account(request, write=True)) as db:
        purge_expired(db)
        if db.execute('SELECT COUNT(*) FROM items').fetchone()[0] >= MAX_ITEMS:
            raise HTTPException(409, 'La mémoire contient 500 exemples. Supprimez-en avant de continuer.')
        created = datetime.now(timezone.utc)
        item = body.model_dump(exclude={'consent', 'reviewed'})
        item.update(id=str(uuid4()), created_at=created.isoformat(), expires_at=(created+timedelta(days=30)).isoformat())
        db.execute('INSERT INTO items VALUES (:id,:conversation,:reply,:intent,:tone,:locale,:rating,:feedback,:validated,:created_at,:expires_at)', item)
        db.execute('INSERT INTO feedback VALUES (?,?,?,?)',(str(uuid4()),item['id'],item['rating'],item['created_at']))
        bump(db)
    return item


@router.put('/profile')
def save_profile(body: StyleProfile, request: Request):
    if not body.consent:
        raise HTTPException(403, 'Autorisez explicitement la conservation du profil de style.')
    value = body.model_dump(exclude={'consent'}, by_alias=True)
    with transaction(True, memory_account(request, write=True)) as db:
        db.execute('INSERT INTO profile VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at', (json.dumps(value),now()))
        bump(db)
    return value


def delete_derived(db, item_id):
    # Evaluation module may attach version sources; never retain a derived version
    # after its source disappears. No private text is copied into retrieval caches.
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'eval_versions' in tables:
        from .evaluation import delete_source
        delete_source(db, item_id)


def purge_expired(db):
    ids = [row[0] for row in db.execute('SELECT id FROM items WHERE expires_at<=?',(now(),))]
    for item_id in ids:
        delete_derived(db,item_id)
        db.execute('DELETE FROM items WHERE id=?',(item_id,))
    if ids:
        bump(db)


@router.delete('/items/{item_id}')
def delete_item(item_id: str, request: Request):
    with transaction(account_id=memory_account(request, write=True)) as db:
        if db:
            delete_derived(db,item_id)
            db.execute('DELETE FROM items WHERE id=?',(item_id,))
            bump(db)
    return {'deleted': True}


@router.delete('')
def delete_memory(request: Request):
    with transaction(account_id=memory_account(request, write=True)) as db:
        if db:
            for row in db.execute('SELECT id FROM items').fetchall():
                delete_derived(db,row[0])
            db.execute('DELETE FROM items')
            db.execute('DELETE FROM profile')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='eval_versions'").fetchone():
                from .evaluation import delete_all
                delete_all(db)
            bump(db)
    return {'deleted': True, 'notice': 'Données effacées de la base active. Les sauvegardes externes et copies exportées ne sont pas effacées.'}


@router.get('/export')
def export_memory(request: Request):
    account_id = memory_account(request)
    with transaction(account_id=account_id) as db:
        result = {'format':'replique-memory-v1','exported_at':now(),'notice':HOSTED_NOTICE if account_id else NOTICE,'items':active_items(db),'profile':read_profile(db),'revision':revision(db)}
        result['evaluation'] = {}
        if db:
            for table in ('eval_versions', 'eval_runs', 'eval_active', 'eval_history'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    result['evaluation'][table] = [dict(row) for row in db.execute('SELECT * FROM ' + table)]
        result['feedback'] = [dict(row) for row in db.execute('SELECT feedback.* FROM feedback JOIN items ON items.id=feedback.item_id WHERE items.expires_at>?',(now(),))] if db else []
    return JSONResponse(result, headers={'Content-Disposition':'attachment; filename="replique-memory.json"','Cache-Control':'no-store'})


def select_context(intent: str, tone: str, locale: str, account_id: str | None = None):
    with transaction(account_id=account_id) as db:
        examples = []
        max_examples, max_chars = 3, 4500
        if db and db.execute("SELECT 1 FROM sqlite_master WHERE name='eval_versions'").fetchone():
            from .evaluation import get_active
            config = get_active(db)['config']
            max_examples = min(3, max(0, config['max_examples']))
            max_chars = min(6000, max(0, config['max_context_chars']))
        if db:
            rows = db.execute('SELECT * FROM items WHERE validated=1 AND rating IN (\'positive\',\'edited\') AND expires_at>? AND intent=? AND locale=? ORDER BY (tone=?) DESC,created_at DESC LIMIT ?', (now(),intent,locale,tone,max_examples))
            budget = max_chars
            for row in rows:
                # Only bounded chosen text/excerpts. No model instructions or facts inferred.
                example = {key: row[key] for key in ('id','reply','conversation','intent','tone','locale')}
                size = len(example['reply']) + len(example['conversation'])
                if size > budget:
                    continue
                examples.append(example)
                budget -= size
        return {'examples':examples,'profile':read_profile(db),'revision':revision(db),'notice':HOSTED_NOTICE if account_id else NOTICE}


@router.get('/preview')
def preview(request: Request, intent: str='', tone: str='naturel', locale: str='fr_neutre'):
    return select_context(intent,tone,locale,memory_account(request))
