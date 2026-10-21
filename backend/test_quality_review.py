"""A human-only scorecard rejects incomplete or duplicated reviews."""

import csv
import tempfile
import unittest
from pathlib import Path

from backend.quality_review import DIMENSIONS, FIELDS, case_ids, report, template


class QualityReviewTests(unittest.TestCase):
    def test_two_complete_reviews_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            template(path, "owner-model")
            with path.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2 * len(case_ids()))
            with self.assertRaises(ValueError):
                report(path)
            for row in rows:
                for dimension in DIMENSIONS:
                    row[dimension] = "4"
                row["passes_case"] = "yes"
            rows[0]["passes_case"] = "no"
            with path.open("w", encoding="utf-8", newline="") as destination:
                writer = csv.DictWriter(destination, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            summary = report(path)
            self.assertEqual(summary["cases"], len(case_ids()))
            self.assertEqual(summary["mean_scores"]["naturalness"], 4)
            self.assertEqual(summary["cases_failed_by_either_reviewer"], [rows[0]["case_id"]])
            self.assertEqual(summary["cases_passed_by_both"], len(case_ids()) - 1)
            self.assertLess(summary["reviewer_agreement_percent"], 100)
            rows[2]["case_id"] = rows[0]["case_id"]
            with path.open("w", encoding="utf-8", newline="") as destination:
                writer = csv.DictWriter(destination, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                report(path)


if __name__ == "__main__":
    unittest.main()
