import json
import threading
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from casework import server
from casework.core import CaseStore
from casework.sink import DemoDesk


class APIFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_store, cls.original_desk = server.STORE, server.DESK
        server.STORE, server.DESK = CaseStore(), DemoDesk()
        cls.http = HTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.http.server_port
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.worker.start()
        cls.original_log = server.Handler.log_message
        server.Handler.log_message = lambda self, *args: None

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.worker.join(timeout=2)
        cls.http.server_close()
        server.Handler.log_message = cls.original_log
        server.STORE, server.DESK = cls.original_store, cls.original_desk

    def request(self, path, body=None, key=None, customer="acme-demo"):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"X-Demo-Customer": customer, "Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers,
                          method="POST" if data is not None else "GET")
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_full_authorized_flow_with_stale_evidence(self):
        fixture = json.loads((server.ROOT / "examples" / "incident.json").read_text())
        self.assertEqual(self.request("/health")[0], 200)
        self.assertEqual(self.request("/api/cases")[0], 401)
        self.assertEqual(self.request("/api/attempts", fixture["attempts"][0], "wrong")[0], 401)
        for a in fixture["attempts"]:
            self.assertEqual(self.request("/api/attempts", a, "local-ingest")[0], 201)
        self.assertEqual(self.request("/api/cases", fixture["ticket"], "local-operator", customer="other")[0], 401)
        status, opened = self.request("/api/cases", fixture["ticket"], "local-operator")
        self.assertEqual(status, 201)
        cid = opened["case_id"]
        self.assertEqual(self.request("/api/cases/" + cid, key="local-operator", customer="other")[0], 404)
        self.assertEqual(self.request("/api/attempts", fixture["next_attempt"], "local-ingest")[0], 201)
        decision = {"reviewer": "support-1", "decision": "approve"}
        self.assertEqual(self.request("/api/cases/" + cid + "/decision", decision, "local-operator")[0], 409)
        self.assertEqual(self.request("/api/cases/" + cid + "/refresh", {}, "local-operator")[1]["finding"], "ACKNOWLEDGED")
        self.assertEqual(self.request("/api/cases/" + cid + "/decision", decision, "local-operator")[0], 200)
        self.assertEqual(self.request("/api/handoff", {}, "local-operator")[1][0]["result"], "handed_off")
        desk = self.request("/api/desk", key="local-operator")[1]
        self.assertEqual(len(desk), 1)
        self.assertEqual(desk[0]["ticket_id"], fixture["ticket"]["ticket_id"])
        self.assertEqual(self.request("/api/metrics", key="local-operator")[1]["total"], 1)

    def test_invalid_input_and_unsupported_route(self):
        self.assertEqual(self.request("/api/attempts", {"invalid": True}, "local-ingest")[0], 400)
        self.assertEqual(self.request("/api/no-such-endpoint", key="local-operator")[0], 404)
        self.assertEqual(self.request("/api/cases/not-found", key="local-operator")[0], 404)

    def test_oversized_body_is_rejected(self):
        status, response = self.request("/api/cases", {"padding":"x" * 17000}, "local-operator")
        self.assertEqual(status, 400)
        self.assertIn("16384", response["error"])


if __name__ == "__main__":
    unittest.main()
