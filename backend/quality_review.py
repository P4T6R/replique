"""Two-person review sheet for real hosted outputs, without storing conversations."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path

DATASET = Path(__file__).resolve().parent / "evals" / "conversation_cases.json"
DIMENSIONS = ("groundedness", "naturalness", "variation", "boundaries")
FIELDS = ("case_id", "reviewer", "model", *DIMENSIONS, "passes_case")


def case_ids() -> list[str]:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    ids = [case["id"] for case in dataset["cases"]]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Evaluation case IDs are missing or duplicated")
    return ids


def template(output: Path, model: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model):
        raise ValueError("A fixed model slug is required")
    with output.open("x", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        for case_id in case_ids():
            for reviewer in ("testeur1", "testeur2"):
                writer.writerow({"case_id": case_id, "reviewer": reviewer, "model": model})


def report(source: Path) -> dict:
    with source.open(encoding="utf-8", newline="") as document:
        reader = csv.DictReader(document)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("Review sheet columns are invalid")
        rows = list(reader)
    ids = set(case_ids())
    reviewers = {row["reviewer"] for row in rows}
    models = {row["model"] for row in rows}
    if len(reviewers) != 2 or "" in reviewers or len(models) != 1 or "" in models:
        raise ValueError("Exactly two reviewers and one fixed model are required")
    if len(rows) != len(ids) * 2 or {row["case_id"] for row in rows} != ids:
        raise ValueError("Every case must be reviewed twice")
    ratings: dict[str, list[int]] = {dimension: [] for dimension in DIMENSIONS}
    failing = set()
    seen = set()
    for row in rows:
        pair = row["case_id"], row["reviewer"]
        if pair in seen or row["case_id"] not in ids or row["passes_case"] not in {"yes", "no"}:
            raise ValueError("Review sheet contains duplicate, unknown or incomplete cases")
        seen.add(pair)
        if row["passes_case"] == "no":
            failing.add(row["case_id"])
        for dimension in DIMENSIONS:
            value = row[dimension]
            if value not in {"1", "2", "3", "4", "5"}:
                raise ValueError("Every quality dimension must be rated from 1 to 5")
            ratings[dimension].append(int(value))
    return {"model": next(iter(models)), "cases": len(ids), "reviews": len(rows),
            "mean_scores": {name: round(statistics.mean(values), 2) for name, values in ratings.items()},
            "cases_failed_by_either_reviewer": sorted(failing)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Review real outputs on the synthetic conversation corpus")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("template")
    make.add_argument("--model", required=True)
    make.add_argument("--output", required=True, type=Path)
    read = commands.add_parser("report")
    read.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "template":
            template(args.output, args.model)
            print("Review sheet created")
        else:
            print(json.dumps(report(args.input), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Quality review failed: {error}\n")


if __name__ == "__main__":
    main()
