"""Evidence-bound support workflow for SaaS webhook delivery escalations."""
import hashlib
import json
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone


class Conflict(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return dt.astimezone(timezone.utc).isoformat()


def validate_attempt(value):
    if not isinstance(value, dict):
        raise ValueError("attempt must be an object")
    result = {}
    for key in ("attempt_id", "customer_id", "event_id", "endpoint_id"):
        item = value.get(key)
        if not isinstance(item, str) or not 1 <= len(item) <= 128:
            raise ValueError(f"invalid {key}")
        result[key] = item
    sequence = value.get("sequence")
    if type(sequence) is not int or not 1 <= sequence <= 1000:
        raise ValueError("sequence must be an integer from 1 to 1000")
    result["sequence"] = sequence
    result["sent_at"] = parse_time(value.get("sent_at"))
    result["outcome"] = value.get("outcome")
    result["http_status"] = value.get("http_status")
    retry = value.get("next_retry_at")
    result["next_retry_at"] = parse_time(retry) if retry is not None else None
    if result["outcome"] == "acknowledged":
        if type(result["http_status"]) is not int or not 200 <= result["http_status"] < 300 or retry:
            raise ValueError("acknowledged requires 2xx and no retry")
    elif result["outcome"] == "http_error":
        if type(result["http_status"]) is not int or not 400 <= result["http_status"] <= 599:
            raise ValueError("http_error requires 4xx/5xx")
    elif result["outcome"] == "timeout":
        if result["http_status"] is not None:
            raise ValueError("timeout cannot have HTTP status")
    else:
        raise ValueError("unsupported attempt outcome")
    if result["next_retry_at"] and result["next_retry_at"] <= result["sent_at"]:
        raise ValueError("retry must follow attempt")
    return result


def validate_ticket(value):
    if not isinstance(value, dict):
        raise ValueError("ticket must be an object")
    result = {}
    for key, maximum in (("ticket_id", 128), ("customer_id", 128), ("event_id", 128),
                         ("endpoint_id", 128), ("subject", 200), ("description", 2000)):
        item = value.get(key)
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= maximum:
            raise ValueError(f"invalid {key}")
        result[key] = item.strip()
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_coverage(value):
    """A source's claim about its complete export window, not a claim about downstream processing."""
    if not isinstance(value, dict) or set(value) != {"customer_id", "endpoint_id", "source", "complete_from", "complete_through"}:
        raise ValueError("coverage requires customer_id, endpoint_id, source, complete_from, complete_through")
    result = {}
    for key in ("customer_id", "endpoint_id", "source"):
        item = value[key]
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 128:
            raise ValueError(f"invalid {key}")
        result[key] = item.strip()
    result["complete_from"] = parse_time(value["complete_from"])
    result["complete_through"] = parse_time(value["complete_through"])
    if result["complete_from"] > result["complete_through"]:
        raise ValueError("coverage window is reversed")
    if result["complete_through"] > utcnow():
        raise ValueError("coverage cannot extend into the future")
    return result


def coverage_state(finding, attempts, coverage):
    if finding != "RETRY_UNOBSERVED":
        return "NOT_APPLICABLE"
    if not coverage:
        return "NOT_REPORTED"
    latest = max(attempts, key=lambda a: (a["sequence"], a["sent_at"], a["attempt_id"]))
    if coverage["complete_from"] > latest["sent_at"]:
        return "WINDOW_GAP"
    return "THROUGH_RETRY" if coverage["complete_through"] >= latest["next_retry_at"] else "BEHIND_RETRY"


def finding_for(attempts, as_of=None):
    """Observations only. An HTTP 2xx says nothing about downstream processing."""
    if not attempts:
        return "NO_RECORD"
    successes = [a for a in attempts if a["outcome"] == "acknowledged"]
    if len(successes) > 1:
        return "MULTIPLE_ACKS"
    if successes:
        return "ACKNOWLEDGED"
    latest = max(attempts, key=lambda a: (a["sequence"], a["sent_at"], a["attempt_id"]))
    if latest["next_retry_at"]:
        as_of = as_of or datetime.now(timezone.utc)
        return "RETRY_UNOBSERVED" if latest["next_retry_at"] <= as_of.isoformat() else "RETRY_SCHEDULED"
    return "FAILED_UNRESOLVED"


def evidence_for(policy, finding, attempts):
    runbooks = [item for item in policy["runbooks"] if finding in item["findings"]]
    if len(runbooks) != 1:
        raise ValueError("policy must have exactly one runbook for finding")
    return [{"id": f"attempt:{a['attempt_id']}", "type": "delivery_attempt", "data": a}
            for a in attempts] + [{"id": f"runbook:{runbooks[0]['id']}", "type": "runbook",
                                    "data": {"title": runbooks[0]["title"], "text": runbooks[0]["text"]}}]


def baseline_draft(ticket, finding, evidence, coverage=None):
    attempts = [e["data"] for e in evidence if e["type"] == "delivery_attempt"]
    citations = [e["id"] for e in evidence]
    if finding == "NO_RECORD":
        message = "We could not locate a matching delivery attempt in the available logs. We are investigating and will confirm what happened before suggesting a fix."
    elif finding == "ACKNOWLEDGED":
        success = next(a for a in attempts if a["outcome"] == "acknowledged")
        message = f"Our logs show your endpoint acknowledged event {ticket['event_id']} with HTTP {success['http_status']} at {success['sent_at']}. This does not confirm how your application processed it."
    elif finding == "MULTIPLE_ACKS":
        message = f"Our logs show more than one acknowledged delivery attempt for event {ticket['event_id']}. We are investigating the delivery history. Please use the event ID when checking how your application handled the event."
    elif finding == "RETRY_SCHEDULED":
        latest = max(attempts, key=lambda a: (a["sequence"], a["sent_at"], a["attempt_id"]))
        message = f"The most recent attempt for event {ticket['event_id']} was not acknowledged. Our logs show a retry scheduled for {latest['next_retry_at']}. We will check the next result."
    elif finding == "RETRY_UNOBSERVED":
        latest = max(attempts, key=lambda a: (a["sequence"], a["sent_at"], a["attempt_id"]))
        state = coverage_state(finding, attempts, coverage)
        if state == "BEHIND_RETRY":
            message = f"A retry for event {ticket['event_id']} was scheduled for {latest['next_retry_at']}, but the delivery export currently covers only through {coverage['complete_through']}. We cannot yet confirm whether that retry occurred."
        elif state == "WINDOW_GAP":
            message = f"A retry for event {ticket['event_id']} was scheduled for {latest['next_retry_at']}, but the available export does not cover the earlier attempt. We are checking the missing window before confirming the outcome."
        else:
            message = f"A retry for event {ticket['event_id']} was scheduled for {latest['next_retry_at']}, but no later attempt appears in the available logs. We are investigating the gap rather than assuming delivery succeeded or failed."
    else:
        message = f"The available logs show an unacknowledged delivery attempt for event {ticket['event_id']} and no recorded next retry. We are investigating before confirming a resolution."
    return {"customer_message": message, "internal_summary": f"{finding}: {ticket['subject']}",
            "finding": finding, "citations": citations}


def validate_draft(draft, finding, evidence):
    if not isinstance(draft, dict) or set(draft) != {"customer_message", "internal_summary", "finding", "citations"}:
        raise ValueError("draft shape does not match contract")
    for key, maximum in (("customer_message", 1500), ("internal_summary", 500)):
        if not isinstance(draft[key], str) or not 1 <= len(draft[key].strip()) <= maximum:
            raise ValueError(f"invalid draft {key}")
    allowed = {item["id"] for item in evidence}
    citations = draft["citations"]
    if draft["finding"] != finding:
        raise ValueError("draft changed the evidence-derived finding")
    if not isinstance(citations, list) or not citations or any(not isinstance(c, str) for c in citations) or len(citations) != len(set(citations)) or any(
            c not in allowed for c in citations):
        raise ValueError("missing, duplicated, or invented citations")
    if not any(c.startswith("runbook:") for c in citations):
        raise ValueError("runbook citation required")
    if finding != "NO_RECORD" and not any(c.startswith("attempt:") for c in citations):
        raise ValueError("delivery attempt citation required")
    return draft


class CaseStore:
    def __init__(self, path=":memory:", clock=None):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS attempts (
              attempt_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,event_id TEXT NOT NULL,
              endpoint_id TEXT NOT NULL,sequence INTEGER NOT NULL,sent_at TEXT NOT NULL,
              outcome TEXT NOT NULL,http_status INTEGER,next_retry_at TEXT,
              payload_hash TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS attempt_lookup ON attempts(customer_id,event_id,endpoint_id,sequence);
            CREATE TABLE IF NOT EXISTS source_coverage (
              customer_id TEXT NOT NULL,endpoint_id TEXT NOT NULL,source TEXT NOT NULL,
              complete_from TEXT NOT NULL,complete_through TEXT NOT NULL,
              PRIMARY KEY(customer_id,endpoint_id));
            CREATE TABLE IF NOT EXISTS cases (
              id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL,customer_id TEXT NOT NULL,
              event_id TEXT NOT NULL,endpoint_id TEXT NOT NULL,subject TEXT NOT NULL,
              description TEXT NOT NULL,ticket_hash TEXT NOT NULL,status TEXT NOT NULL,
              finding TEXT NOT NULL,evidence TEXT NOT NULL,evidence_hash TEXT NOT NULL,
              draft TEXT NOT NULL,policy_version TEXT NOT NULL,created_at TEXT NOT NULL,
              reviewed_at TEXT,reviewer TEXT, UNIQUE(customer_id,ticket_id));
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT NOT NULL REFERENCES cases(id),
              action TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
              case_id TEXT PRIMARY KEY REFERENCES cases(id),payload TEXT NOT NULL,
              delivered_at TEXT,attempts INTEGER NOT NULL DEFAULT 0,last_error_type TEXT);
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(cases)")}
        if "coverage_snapshot" not in columns:
            self.db.execute("ALTER TABLE cases ADD COLUMN coverage_snapshot TEXT NOT NULL DEFAULT 'null'")

    def set_coverage(self, value):
        item = validate_coverage(value)
        with self.lock, self.db:
            return self._put_coverage(item)

    def _put_coverage(self, item):
        prior = self._coverage(item["customer_id"], item["endpoint_id"])
        if prior == item:
            return False
        self.db.execute("""INSERT INTO source_coverage VALUES(?,?,?,?,?)
            ON CONFLICT(customer_id,endpoint_id) DO UPDATE SET source=excluded.source,
            complete_from=excluded.complete_from,complete_through=excluded.complete_through""",
            tuple(item.values()))
        return True

    def _coverage(self, customer_id, endpoint_id):
        row = self.db.execute("SELECT * FROM source_coverage WHERE customer_id=? AND endpoint_id=?",
                              (customer_id, endpoint_id)).fetchone()
        return dict(row) if row else None

    def _evidence_hash(self, attempts, coverage):
        return digest({"attempts": attempts, "source_coverage": coverage})

    def _attempts(self, customer_id, event_id, endpoint_id):
        rows = self.db.execute("""SELECT attempt_id,customer_id,event_id,endpoint_id,sequence,
               sent_at,outcome,http_status,next_retry_at FROM attempts
               WHERE customer_id=? AND event_id=? AND endpoint_id=? ORDER BY sequence,sent_at,attempt_id""",
               (customer_id, event_id, endpoint_id)).fetchall()
        return [dict(r) for r in rows]

    def add_attempt(self, attempt):
        attempt = validate_attempt(attempt)
        stamp = digest(attempt)
        with self.lock, self.db:
            existing = self.db.execute("SELECT payload_hash FROM attempts WHERE attempt_id=?", (attempt["attempt_id"],)).fetchone()
            if existing:
                if existing["payload_hash"] != stamp:
                    raise Conflict("attempt ID reused with different data")
                return False
            self.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (*attempt.values(), stamp))
            return True

    def import_attempts(self, values, coverage=None):
        """All-or-nothing batch ingestion for a sanitized support export."""
        normalized = [validate_attempt(value) for value in values]
        windows = [validate_coverage(value) for value in coverage] if coverage is not None else None
        stats = {"inserted": 0, "duplicates": 0}
        with self.lock, self.db:
            for item in normalized:
                stamp = digest(item)
                existing = self.db.execute("SELECT payload_hash FROM attempts WHERE attempt_id=?", (item["attempt_id"],)).fetchone()
                if existing:
                    if existing["payload_hash"] != stamp:
                        raise Conflict("attempt ID reused with different data")
                    stats["duplicates"] += 1
                    continue
                self.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (*item.values(), stamp))
                stats["inserted"] += 1
            if windows is not None:
                stats["coverage_updated"] = sum(self._put_coverage(item) for item in windows)
        return stats

    def _audit(self, case_id, action, actor, detail):
        self.db.execute("INSERT INTO audit(case_id,action,actor,detail,created_at) VALUES(?,?,?,?,?)",
                        (case_id, action, actor, json.dumps(detail, sort_keys=True), utcnow()))

    def open_case(self, ticket, policy, generator=None):
        ticket = validate_ticket(ticket)
        with self.lock, self.db:
            prior = self.db.execute("SELECT id,ticket_hash FROM cases WHERE customer_id=? AND ticket_id=?",
                                    (ticket["customer_id"], ticket["ticket_id"])).fetchone()
            if prior:
                if prior["ticket_hash"] != digest(ticket):
                    raise Conflict("ticket ID reused with different data")
                return {"case_id": prior["id"], "created": False}
            attempts = self._attempts(ticket["customer_id"], ticket["event_id"], ticket["endpoint_id"])
            coverage = self._coverage(ticket["customer_id"], ticket["endpoint_id"])
            finding = finding_for(attempts, self.clock())
            evidence = evidence_for(policy, finding, attempts)
            safe_generator = generator if coverage_state(finding, attempts, coverage) not in {"BEHIND_RETRY", "WINDOW_GAP", "NOT_REPORTED"} else None
            draft = validate_draft(safe_generator(ticket, finding, evidence) if safe_generator else
                                   baseline_draft(ticket, finding, evidence, coverage), finding, evidence)
            case_id = str(uuid.uuid4())
            self.db.execute("""INSERT INTO cases(
                id,ticket_id,customer_id,event_id,endpoint_id,subject,description,ticket_hash,
                status,finding,evidence,evidence_hash,draft,policy_version,created_at,reviewed_at,reviewer)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)""",
                            (case_id, ticket["ticket_id"], ticket["customer_id"], ticket["event_id"],
                             ticket["endpoint_id"], ticket["subject"], ticket["description"], digest(ticket),
                             "pending_review", finding, json.dumps(evidence), self._evidence_hash(attempts, coverage), json.dumps(draft),
                             policy["version"], utcnow()))
            self.db.execute("UPDATE cases SET coverage_snapshot=? WHERE id=?", (json.dumps(coverage), case_id))
            self._audit(case_id, "opened", "system", {"finding": finding, "evidence_ids": draft["citations"]})
            return {"case_id": case_id, "created": True}

    def get(self, case_id, customer_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM cases WHERE id=? AND customer_id=?", (case_id, customer_id)).fetchone()
            if row is None:
                raise KeyError("case not found")
            result = dict(row)
            for field in ("evidence", "draft"):
                result[field] = json.loads(result[field])
            result["source_coverage"] = json.loads(row["coverage_snapshot"])
            attempts = self._attempts(row["customer_id"], row["event_id"], row["endpoint_id"])
            current_coverage = self._coverage(row["customer_id"], row["endpoint_id"])
            result["evidence_current"] = self._evidence_hash(attempts, current_coverage) == row["evidence_hash"]
            pinned_attempts = [e["data"] for e in result["evidence"] if e["type"] == "delivery_attempt"]
            result["coverage_state"] = coverage_state(row["finding"], pinned_attempts, result["source_coverage"])
            result["audit"] = [dict(r) for r in self.db.execute(
                "SELECT action,actor,detail,created_at FROM audit WHERE case_id=? ORDER BY id", (case_id,))]
            return result

    def list(self, customer_id):
        with self.lock:
            return [dict(r) for r in self.db.execute("""SELECT id,ticket_id,subject,finding,status,created_at
                FROM cases WHERE customer_id=? ORDER BY created_at DESC,id DESC""", (customer_id,))]

    def refresh(self, case_id, customer_id, policy, generator=None):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM cases WHERE id=? AND customer_id=?", (case_id, customer_id)).fetchone()
            if not row:
                raise KeyError("case not found")
            if row["status"] != "pending_review":
                raise Conflict("only pending cases may refresh")
            ticket = {k: row[k] for k in ("ticket_id", "customer_id", "event_id", "endpoint_id", "subject", "description")}
            attempts = self._attempts(customer_id, row["event_id"], row["endpoint_id"])
            coverage = self._coverage(customer_id, row["endpoint_id"])
            finding = finding_for(attempts, self.clock())
            evidence = evidence_for(policy, finding, attempts)
            safe_generator = generator if coverage_state(finding, attempts, coverage) not in {"BEHIND_RETRY", "WINDOW_GAP", "NOT_REPORTED"} else None
            draft = validate_draft(safe_generator(ticket, finding, evidence) if safe_generator else
                                   baseline_draft(ticket, finding, evidence, coverage), finding, evidence)
            self.db.execute("UPDATE cases SET finding=?,evidence=?,evidence_hash=?,draft=?,policy_version=?,coverage_snapshot=? WHERE id=?",
                            (finding, json.dumps(evidence), self._evidence_hash(attempts, coverage), json.dumps(draft), policy["version"], json.dumps(coverage), case_id))
            self._audit(case_id, "refreshed", "system", {"finding": finding, "evidence_ids": draft["citations"]})
        return self.get(case_id, customer_id)

    def decide(self, case_id, customer_id, reviewer, decision, final_message=None, acknowledge_uncertainty=False):
        if not isinstance(reviewer, str) or not reviewer.strip() or decision not in ("approve", "reject"):
            raise ValueError("reviewer and approve/reject decision required")
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM cases WHERE id=? AND customer_id=?", (case_id, customer_id)).fetchone()
            if not row:
                raise KeyError("case not found")
            if row["status"] != "pending_review":
                raise Conflict("case is no longer pending")
            latest = self._attempts(customer_id, row["event_id"], row["endpoint_id"])
            if self._evidence_hash(latest, self._coverage(customer_id, row["endpoint_id"])) != row["evidence_hash"]:
                raise Conflict("delivery evidence changed; refresh the draft before review")
            draft = json.loads(row["draft"])
            if final_message is not None:
                if not isinstance(final_message, str) or not 1 <= len(final_message.strip()) <= 1500:
                    raise ValueError("final_message must contain 1–1500 characters")
                draft["customer_message"] = final_message.strip()
            ambiguous = row["finding"] in {"NO_RECORD", "MULTIPLE_ACKS", "FAILED_UNRESOLVED", "RETRY_UNOBSERVED"}
            if decision == "approve" and ambiguous and not acknowledge_uncertainty:
                raise ValueError("reviewer must acknowledge uncertain evidence")
            status = "approved" if decision == "approve" else "rejected"
            self.db.execute("UPDATE cases SET status=?,draft=?,reviewed_at=?,reviewer=? WHERE id=?",
                            (status, json.dumps(draft), utcnow(), reviewer, case_id))
            self._audit(case_id, decision, reviewer, {"edited": final_message is not None,
                "acknowledged_uncertainty": bool(acknowledge_uncertainty),
                "message_hash": hashlib.sha256(draft["customer_message"].encode()).hexdigest()})
            if decision == "approve":
                payload = {"handoff_id": case_id, "customer_id": customer_id, "ticket_id": row["ticket_id"],
                           "message": draft["customer_message"], "finding": row["finding"],
                           "policy_version": row["policy_version"]}
                self.db.execute("INSERT INTO outbox(case_id,payload) VALUES(?,?)", (case_id, json.dumps(payload)))
        return self.get(case_id, customer_id)

    def handoff(self, customer_id, send, limit=20):
        """At-least-once delivery. Receiver must deduplicate using handoff_id."""
        results = []
        with self.lock:
            rows = self.db.execute("""SELECT o.* FROM outbox o JOIN cases c ON c.id=o.case_id
                WHERE c.customer_id=? AND o.delivered_at IS NULL ORDER BY c.created_at LIMIT ?""",
                (customer_id, limit)).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                try:
                    send(payload)
                except Exception as exc:
                    with self.db:
                        self.db.execute("UPDATE outbox SET attempts=attempts+1,last_error_type=? WHERE case_id=?",
                                        (type(exc).__name__, row["case_id"]))
                        self._audit(row["case_id"], "handoff_failed", "system", {"type": type(exc).__name__})
                    results.append({"case_id": row["case_id"], "result": "retryable_failure"})
                    continue
                with self.db:
                    self.db.execute("UPDATE outbox SET attempts=attempts+1,delivered_at=?,last_error_type=NULL WHERE case_id=?",
                                    (utcnow(), row["case_id"]))
                    self._audit(row["case_id"], "handed_off", "system", {})
                results.append({"case_id": row["case_id"], "result": "handed_off"})
        return results

    def metrics(self, customer_id):
        with self.lock:
            rows = self.db.execute("SELECT status,finding,created_at,reviewed_at FROM cases WHERE customer_id=?", (customer_id,)).fetchall()
            times = [(datetime.fromisoformat(r["reviewed_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds()
                     for r in rows if r["reviewed_at"]]
            return {"total": len(rows), "status": dict(Counter(r["status"] for r in rows)),
                    "findings": dict(Counter(r["finding"] for r in rows)),
                    "mean_review_seconds": round(sum(times) / len(times), 2) if times else None}
