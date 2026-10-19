"""Consistent, private snapshots of hosted accounts and owner credentials.

Run restore only with the application stopped and empty destination files.
Snapshots contain the owner credential key and must leave the VPS promptly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

FILES = ("accounts.sqlite3", "oauth-session.enc", "credential.key")


def absolute(path: str) -> Path:
    value = Path(path)
    if not value.is_absolute() or value.is_symlink() or value.parent.is_symlink():
        raise ValueError("Use a private absolute path without symlinks.")
    return value


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def private_copy(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ValueError("A required private source file is missing or unsafe.")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output, source.open("rb") as original:
        shutil.copyfileobj(original, output)
        output.flush()
        os.fsync(output.fileno())


def check_snapshot(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Snapshot directory is missing or unsafe.")
    if directory.stat().st_mode & 0o077:
        raise ValueError("Snapshot directory must be private (mode 700).")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_mode & 0o077:
        raise ValueError("Snapshot manifest is unsafe.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("version") != 1
            or not isinstance(manifest.get("sha256"), dict)
            or set(manifest["sha256"]) != set(FILES)):
        raise ValueError("Snapshot manifest is invalid.")
    for name in FILES:
        path = directory / name
        if not path.is_file() or path.is_symlink() or digest(path) != manifest["sha256"][name]:
            raise ValueError("Snapshot checksum mismatch.")
        if path.stat().st_mode & 0o077:
            raise ValueError("Snapshot files must be private (mode 600).")
    with sqlite3.connect(directory / "accounts.sqlite3") as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Account database is damaged.")
        db.execute("SELECT id FROM accounts LIMIT 1").fetchone()
    try:
        raw = Fernet((directory / "credential.key").read_bytes()).decrypt(
            (directory / "oauth-session.enc").read_bytes())
        session = json.loads(raw)
        if not isinstance(session.get("refresh"), str) or not session["refresh"]:
            raise ValueError("Owner session is invalid.")
    except (InvalidToken, ValueError, TypeError, KeyError) as exc:
        raise ValueError("Owner session and key do not match.") from exc


def create(directory: Path) -> None:
    data = absolute(os.environ["REPLIQUE_DATA_DIR"])
    key = absolute(os.environ["REPLIQUE_CREDENTIAL_KEY_FILE"])
    if not (data / "accounts.sqlite3").is_file() or (data / "accounts.sqlite3").is_symlink():
        raise ValueError("Account database is missing or unsafe.")
    directory = absolute(str(directory))
    directory.mkdir(mode=0o700)
    database_copy = directory / "accounts.sqlite3"
    descriptor = os.open(database_copy, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    with sqlite3.connect(data / "accounts.sqlite3") as source, sqlite3.connect(database_copy) as target:
        source.backup(target)
    private_copy(data / "oauth-session.enc", directory / "oauth-session.enc")
    private_copy(key, directory / "credential.key")
    manifest = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "sha256": {name: digest(directory / name) for name in FILES}}
    target = directory / "manifest.json"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(manifest, output, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
    check_snapshot(directory)


def restore(directory: Path, data: Path, key: Path) -> None:
    directory, data, key = (absolute(str(path)) for path in (directory, data, key))
    check_snapshot(directory)
    if not data.is_dir() or not key.parent.is_dir():
        raise ValueError("Create the empty private data and secrets directories first.")
    if data.is_symlink() or key.parent.is_symlink() or data.stat().st_mode & 0o077 or key.parent.stat().st_mode & 0o077:
        raise ValueError("Restore directories must be private (mode 700) and must not be symlinks.")
    destinations = (data / "accounts.sqlite3", data / "oauth-session.enc", key)
    if any(path.exists() or path.is_symlink() for path in destinations):
        raise ValueError("Restore requires absent account, session and key files; stop the service first.")
    created = []
    try:
        for name, destination in zip(FILES, destinations):
            private_copy(directory / name, destination)
            created.append(destination)
        if digest(destinations[0]) != digest(directory / FILES[0]):
            raise ValueError("Restored database checksum mismatch.")
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def drill(directory: Path) -> None:
    """Restore a snapshot into disposable private directories, without touching live data."""
    directory = absolute(str(directory))
    with tempfile.TemporaryDirectory(prefix=".replique-restore-check-", dir=directory.parent) as temporary:
        data, secrets = Path(temporary) / "data", Path(temporary) / "secrets"
        data.mkdir(mode=0o700)
        secrets.mkdir(mode=0o700)
        key = secrets / "credential.key"
        restore(directory, data, key)
        for name, target in zip(FILES, (data / FILES[0], data / FILES[1], key)):
            if digest(directory / name) != digest(target):
                raise ValueError("Restored snapshot does not match its source.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Private hosted backup and restore")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create").add_argument("directory")
    commands.add_parser("verify").add_argument("directory")
    commands.add_parser("drill").add_argument("directory")
    recovery = commands.add_parser("restore")
    recovery.add_argument("directory")
    recovery.add_argument("data_directory")
    recovery.add_argument("key_file")
    args = parser.parse_args()
    try:
        if args.command == "create":
            create(Path(args.directory))
        elif args.command == "verify":
            check_snapshot(absolute(args.directory))
        elif args.command == "drill":
            drill(Path(args.directory))
        else:
            restore(Path(args.directory), Path(args.data_directory), Path(args.key_file))
    except (OSError, ValueError, sqlite3.Error, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Backup operation failed: {error}\n")
    print(f"{args.command} verified")


if __name__ == "__main__":
    main()
