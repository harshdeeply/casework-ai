"""Loopback-only operator demo; an identity proxy is required for deployment."""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import CaseStore, Conflict
from .provider import model_draft
from .sink import DemoDesk, HTTPSDesk

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "examples" / "runbook.json").read_text())
STORE = CaseStore(os.environ.get("CASEWORK_DB", "casework-webhook.sqlite3"))
DESK = DemoDesk(os.environ.get("CASEWORK_DEMO_DESK_DB", "supportdesk-webhook.sqlite3"))
OPERATOR_KEY = os.environ.get("CASEWORK_OPERATOR_KEY", "local-operator")
INGEST_KEY = os.environ.get("CASEWORK_INGEST_KEY", "local-ingest")


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 16384:
            raise ValueError("request body must be 1–16384 bytes")
        result = json.loads(self.rfile.read(length))
        if not isinstance(result, dict):
            raise ValueError("JSON object required")
        return result

    def require(self, kind):
        expected = OPERATOR_KEY if kind == "operator" else INGEST_KEY
        provided = self.headers.get("Authorization", "")
        if not provided.startswith("Bearer ") or not hmac.compare_digest(provided[7:], expected):
            raise PermissionError("invalid credential")

    def customer(self):
        customer = self.headers.get("X-Demo-Customer", "acme-demo")
        if not customer or len(customer) > 128:
            raise ValueError("invalid customer scope")
        return customer

    def route(self):
        path = urlparse(self.path).path
        if self.command == "GET" and path == "/":
            data = (ROOT / "examples" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if self.command == "GET" and path == "/health":
            return self.respond(200, {"status": "ok"})
        if self.command == "POST" and path == "/api/attempts":
            self.require("ingest")
            return self.respond(201, {"inserted": STORE.add_attempt(self.body())})
        if self.command == "POST" and path == "/api/source-coverage":
            self.require("ingest")
            return self.respond(200, {"updated": STORE.set_coverage(self.body())})
        self.require("operator")
        customer = self.customer()
        if self.command == "GET" and path == "/api/cases":
            return self.respond(200, STORE.list(customer))
        if self.command == "GET" and path == "/api/metrics":
            return self.respond(200, STORE.metrics(customer))
        if self.command == "GET" and path == "/api/desk":
            return self.respond(200, [m for m in DESK.list() if m["customer_id"] == customer])
        if self.command == "POST" and path == "/api/cases":
            payload = self.body()
            if payload.get("customer_id") != customer:
                raise PermissionError("ticket customer differs from operator scope")
            generator = model_draft if os.environ.get("CASEWORK_MODEL_DRAFT") == "1" else None
            return self.respond(201, STORE.open_case(payload, POLICY, generator))
        parts = path.split("/")
        if len(parts) in (4, 5) and parts[:3] == ["", "api", "cases"]:
            case_id = parts[3]
            if self.command == "GET" and len(parts) == 4:
                return self.respond(200, STORE.get(case_id, customer))
            if self.command == "POST" and len(parts) == 5 and parts[4] == "refresh":
                generator = model_draft if os.environ.get("CASEWORK_MODEL_DRAFT") == "1" else None
                return self.respond(200, STORE.refresh(case_id, customer, POLICY, generator))
            if self.command == "POST" and len(parts) == 5 and parts[4] == "decision":
                body = self.body()
                return self.respond(200, STORE.decide(case_id, customer, body.get("reviewer"), body.get("decision"),
                                                      body.get("final_message"), body.get("acknowledge_uncertainty", False)))
        if self.command == "POST" and path == "/api/handoff":
            url = os.environ.get("CASEWORK_HANDOFF_URL")
            adapter = HTTPSDesk(url, os.environ.get("CASEWORK_HANDOFF_TOKEN")) if url else DESK
            return self.respond(200, STORE.handoff(customer, adapter.send))
        self.respond(404, {"error": "not found"})

    def handle_request(self):
        try:
            self.route()
        except PermissionError:
            self.respond(401, {"error": "unauthorized"})
        except KeyError:
            self.respond(404, {"error": "case not found"})
        except Conflict as exc:
            self.respond(409, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.respond(400, {"error": str(exc)})

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()


if __name__ == "__main__":
    scenario = json.loads((ROOT / "examples" / "incident.json").read_text())
    if not STORE.db.execute("SELECT 1 FROM attempts LIMIT 1").fetchone():
        for attempt in scenario["attempts"]:
            STORE.add_attempt(attempt)
        STORE.open_case(scenario["ticket"], POLICY)
    print("Casework operator demo: http://127.0.0.1:8080", flush=True)
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
