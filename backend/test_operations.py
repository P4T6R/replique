"""Aggregate diagnostics are useful without retaining visitor content."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.operations import record_generation, report


class OperationsTests(unittest.TestCase):
    def test_counts_latency_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"REPLIQUE_DATA_DIR": directory}):
            for duration in (100, 200, 1000):
                self.assertTrue(record_generation("owner_chatgpt", "success", duration))
            self.assertTrue(record_generation("owner_chatgpt", "quota", 50))
            self.assertFalse(record_generation("owner_chatgpt", "secret-token", 30))
            result = report(1)
            self.assertEqual(result["outcomes"], {"success": 3, "quota": 1})
            self.assertEqual(result["success_latency_ms"], {"median": 200, "p95": 1000, "max": 1000})
            with sqlite3.connect(Path(directory) / "operations.sqlite3") as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(generation_events)")}
            self.assertEqual(columns, {"created_at", "provider", "outcome", "duration_ms"})


if __name__ == "__main__":
    unittest.main()
