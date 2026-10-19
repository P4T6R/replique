"""Private generation latency and failure counts; no prompts or identities."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import time
from pathlib import Path

OUTCOMES = {"success", "quota", "authorization", "credentials", "configuration",
            "model", "provider", "invalid_response", "busy", "cancelled", "other"}
PROVIDERS = {"owner_chatgpt", "local"}
RETENTION_SECONDS = 30 * 24 * 3600


def database_path() -> Path:
    root = Path(os.environ["REPLIQUE_DATA_DIR"])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("REPLIQUE_DATA_DIR must be private and absolute")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root / "operations.sqlite3"


def record_generation(provider: str, outcome: str, duration_ms: int) -> bool:
    """Best-effort telemetry must never change a visitor's result."""
    if provider not in PROVIDERS or outcome not in OUTCOMES or duration_ms < 0:
        return False
    try:
        path = database_path()
        if path.is_symlink():
            return False
        if not path.exists():
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
        now = int(time.time())
        with sqlite3.connect(path, timeout=2) as db:
            db.execute("CREATE TABLE IF NOT EXISTS generation_events ("
                       "created_at INTEGER NOT NULL, provider TEXT NOT NULL, outcome TEXT NOT NULL, duration_ms INTEGER NOT NULL)")
            db.execute("DELETE FROM generation_events WHERE created_at<?", (now - RETENTION_SECONDS,))
            db.execute("INSERT INTO generation_events VALUES (?,?,?,?)", (now, provider, outcome, min(duration_ms, 600_000)))
        return True
    except (OSError, sqlite3.Error, ValueError):
        return False


def report(days: int = 7) -> dict:
    if not 1 <= days <= 30:
        raise ValueError("days must be between 1 and 30")
    path = database_path()
    if not path.exists():
        return {"days": days, "total": 0, "outcomes": {}, "success_latency_ms": None}
    if path.is_symlink():
        raise ValueError("Metrics database path is unsafe")
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT outcome,duration_ms FROM generation_events WHERE created_at>=?",
                          (int(time.time()) - days * 24 * 3600,)).fetchall()
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Private aggregate generation diagnostics")
    parser.add_argument("report", choices=["report"])
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(report(args.days), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
