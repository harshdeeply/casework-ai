import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from casework.core import CaseStore, Conflict, baseline_draft
from casework.importer import read_export
from casework.provider import model_draft
from casework.sink import HTTPSDesk

POLICY = json.loads((Path(__file__).resolve().parents[1] / "examples" / "runbook.json").read_text())
ATTEMPT = {"attempt_id":"attempt-1","customer_id":"c","event_id":"e","endpoint_id":"ep",
           "sequence":1,"sent_at":"2026-09-22T17:00:00Z","outcome":"acknowledged","http_status":200,
           "next_retry_at":None}
TICKET = {"ticket_id":"t","customer_id":"c","event_id":"e","endpoint_id":"ep",
          "subject":"Question about delivery","description":"Please check logs"}


class DurableTests(unittest.TestCase):
    def test_jsonl_and_csv_export_are_equivalent(self):
        root = Path(__file__).resolve().parents[1] / "examples"
        records = read_export(root / "attempts.jsonl")
        self.assertEqual(records, read_export(root / "attempts.csv"))
        store = CaseStore()
        self.assertEqual(store.import_attempts(records), {"inserted": 2, "duplicates": 0})
        self.assertEqual(store.import_attempts(records), {"inserted": 0, "duplicates": 2})

    def test_batch_conflict_rolls_back_every_row(self):
        store = CaseStore()
        first = {**ATTEMPT, "attempt_id": "first"}
        conflicting = {**ATTEMPT, "attempt_id": "first", "http_status": 202}
        with self.assertRaises(Conflict):
            store.import_attempts([first, conflicting])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)

    def test_export_and_coverage_manifest_commit_atomically(self):
        root = Path(__file__).resolve().parents[1] / "examples"
        records = read_export(root / "attempts.jsonl")
        coverage = json.loads((root / "coverage.json").read_text())
        store = CaseStore()
        self.assertEqual(store.import_attempts(records, coverage),
                         {"inserted": 2, "duplicates": 0, "coverage_updated": 1})
        case = store.get(store.open_case(json.loads((root / "incident.json").read_text())["ticket"], POLICY)["case_id"], "acme-demo")
        self.assertEqual(case["coverage_state"], "BEHIND_RETRY")
        changed = [{**records[0], "outcome": "acknowledged", "http_status": 200, "next_retry_at": None}]
        with self.assertRaises(Conflict):
            store.import_attempts(changed, [{**coverage[0], "complete_through":"2026-09-22T17:10:00Z"}])
        self.assertTrue(store.get(case["id"], "acme-demo")["evidence_current"])

    def test_batch_validation_fails_before_any_write(self):
        store = CaseStore()
        with self.assertRaises(ValueError):
            store.import_attempts([ATTEMPT, {**ATTEMPT, "attempt_id":"bad", "sequence":0}])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)

    def test_restart_preserves_case_review_and_outbox(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "cases.sqlite3")
            first = CaseStore(path)
            first.add_attempt(ATTEMPT)
            case_id = first.open_case(TICKET, POLICY)["case_id"]
            first.decide(case_id, "c", "reviewer", "approve")
            first.db.close()
            resumed = CaseStore(path)
            self.assertEqual(resumed.get(case_id, "c")["status"], "approved")
            self.assertEqual(len(resumed.handoff("c", lambda payload: None)), 1)
            self.assertEqual(resumed.handoff("c", lambda payload: None), [])
            resumed.db.close()

    def test_concurrent_duplicate_attempt_is_inserted_once(self):
        store = CaseStore()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(store.add_attempt, [ATTEMPT] * 30))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 1)

    def test_model_refusal_and_invalid_json_do_not_create_case(self):
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()
        for output in ({"status":"incomplete","output":[]},
                       {"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"not-json"}]}]}):
            with self.subTest(output=output):
                store = CaseStore()
                store.add_attempt(ATTEMPT)
                with patch.dict("os.environ", {"OPENAI_API_KEY":"test-key"}), patch(
                    "casework.provider.urlopen", return_value=Response(json.dumps(output).encode())):
                    with self.assertRaises(ValueError):
                        store.open_case(TICKET, POLICY, model_draft)
                self.assertEqual(store.list("c"), [])

    def test_model_output_cannot_change_finding(self):
        store = CaseStore()
        store.add_attempt(ATTEMPT)
        def wrong_model(ticket, finding, evidence):
            return {**baseline_draft(ticket, finding, evidence), "finding":"NO_RECORD"}
        with self.assertRaisesRegex(ValueError, "finding"):
            store.open_case(TICKET, POLICY, wrong_model)

    def test_https_adapter_sends_idempotency_key_and_rejects_redirect(self):
        sent = []
        class Response:
            status = 204
            def read(self, length):
                return b""
        class Connection:
            def __init__(self, host, port, timeout):
                self.host = host
            def request(self, method, path, body, headers):
                sent.append((method,path,json.loads(body),headers))
            def getresponse(self):
                return Response()
            def close(self):
                pass
        adapter = HTTPSDesk("https://support.example.test/api/notes", "test-token")
        with patch("casework.sink.http.client.HTTPSConnection", Connection):
            adapter.send({"handoff_id":"h-1","message":"reviewed"})
        self.assertEqual(sent[0][3]["Idempotency-Key"], "h-1")
        self.assertEqual(sent[0][1], "/api/notes")
        class Redirect(Response):
            status = 302
        Connection.getresponse = lambda self: Redirect()
        with patch("casework.sink.http.client.HTTPSConnection", Connection):
            with self.assertRaises(RuntimeError):
                adapter.send({"handoff_id":"h-1","message":"reviewed"})


if __name__ == "__main__":
    unittest.main()
