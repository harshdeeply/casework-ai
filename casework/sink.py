"""Support desk adapters. A separate local database models an external sink."""
import http.client
import json
import sqlite3
from urllib.parse import urlsplit


class DemoDesk:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS messages (handoff_id TEXT PRIMARY KEY,payload TEXT NOT NULL)")

    def send(self, payload):
        with self.db:
            row = self.db.execute("SELECT payload FROM messages WHERE handoff_id=?", (payload["handoff_id"],)).fetchone()
            content = json.dumps(payload, sort_keys=True)
            if row and row[0] != content:
                raise ValueError("handoff ID collision")
            self.db.execute("INSERT OR IGNORE INTO messages VALUES(?,?)", (payload["handoff_id"], content))

    def list(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM messages ORDER BY handoff_id")]


class HTTPSDesk:
    def __init__(self, url, token):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("desk endpoint must be HTTPS without embedded credentials")
        if not token:
            raise ValueError("desk token required")
        self.host, self.port, self.path, self.token = parsed.hostname, parsed.port, parsed.path or "/", token
        if parsed.query:
            self.path += "?" + parsed.query

    def send(self, payload):
        body = json.dumps(payload).encode()
        conn = http.client.HTTPSConnection(self.host, self.port, timeout=8)
        try:
            conn.request("POST", self.path, body=body,
                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token,
                                  "Idempotency-Key": payload["handoff_id"]})
            response = conn.getresponse()
            response.read(2048)
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"desk returned HTTP {response.status}")
        finally:
            conn.close()
