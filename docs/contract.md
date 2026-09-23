# Integration contract (reference)

This is a portable contract for a future webhook platform and support desk. It does not claim that any vendor implements these exact routes.

## Attempt ingestion

`POST /api/attempts`, authorized with the ingestion key, maximum JSON body 16 KiB:

```json
{
  "attempt_id": "attempt-101",
  "customer_id": "acme-demo",
  "event_id": "evt-invoice-1042",
  "endpoint_id": "endpoint-billing",
  "sequence": 1,
  "sent_at": "2026-09-22T17:00:00Z",
  "outcome": "http_error",
  "http_status": 503,
  "next_retry_at": "2026-09-22T17:02:00Z"
}
```

`outcome` is `acknowledged` with a 2xx code and no retry, `http_error` with 4xx/5xx, or `timeout` with null status. A retry time is an observation from the source scheduler, not a promise of success. Event ID alone is insufficient for account isolation: correlation also requires customer and endpoint IDs. A repeated `attempt_id` with a changed payload returns conflict.

## Source completeness contract

`POST /api/source-coverage` uses the ingestion key. It records a **source-declared** export window for one customer and endpoint:

```json
{"customer_id":"acme-demo","endpoint_id":"endpoint-billing","source":"Synthetic delivery export","complete_from":"2026-09-22T16:55:00Z","complete_through":"2026-09-22T17:04:00Z"}
```

Times require timezones; the window cannot be reversed or extend into the future. The source's assertion is not independent proof of completeness. A production adapter must define what complete means and account for delayed ingestion, backfill, and retention. `python3 -m casework.importer examples/attempts.jsonl --coverage examples/coverage.json --dry-run` validates an export and JSON array of windows; without `--dry-run` it stores both atomically. Changing a window invalidates pending review even when the attempt list is identical.

## Support case

`POST /api/cases`, authorized with the operator key and `X-Demo-Customer` header:

```json
{
  "ticket_id": "T-1042",
  "customer_id": "acme-demo",
  "event_id": "evt-invoice-1042",
  "endpoint_id": "endpoint-billing",
  "subject": "Invoice event did not arrive",
  "description": "Our finance workflow has not updated."
}
```

The local operator key is global to the demo; a real identity proxy must establish customer scope independently of the request header. `GET /api/cases/{id}` returns the finding, pinned runbook version, attempt evidence, `source_coverage`, `coverage_state`, draft, staleness flag, and audit trail. `POST /api/cases/{id}/refresh` takes `{}`. `POST /api/cases/{id}/decision` takes `{"reviewer":"support-1","decision":"approve","final_message":"...","acknowledge_uncertainty":true}`. No case sends a message on its own.

## Handoff to a support desk

The opt-in HTTPS adapter sends a POST with `Authorization: Bearer <token>`, `Content-Type: application/json`, and `Idempotency-Key: <handoff_id>`:

```json
{
  "handoff_id": "unique-case-uuid",
  "customer_id": "acme-demo",
  "ticket_id": "T-1042",
  "message": "Reviewed customer-facing message",
  "finding": "ACKNOWLEDGED",
  "policy_version": "2026-09-example-v2"
}
```

The receiver must authenticate this service, check its own ticket/customer ownership, insert by `handoff_id` with a unique constraint, and return 2xx for a repeated identical request. Reject collisions with changed content. The sender treats every non-2xx and transport error as retryable and does not follow redirects. A crash after remote success but before local acknowledgment may resend the same handoff. The receiver should stage a **draft/private note** until its own operator confirms customer delivery; never assume an arbitrary third-party endpoint posts privately.
