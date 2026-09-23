"""Deterministic offline eval: retrieval relevance, abstention, citation integrity."""
import json
from pathlib import Path
from .core import draft_response, evidence, validate_draft

ROOT = Path(__file__).resolve().parents[1]


def evaluate():
    policy = json.loads((ROOT / "examples" / "policy.json").read_text())
    cases = json.loads((ROOT / "examples" / "eval.json").read_text())
    rows = []
    for case in cases:
        snippets = evidence(policy, case["question"])
        draft = validate_draft(draft_response(case["question"], snippets), snippets)
        rows.append({"question": case["question"], "expected": case["expected"],
                     "observed": draft["citations"], "pass": case["expected"] in draft["citations"]
                     if case["expected"] else not draft["citations"]})
    return {"passed": sum(r["pass"] for r in rows), "total": len(rows), "cases": rows}


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] == result["total"] else 1)
