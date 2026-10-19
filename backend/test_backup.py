"""Private snapshot can be verified and restored without live credentials."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from backend.accounts import create_invitation, database
from backend.backup import check_snapshot, create, drill, restore
from backend.oauth import Session, load_persistent_session, save_persistent_session


class BackupTests(unittest.TestCase):
    def test_consistent_snapshot_and_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data, secrets, restored_data, restored_secrets = (
                root / name for name in ("data", "secrets", "restored-data", "restored-secrets"))
            for directory in (data, secrets, restored_data, restored_secrets):
                directory.mkdir(mode=0o700)
            key = secrets / "credential.key"
            key.write_bytes(Fernet.generate_key())
            key.chmod(0o600)
            with patch.dict(os.environ, {"REPLIQUE_DATA_DIR": str(data),
                                      "REPLIQUE_CREDENTIAL_KEY_FILE": str(key)}):
                code = create_invitation()
                save_persistent_session(Session("owner-browser", "client", "owner", None, "", "test-refresh",
                                                {"openid", "resource.invoke", "chatgpt.tokens.use.direct"}, 0))
                snapshot = root / "snapshot"
                create(snapshot)
                check_snapshot(snapshot)
                drill(snapshot)
                restore(snapshot, restored_data, restored_secrets / "credential.key")
                with patch.dict(os.environ, {"REPLIQUE_DATA_DIR": str(restored_data),
                                          "REPLIQUE_CREDENTIAL_KEY_FILE": str(restored_secrets / "credential.key")}):
                    self.assertEqual(load_persistent_session("", owner=True).refresh, "test-refresh")
                    with database() as db:
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM invitations").fetchone()[0], 1)
                with self.assertRaises(ValueError):
                    restore(snapshot, restored_data, restored_secrets / "credential.key")
                public_data = root / "public-data"
                public_data.mkdir(mode=0o755)
                public_data.chmod(0o755)
                with self.assertRaises(ValueError):
                    restore(snapshot, public_data, restored_secrets / "unused.key")
                self.assertEqual((snapshot / "credential.key").stat().st_mode & 0o777, 0o600)
                self.assertEqual((snapshot / "accounts.sqlite3").stat().st_mode & 0o777, 0o600)
                (snapshot / "oauth-session.enc").write_bytes(b"damaged")
                with self.assertRaises(ValueError):
                    check_snapshot(snapshot)
                self.assertGreater(len(code), 16)


if __name__ == "__main__":
    unittest.main()
