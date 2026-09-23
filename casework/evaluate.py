"""Transparent fixture regression; no claim of real-model answer quality."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import CaseStore

ROOT = Path(__file__).resolve().parents[1]


def evaluate():
    fixtures = json.loads((ROOT / "examples" / "eval.json").read_text())
    policy = json.loads((ROOT / "examples" / "runbook.json").read_text())
    results = []
    for index, fixture in enumerate(fixtures):
        # Inspect 30 seconds after the final attempt, so a retry one minute later is still pending.
        inspection_time = datetime(2026, 9, 22, 17, 0, tzinfo=timezone.utc) + timedelta(minutes=max(1, len(fixture["trace"])) * 2, seconds=30)
        if fixture.get("overdue"):
            inspection_time += timedelta(minutes=5)
        store = CaseStore(clock=lambda: inspection_time)
        event_id = f"event-{index}"
        for sequence, (outcome, status, retry) in enumerate(fixture["trace"], 1):
            time = datetime(2026, 9, 22, 17, 0, tzinfo=timezone.utc) + timedelta(minutes=sequence * 2)
            store.add_attempt({"attempt_id": f"attempt-{index}-{sequence}", "customer_id": "fixture",
                               "event_id": event_id, "endpoint_id": "billing", "sequence": sequence,
                               "sent_at": time.isoformat(), "outcome": outcome, "http_status": status,
                               "next_retry_at": (time + timedelta(minutes=1)).isoformat() if retry else None})
        ticket = {"ticket_id": f"ticket-{index}", "customer_id": "fixture", "event_id": event_id,
                  "endpoint_id": "billing", "subject": fixture["name"], "description": "Please investigate this delivery."}
        opened = store.open_case(ticket, policy)
        case = store.get(opened["case_id"], "fixture")
        passed = case["finding"] == fixture["expected"] and case["evidence_current"]
        results.append({"scenario": fixture["name"], "expected": fixture["expected"],
                        "observed": case["finding"], "pass": passed})
    return {"passed": sum(row["pass"] for row in results), "total": len(results), "scenarios": results}


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)
