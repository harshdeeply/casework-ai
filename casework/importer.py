"""Load a support team's sanitized JSONL/CSV delivery export atomically."""
import argparse
import csv
import json
from pathlib import Path
from .core import CaseStore, validate_attempt, validate_coverage


def read_export(path):
    file = Path(path)
    if file.suffix == ".jsonl":
        with file.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    if file.suffix == ".csv":
        with file.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row["sequence"] = int(row["sequence"])
            row["http_status"] = int(row["http_status"]) if row["http_status"] else None
            row["next_retry_at"] = row["next_retry_at"] or None
        return rows
    raise ValueError("export must be .jsonl or .csv")


def main():
    parser = argparse.ArgumentParser(description="Validate and import sanitized delivery attempts")
    parser.add_argument("file")
    parser.add_argument("--db", default="casework-webhook.sqlite3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--coverage", help="JSON array of source-declared completeness windows")
    args = parser.parse_args()
    records = read_export(args.file)
    coverage = json.loads(Path(args.coverage).read_text()) if args.coverage else None
    if coverage is not None and not isinstance(coverage, list):
        raise ValueError("coverage manifest must be an array")
    if args.dry_run:
        for record in records:
            validate_attempt(record)
        for window in coverage or []:
            validate_coverage(window)
        result = {"validated": len(records), "coverage_validated": len(coverage or []), "written": False}
    else:
        store = CaseStore(args.db)
        result = store.import_attempts(records, coverage)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
