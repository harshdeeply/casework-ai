# Case study: a billing webhook escalation

## Customer situation

This is a synthetic, reproducible scenario. A B2B SaaS platform sends billing webhooks to customers. One customer reports that its finance workflow did not update and asks whether invoice event `evt-invoice-1042` arrived. The support engineer has a ticket, two delivery attempts, and a separately exported completeness window.

**The decision to make:** What can support tell the customer now, and who should investigate next? A timeout, an HTTP 503, and an elapsed retry time do not by themselves prove that a retry never ran. Even an HTTP 200 cannot prove the customer's finance application processed the invoice.

## Before Casework

A support engineer searches a delivery console, checks the customer and endpoint IDs, inspects the retry scheduler, asks engineering whether the log export is delayed, checks an internal runbook, and manually drafts an answer in a ticketing tool. This is a workflow hypothesis; no customer interviews or handling-time measurements have been conducted for this repository.

The dangerous shortcut is to treat an absent log row as a negative fact. If a source export is only complete through 17:04, it cannot establish what happened to a retry scheduled for 17:06.

## Investigation replay

| Observed record | Meaning | Limit |
|---|---|---|
| Attempt 101, 17:00 UTC: timeout | No HTTP acknowledgment recorded for this attempt | No conclusion about a later retry |
| Attempt 102, 17:02 UTC: HTTP 503, retry planned at 17:06 | Endpoint returned an error; scheduler recorded a next retry time | The schedule is not proof the retry ran |
| Export window, 16:55–17:04 UTC | Source declares this time span complete for the customer and endpoint | The export ends before the scheduled retry |

Casework correlates on **customer + event + endpoint**, pins the two attempts and the runbook version, and classifies the available ledger as `RETRY_UNOBSERVED`. It separately marks the source coverage `BEHIND_RETRY`. The initial draft therefore says it **cannot yet confirm whether the 17:06 retry occurred**.

There are two independent changes worth testing:

1. **Coverage advances without a new attempt.** The source declares the export complete through 17:10. Casework invalidates the old snapshot even though the attempt list is unchanged. After refresh, support can say no later attempt appears in a source window covering the retry time. It still cannot identify why the attempt is absent.
2. **Attempt 103 arrives.** An HTTP 200 at 17:06 invalidates the saved answer again. After refresh, Casework reports endpoint acknowledgment and explicitly leaves downstream invoice processing unverified.

The reviewer may edit the message, acknowledges uncertainty for ambiguous findings, approves or rejects, and hands an approved response to an isolated demo desk. The Python backend stores an outbox entry and retries delivery with a stable `handoff_id`; the receiving desk deduplicates it. No customer is contacted by this project.

## What is implemented

- The Python reference service validates and stores attempts and source-declared completeness windows in SQLite. `POST /api/source-coverage` uses the separate ingestion key. A sanitized JSONL/CSV export can be imported with a JSON coverage manifest in one transaction.
- The optional model draft is bypassed for overdue retries without complete source coverage. A cautious code-generated response is used until a reported window covers the retry.
- Each case pins the attempts, source window, runbook entry, and finding at drafting time. Changes in either attempts or coverage block review until refresh. Coverage is scoped by customer and endpoint.
- The hosted React demo replays the same case with browser-local state and a monochrome operator UI. Its sample export can be advanced independently of adding an HTTP 200.
- Automated tests exercise a coverage-only change, tenant isolation, invalid windows, transactional import rollback, stale review, and the existing handoff failure cases.

## Boundaries and unknowns

The completeness window is **a claim made by the source export**. Casework cannot independently prove the source's instrumentation is correct. A production adapter would need a source-specific definition of “complete,” an ingestion watermark, retention bounds, source identity, and controls for backfills and late data. For `NO_RECORD`, the current ticket has no event-generation timestamp or bounded search window, so absence remains qualified as “in the available logs.”

The live UI is a static browser simulation, separate from the Python API. The Python HTTP server binds to loopback and uses demo credentials, not production authentication. The optional model path is off by default. Citation IDs constrain draft structure; they do not prove every natural-language sentence is truthful. There is no real provider connector, ticketing integration, external customer, or measured business outcome.

## Forward-deployed pilot proposal

**Discovery:** Ask a support lead and 3–5 engineers for recent missing/late/duplicate webhook tickets. Map authoritative event IDs, delivery attempts, export lag, retention, customer account scope, runbooks, and the existing ticketing workflow.

**Read-only integration:** Implement one source-specific adapter for a permissioned delivery ledger, with a documented definition of its completeness window. Keep the support desk as system of record; attach an investigation card or private note, not an automatic public response.

**Shadow evaluation:** Replay at least 100 permission-cleared historical tickets using only records available at the relevant point in time. Have reviewers score account/event/endpoint matching, unsupported factual claims, uncertainty handling, stale-evidence detection, edit effort, and time to a reviewed answer against the team's current workflow. Define acceptance thresholds before the pilot. The repository's 17 synthetic scenarios are regression fixtures, not a field accuracy estimate.

**Decision:** If the tool fails to outperform existing provider consoles plus support tools, narrow or stop the product hypothesis. If it consistently catches coverage gaps or answer overclaims while reducing review effort, consider guarded ticket writeback with verified identity, tenant scope, retention, and audit controls.
