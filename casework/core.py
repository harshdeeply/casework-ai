import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def evidence(policy, question, limit=3):
    terms = set(re.findall(r"[a-z0-9]+", question.lower())) - {
        "a", "an", "the", "is", "to", "for", "and", "of", "my", "i", "can", "what", "how", "do", "on", "we", "need"
    }
    scored = []
    for item in policy:
        title_words = set(re.findall(r"[a-z0-9]+", item["title"].lower()))
        body_words = set(re.findall(r"[a-z0-9]+", item["text"].lower()))
        score = sum(2 if word in title_words else 1 for word in terms if word in title_words | body_words)
        if score:
            scored.append((score, item["id"], item))
    return [item for _, _, item in sorted(scored, key=lambda row: (-row[0], row[1]))[:limit]]


def draft_response(question, snippets):
    if not snippets:
        return {"answer": "I could not find an applicable policy. Route this case for human review.",
                "citations": [], "confidence": "unresolved"}
    return {"answer": "Relevant policy: " + " ".join(s["text"] for s in snippets),
            "citations": [s["id"] for s in snippets], "confidence": "evidence_found"}


def validate_draft(draft, snippets):
    allowed = {s["id"] for s in snippets}
    if not isinstance(draft, dict) or not isinstance(draft.get("answer"), str):
        raise ValueError("draft must contain an answer string")
    citations = draft.get("citations")
    if not isinstance(citations, list) or len(citations) != len(set(citations)) or any(c not in allowed for c in citations):
        raise ValueError("draft cites unknown or duplicate policy IDs")
    if not citations and draft.get("confidence") != "unresolved":
        raise ValueError("uncited draft must be unresolved")
    if citations and draft.get("confidence") != "evidence_found":
        raise ValueError("cited draft must be evidence_found")
    if len(draft["answer"]) > 4000:
        raise ValueError("draft too long")
    return draft


class CaseStore:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cases (
              id TEXT PRIMARY KEY, tenant TEXT NOT NULL, question TEXT NOT NULL,
              status TEXT NOT NULL, draft TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
              action TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL,
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
              case_id TEXT PRIMARY KEY, payload TEXT NOT NULL, delivered_at TEXT);
        """)

    def _event(self, case_id, action, actor, details):
        self.db.execute("INSERT INTO events(case_id,action,actor,details,created_at) VALUES(?,?,?,?,?)",
                        (case_id, action, actor, json.dumps(details, sort_keys=True), utcnow()))

    def submit(self, tenant, question, policy, generator=None):
        if not tenant or not question or len(question) > 4000:
            raise ValueError("tenant and question are required; question max 4000 characters")
        snippets = evidence(policy, question)
        draft = validate_draft(generator(question, snippets) if generator else draft_response(question, snippets), snippets)
        record = {"id": str(uuid.uuid4()), "tenant": tenant, "question": question,
                  "status": "pending_review", "draft": draft, "created_at": utcnow()}
        with self.lock, self.db:
            self.db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,?)",
                            (record["id"], tenant, question, record["status"], json.dumps(draft),
                             record["created_at"], record["created_at"]))
            self._event(record["id"], "drafted", "system", {"policy_ids": draft["citations"]})
        return record

    def get(self, case_id, tenant):
        row = self.db.execute("SELECT * FROM cases WHERE id=? AND tenant=?", (case_id, tenant)).fetchone()
        if row is None:
            raise KeyError("case not found")
        record = dict(row)
        record["draft"] = json.loads(record["draft"])
        record["events"] = [dict(e) for e in self.db.execute(
            "SELECT action,actor,details,created_at FROM events WHERE case_id=? ORDER BY id", (case_id,))]
        return record

    def list(self, tenant):
        return [{"id": r["id"], "status": r["status"], "question": r["question"]}
                for r in self.db.execute("SELECT * FROM cases WHERE tenant=? ORDER BY created_at DESC", (tenant,))]

    def decide(self, case_id, tenant, actor, decision, final_answer=None):
        if decision not in ("approve", "reject") or not actor:
            raise ValueError("decision must be approve or reject and actor is required")
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM cases WHERE id=? AND tenant=?", (case_id, tenant)).fetchone()
            if row is None:
                raise KeyError("case not found")
            if row["status"] != "pending_review":
                raise ValueError("case already reviewed")
            draft = json.loads(row["draft"])
            if final_answer is not None:
                if not isinstance(final_answer, str) or not final_answer.strip() or len(final_answer) > 4000:
                    raise ValueError("final_answer must be 1-4000 characters")
                draft["answer"] = final_answer
            if decision == "approve" and draft["confidence"] == "unresolved" and final_answer is None:
                raise ValueError("unresolved answer needs a human-authored final_answer")
            status = "approved" if decision == "approve" else "rejected"
            self.db.execute("UPDATE cases SET status=?, draft=?, updated_at=? WHERE id=?",
                            (status, json.dumps(draft), utcnow(), case_id))
            self._event(case_id, decision, actor, {"answer_sha256": hashlib.sha256(draft["answer"].encode()).hexdigest()})
            if decision == "approve":
                self.db.execute("INSERT INTO outbox(case_id,payload) VALUES(?,?)",
                                (case_id, json.dumps({"case_id": case_id, "tenant": tenant, "answer": draft["answer"]})))
        return self.get(case_id, tenant)

    def deliver(self, send):
        """Call a delivery adapter; keep failed entries for retry. Adapter must be idempotent on case_id."""
        delivered = 0
        with self.lock:
            pending = self.db.execute("SELECT case_id,payload FROM outbox WHERE delivered_at IS NULL").fetchall()
            for item in pending:
                send(json.loads(item["payload"]))
                with self.db:
                    self.db.execute("UPDATE outbox SET delivered_at=? WHERE case_id=? AND delivered_at IS NULL",
                                    (utcnow(), item["case_id"]))
                    self._event(item["case_id"], "delivered", "system", {})
                delivered += 1
        return delivered
