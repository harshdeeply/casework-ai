"""A complete customer escalation using synthetic support and delivery data."""
import json
from pathlib import Path
from .core import CaseStore, Conflict
from .sink import DemoDesk

ROOT = Path(__file__).resolve().parents[1]


def run():
    scenario = json.loads((ROOT / "examples" / "incident.json").read_text())
    policy = json.loads((ROOT / "examples" / "runbook.json").read_text())
    store, desk = CaseStore(), DemoDesk()
    for attempt in scenario["attempts"]:
        store.add_attempt(attempt)
    opened = store.open_case(scenario["ticket"], policy)
    case_id = opened["case_id"]
    before = store.get(case_id, "acme-demo")
    store.add_attempt(scenario["next_attempt"])
    stale_blocked = False
    try:
        store.decide(case_id, "acme-demo", "ops-reviewer", "approve")
    except Conflict:
        stale_blocked = True
    refreshed = store.refresh(case_id, "acme-demo", policy)
    store.decide(case_id, "acme-demo", "ops-reviewer", "approve")
    handed_off = store.handoff("acme-demo", desk.send)
    return {"initial_finding": before["finding"], "stale_review_blocked": stale_blocked,
            "refreshed_finding": refreshed["finding"], "handoff": handed_off,
            "desk_messages": desk.list(), "metrics": store.metrics("acme-demo")}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
