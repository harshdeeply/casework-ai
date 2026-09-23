# Casework · evidence-bound operations queue

A runnable, synthetic customer deployment for rental operations. An incoming question is matched to a versioned policy set, turned into an evidence-linked draft, reviewed by a person, and staged in an outbox for delivery. The sample data is fictional; this does **not** represent a deployed Propsynk feature or a legal advice system.

## See it work

```bash
python3 -m casework.server                  # http://127.0.0.1:8080
python3 -m casework.evaluate                # offline regression set
python3 -m unittest discover -s tests -v   # workflow and failure tests
```

No API keys, database server, or dependencies are required for the offline demo. Try “A tenant reported a leaking sink. What should I record?” and then approve the case. Try an unrelated question: the assistant abstains until a reviewer supplies an answer.

To exercise an actual model draft, set `OPENAI_API_KEY` and run `CASEWORK_MODEL_DRAFT=1 python3 -m casework.server`. Optionally set `OPENAI_MODEL` to a model that supports structured outputs. The adapter sends the question and selected synthetic policy excerpts to the Responses API with a strict JSON schema and `store: false`. Model output still passes local citation validation and human approval. This path incurs API charges and is not exercised by the offline tests.

## Customer problem and deployment design

Operations teams answer repetitive questions from a changing policy corpus. A plausible answer without supporting policy can cause harm. This deployment separates **retrieval**, **drafting**, **review**, and **delivery**. Each case has a tenant boundary, policy IDs, reviewer identity, decision, timestamps, a SHA-256 fingerprint of the reviewed answer, and a transactional outbox. The delivery adapter uses `case_id` as an idempotency key; external integrations should deduplicate on that key because process crashes can cause a second send after the first send succeeds.

```text
Question → policy match → validated draft → pending review → approve/reject → outbox → delivery adapter
                                              ↘ audit events ↗
```

Endpoints: `POST /api/cases`, `GET /api/cases`, `GET /api/cases/{id}`, `POST /api/cases/{id}/decision`, `POST /api/deliver`. Use `X-Demo-Tenant` to inspect synthetic tenancy isolation. SQLite persists to `casework.sqlite3` by default; set `CASEWORK_DB` to change it.

## Evaluation and boundaries

`examples/eval.json` is a small transparent set of relevant and irrelevant questions. `python3 -m casework.evaluate` reports each citation and fails if the expected result differs. The default drafting engine is deliberately deterministic and extractive; the optional model adapter is a separate path. `validate_draft` checks citation IDs and abstention shape, **not factual entailment**: a cited answer can still be wrong. A real deployment also needs verified authentication, role authorization, source versioning, PII redaction, a real delivery adapter, and a larger human-reviewed evaluation set. The local HTTP UI is a demo and binds to loopback only.

## FDE discussion

Show the customer workflow first, then a malicious or irrelevant input, then the audit and approval steps. Discuss why the outbox cannot promise exactly-once delivery and how to measure reviewer acceptance rate, citation correctness, time saved, and escalation rate with an actual customer pilot. Do not present synthetic test results as customer outcomes.
