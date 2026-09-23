import unittest
from unittest.mock import patch
from io import BytesIO
import json
from casework.core import CaseStore, evidence, validate_draft
from casework.evaluate import evaluate
from casework.provider import model_draft

POLICY = [{"id": "R1", "title": "Rent records", "text": "Record rent amount and date."}]


class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.store = CaseStore()

    def test_approval_and_delivery(self):
        case = self.store.submit("tenant-a", "How should I record rent?", POLICY)
        self.assertEqual(case["draft"]["citations"], ["R1"])
        with self.assertRaises(KeyError):
            self.store.get(case["id"], "tenant-b")
        self.store.decide(case["id"], "tenant-a", "reviewer", "approve")
        sent = []
        self.assertEqual(self.store.deliver(sent.append), 1)
        self.assertEqual(self.store.deliver(sent.append), 0)
        self.assertEqual(len(sent), 1)
        with self.assertRaises(ValueError):
            self.store.decide(case["id"], "tenant-a", "reviewer", "approve")

    def test_uncertain_needs_human_answer(self):
        case = self.store.submit("tenant-a", "Mars weather?", POLICY)
        with self.assertRaises(ValueError):
            self.store.decide(case["id"], "tenant-a", "reviewer", "approve")
        self.store.decide(case["id"], "tenant-a", "reviewer", "approve", "Escalated to operations.")

    def test_hallucinated_citation_rejected(self):
        with self.assertRaises(ValueError):
            validate_draft({"answer": "Sure", "citations": ["fake"], "confidence": "evidence_found"}, POLICY)

    def test_offline_eval(self):
        report = evaluate()
        self.assertEqual(report["passed"], report["total"])

    def test_model_adapter_enforces_structured_output(self):
        model_reply = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps({"answer": "Record rent.",
                "citations": ["R1"], "confidence": "evidence_found"})}]}]}
        class Response(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()
        def fake_urlopen(request, timeout):
            body = json.loads(request.data)
            self.assertEqual(body["store"], False)
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertEqual(timeout, 30)
            return Response(json.dumps(model_reply).encode())
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch("casework.provider.urlopen", fake_urlopen):
            case = self.store.submit("tenant-a", "Record rent", POLICY, generator=model_draft)
        self.assertEqual(case["draft"]["citations"], ["R1"])


if __name__ == "__main__":
    unittest.main()
