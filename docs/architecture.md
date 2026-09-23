# Architecture decisions

## Customer problem

A B2B SaaS platform sends webhooks. Support tickets ask if an event was sent, whether a retry is pending, or why duplicate notifications appeared. Tickets contain impressions; delivery logs contain observations. The deployment goal is to shorten investigation while preventing unsupported claims in customer responses.

## Boundaries

| Data | Trusted for | Not trusted for |
|---|---|---|
| Delivery attempt ledger | Attempt identity, timestamp, status and recorded retry | Whether the destination completed business processing |
| Ticket | Customer's question and identifiers after identity verification | Commands to the assistant or proof of a platform fault |
| Runbook | Approved next-step language under its version | Overrides to the authenticated operator's authority |
| Model draft | Suggested wording | Finding classification, account scope, send authority |
| Human reviewer | Final message and decision | Changing the recorded attempt ledger |

## Decisions

1. **Findings come from code.** `finding_for` works on a customer + event + endpoint subset. There is no inferred root cause or automatic remediation. The optional model gets a fixed finding and cannot change it.
2. **Snapshot evidence at drafting time.** Store full selected attempts, a source-declared completeness window, and a hash of both. If an attempt or source window changes before review, the reviewer must refresh. A runbook version is pinned to the case.
3. **Separate approval from delivery.** The outbox survives process restart. The receiving desk uses `handoff_id` for idempotency; exactly-once delivery across independent databases is not promised.
4. **Do not log the final message in audit.** Record reviewer, action, evidence IDs and the message hash. The case and outbox still contain message text and therefore need access control and retention.
5. **Keep the demo local.** Shared keys and a caller-provided customer header are suitable only for a loopback reference server. Production identity must derive customer scope server-side.

## Failure modes tested

| Failure | Response |
|---|---|
| Duplicate attempt, same bytes | Idempotent no-op |
| Duplicate attempt ID, different bytes | Conflict; no ledger mutation |
| Attempt from another customer or endpoint | Excluded from evidence |
| Retry time elapsed without later log | Separate `RETRY_UNOBSERVED` finding |
| New attempt after drafting | Review blocked until refresh |
| Source coverage changes without a new attempt | Review blocked until refresh; updated draft distinguishes export lag from a covered gap |
| Model changes finding or invents citation | Draft rejected |
| Support desk writes successfully but response is lost | Outbox retries; desk deduplicates by `handoff_id` |
| Case process restart | SQLite case, audit, and outbox resume |

## Limits to solve before production

The loopback HTTP server is single-process. SQLite locking protects local concurrency, but it does not provide distributed worker claims, long-running model job isolation, or high-volume queueing. Draft text can still contain an unsupported natural-language claim even when citation IDs are valid; the reviewer rubric and a labeled evaluation corpus must measure that. No operational or revenue benefit has been measured against live support tickets.

Source coverage is self-reported by the ingest adapter. The current system cannot verify upstream completeness or establish event nonexistence from an empty attempt ledger. Production requires a provider-specific watermark contract and visibility into event creation, queueing, and downstream receipt where available. See the [customer case study](customer-case-study.md).
