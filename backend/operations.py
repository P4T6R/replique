"""Private generation latency and failure counts; no prompts or identities."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import time
from contextlib import closing
from pathlib import Path

OUTCOMES = {"success", "quota", "authorization", "credentials", "configuration",
            "model", "provider", "invalid_response", "busy", "cancelled", "unreadable", "other"}
PROVIDERS = {"owner_chatgpt", "local", "chatgpt", "tesseract"}
RETENTION_SECONDS = 30 * 24 * 3600


def database_path() -> Path:
    root = Path(os.environ["REPLIQUE_DATA_DIR"])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("REPLIQUE_DATA_DIR must be private and absolute")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root / "operations.sqlite3"


def _record(kind: str, provider: str, outcome: str, duration_ms: int) -> bool:
    """Best-effort aggregate telemetry must never change a visitor's result."""
    if kind not in {"generation", "ocr"} or provider not in PROVIDERS or outcome not in OUTCOMES or duration_ms < 0:
        return False
    try:
        path = database_path()
        if path.is_symlink():
            return False
        if not path.exists():
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(descriptor)
        now = int(time.time())
        table = "generation_events" if kind == "generation" else "ocr_events"
        with closing(sqlite3.connect(path, timeout=2)) as db, db:
            db.execute(f"CREATE TABLE IF NOT EXISTS {table} ("
                       "created_at INTEGER NOT NULL, provider TEXT NOT NULL, outcome TEXT NOT NULL, duration_ms INTEGER NOT NULL)")
            db.execute(f"DELETE FROM {table} WHERE created_at<?", (now - RETENTION_SECONDS,))
            db.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", (now, provider, outcome, min(duration_ms, 600_000)))
        return True
    except (OSError, sqlite3.Error, ValueError, KeyError):
        return False


def record_generation(provider: str, outcome: str, duration_ms: int) -> bool:
    return _record("generation", provider, outcome, duration_ms)


def record_ocr(provider: str, outcome: str, duration_ms: int) -> bool:
    return _record("ocr", provider, outcome, duration_ms)


def summarize(rows: list[tuple[str, int]], days: int) -> dict:
    outcomes: dict[str, int] = {}
    success = []
    for outcome, duration in rows:
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if outcome == "success":
            success.append(duration)
    success.sort()
    latency = ({"median": statistics.median(success), "p95": success[max(0, (len(success) * 95 + 99) // 100 - 1)],
                "max": success[-1]} if success else None)
    return {"days": days, "total": len(rows), "outcomes": outcomes, "success_latency_ms": latency}


def report(days: int = 7) -> dict:
    if not 1 <= days <= 30:
        raise ValueError("days must be between 1 and 30")
    path = database_path()
    if not path.exists():
        return {**summarize([], days), "ocr": summarize([], days)}
    if path.is_symlink():
        raise ValueError("Metrics database path is unsafe")
    with closing(sqlite3.connect(path)) as db:
        has_generation = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='generation_events'").fetchone()
        rows = (db.execute("SELECT outcome,duration_ms FROM generation_events WHERE created_at>=?",
                           (int(time.time()) - days * 24 * 3600,)).fetchall() if has_generation else [])
        has_ocr = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ocr_events'").fetchone()
        ocr_rows = (db.execute("SELECT outcome,duration_ms FROM ocr_events WHERE created_at>=?",
                               (int(time.time()) - days * 24 * 3600,)).fetchall() if has_ocr else [])
    return {**summarize(rows, days), "ocr": summarize(ocr_rows, days)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Private aggregate generation diagnostics")
    parser.add_argument("report", choices=["report"])
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(report(args.days), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
