"""Run with python -m casework.server. Synthetic policies and tenants only."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import CaseStore
from .provider import model_draft

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "examples" / "policy.json").read_text())
STORE = CaseStore(os.environ.get("CASEWORK_DB", "casework.sqlite3"))


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def request_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 8192:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(size))

    def tenant(self):
        # Demo boundary. Replace with verified identity and authorization in production.
        return self.headers.get("X-Demo-Tenant", "demo")

    def route(self):
        path = urlparse(self.path).path
        if self.command == "GET" and path == "/":
            data = (ROOT / "examples" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.command == "GET" and path == "/api/policy":
            self.send_json(200, POLICY)
        elif self.command == "GET" and path == "/api/cases":
            self.send_json(200, STORE.list(self.tenant()))
        elif self.command == "POST" and path == "/api/cases":
            body = self.request_body()
            generator = model_draft if os.environ.get("CASEWORK_MODEL_DRAFT") == "1" else None
            self.send_json(201, STORE.submit(self.tenant(), body.get("question", ""), POLICY, generator))
        elif self.command == "GET" and path.startswith("/api/cases/"):
            self.send_json(200, STORE.get(path.split("/")[3], self.tenant()))
        elif self.command == "POST" and path.endswith("/decision") and path.startswith("/api/cases/"):
            body = self.request_body()
            self.send_json(200, STORE.decide(path.split("/")[3], self.tenant(),
                                             body.get("actor"), body.get("decision"), body.get("final_answer")))
        elif self.command == "POST" and path == "/api/deliver":
            # Demo sink: stores outbox state. No message is sent to a real person.
            self.send_json(200, {"delivered": STORE.deliver(lambda payload: None)})
        else:
            self.send_json(404, {"error": "not found"})

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        try:
            self.route()
        except KeyError as exc:
            self.send_json(404, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})


if __name__ == "__main__":
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8080"))
    print(f"Casework demo: http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
