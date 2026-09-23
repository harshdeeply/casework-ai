# Casework

**An evidence-bound support workbench for webhook delivery escalations.**

**[Open the live interactive demo](https://casework-demo.netlify.app/)** · [Browser app and local setup](web/README.md) · **[Customer case study](docs/customer-case-study.md)**

> “Your billing webhook didn't arrive. Was the event sent? We saw two notifications; did you charge us twice?”

A support engineer cannot safely answer that from a ticket alone. They need the customer's event and endpoint IDs, delivery attempts, HTTP acknowledgments, retry schedule, and the platform's runbook. Casework assembles that evidence, drafts a cautious reply, requires human review, and stages an idempotent handoff to a support desk.

This is an original, runnable **reference deployment using synthetic incidents**. It is not connected to a real customer, ticketing account, or production webhook service. No customer impact or model accuracy is claimed.

## Interactive browser demo

The hosted workbench is a monochrome React + TypeScript app in [`web/`](web/) with source-owned shadcn/ui-style components and a fictional operator profile. It lets a visitor inspect three synthetic escalations, advance an export's source-declared completeness window, add delivery attempts, invalidate stale evidence, refresh findings, edit and review a draft, and hand an approved response to an isolated demo desk. Changes are saved in the visitor's browser storage and can be reset. The hosted UI has **no account session, shared backend, customer telemetry, external desk, or live AI model**. The Python service below is the separate runnable reference backend.

**Try the [live demo](https://casework-demo.netlify.app/):** open T-1042 and see why an export ending at 17:04 cannot confirm a retry scheduled for 17:06. Advance export coverage to 17:10 and refresh the stale case; then add the sample HTTP 200 and refresh again. Review the revised response and send it to the demo support desk. The Reset demo control returns the browser to the original synthetic cases.

```bash
cd web
npm ci
npm test
npm run dev
```

## Three-minute walkthrough

```bash
python3 -m unittest discover -s tests -v
python3 -m casework.evaluate
python3 -m casework.demo
python3 -m casework.server                 # http://127.0.0.1:8080
```

Requires Python 3.12+. No packages, cloud account, or API key are needed. Open the dashboard, enter the local operator key `local-operator`, and load `acme-demo`. The seeded ticket has a timeout followed by HTTP 503. Its recorded retry time has passed, with no later result in the available logs. The workbench flags that evidence gap. To see the full transition, run `python3 -m casework.demo`: a later HTTP 200 appears, approval of the stale draft is blocked, the reviewer refreshes the evidence, and the approved response is handed to a separate demo support desk.

For a sanitized delivery export, run `python3 -m casework.importer examples/attempts.jsonl --coverage examples/coverage.json --dry-run`, then omit `--dry-run` to atomically load attempts and a source-declared completeness window into a chosen `--db` file. CSV is also supported (`examples/attempts.csv`). Conflicting records roll back the whole batch.

## Architecture

```text
delivery attempts ──→ scoped evidence snapshot ──→ code-derived finding
support ticket ──────→ cited draft (optional model) ──→ human review
runbook version ─────↗                            ↘ transactional outbox ──→ support desk
```

1. **Ingest:** Validate attempt identity, timestamp, outcome and status. Replayed IDs are harmless; conflicting duplicates are rejected.
2. **Correlate:** Match attempts on `customer_id + event_id + endpoint_id`. The analysis distinguishes acknowledged, multiple acknowledgments, scheduled retry, overdue unobserved retry, unresolved failure, and absent records.
3. **Ground:** Snapshot the exact attempts, source-declared coverage window, and one versioned runbook entry. If the export ends before a retry, the draft says its outcome is unknown. The code decides the finding; a model cannot change it. Drafts must cite available attempt and runbook IDs.
4. **Review:** A reviewer can edit, approve or reject. New attempt data or a changed completeness window makes an existing draft stale and blocks approval until refresh. Ambiguous findings require explicit uncertainty acknowledgment.
5. **Handoff:** Approval creates an outbox entry. A separate demo desk deduplicates on `handoff_id`. An opt-in HTTPS adapter can send to a real support endpoint that implements the [contract](docs/contract.md). A lost response after successful delivery can cause a retry; the receiver must deduplicate.

An HTTP 2xx proves that the endpoint acknowledged a request. It does **not** prove that the customer's application processed an invoice, sent an email, or charged someone. Multiple 2xx responses do **not** prove duplicate business actions. The system keeps those distinctions visible in both the response and the reviewer rubric.

## API and integration

The loopback demo accepts `Authorization: Bearer local-ingest` for `POST /api/attempts` and `Authorization: Bearer local-operator` for the operator routes. Pass `X-Demo-Customer: acme-demo` to select the demo account. See [the JSON contracts](docs/contract.md) for payloads and endpoints.

| Route | Purpose |
|---|---|
| `POST /api/attempts`, `POST /api/source-coverage` | Ingest an attempt or a scoped completeness window using the ingestion key |
| `POST /api/cases`, `GET /api/cases`, `GET /api/cases/{id}` | Open and inspect scoped escalations |
| `POST /api/cases/{id}/refresh` | Recompute after new evidence arrives |
| `POST /api/cases/{id}/decision` | Approve or reject as a named reviewer |
| `POST /api/handoff` | Deliver approved outbox entries |
| `GET /api/desk`, `GET /api/metrics` | Inspect demo handoffs and local review metrics |

Set `CASEWORK_DB`, `CASEWORK_DEMO_DESK_DB`, `CASEWORK_OPERATOR_KEY`, and `CASEWORK_INGEST_KEY` to change local state and keys. The demo **always binds to loopback**. The shared operator key and caller-selected customer header are demo shortcuts, not production authentication. A real deployment needs verified staff identity and account scope from an identity provider, ingress authentication for telemetry, encryption and retention rules, secret management, rate limits, and a ticketing integration. Do not expose this demo server directly to the Internet.

To use a model for language drafting, set `OPENAI_API_KEY` and `CASEWORK_MODEL_DRAFT=1` before starting the server. The adapter uses a strict structured response, sends the finding and selected evidence but deliberately excludes the ticket description, and sets `store: false`. It still needs human review. The default offline baseline uses templates; the automated fixture suite does **not** score natural-language truthfulness. The optional model path may incur API charges.

`CASEWORK_HANDOFF_URL=https://...` plus `CASEWORK_HANDOFF_TOKEN` enables the generic HTTPS support desk adapter. It rejects redirects and requires an idempotency key. Do not point it at a customer-facing endpoint until the receiving team has validated the contract and approved the workflow.

## Verification and honest limits

The CI gate runs 37 Python tests, 12 browser workflow tests, and 17 synthetic scenario classifications. It covers conflicting identities, account isolation, stale evidence, uncertain review, retries, a lost acknowledgment, concurrent duplicate ingestion, atomic batch import, persistence across restarts, API auth, malformed model output, and the HTTPS adapter. `examples/review_rubric.md` describes the manual answer-quality assessment required before a pilot. The fixture pass rate is **not** an estimate of production precision or model accuracy.

The case store is SQLite and the local server handles requests serially. A production deployment would move to a multi-worker database, enforce tenant scope in the identity layer, ingest real telemetry through an authenticated pipeline, and integrate a real support desk. Before claiming FDE business impact, run a permissioned pilot with support agents, measure correction and handling time against a baseline, and document what failed. See [architecture decisions](docs/architecture.md) and [pilot plan](docs/pilot.md).
