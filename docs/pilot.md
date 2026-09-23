# From reference deployment to a real support pilot

This plan is intentionally prospective. It is not evidence that a pilot has occurred.

1. **Discovery:** Interview support leads and 3–5 agents. Collect anonymized examples of missing, delayed, duplicate, and wrong-endpoint reports. Agree on which source logs are authoritative, their retention, and when to escalate.
2. **Contract:** Map the source platform's actual event/attempt IDs and retry semantics to the ingestion contract. Verify a random sample by hand. Add authenticated transport, consent and redaction rules, and tenant scope from server-verified claims.
3. **Shadow mode:** Let agents compare Casework drafts with existing investigations; do not send to customers. Label at least 100 tickets across findings and score each draft with `examples/review_rubric.md`. Record unsupported factual claims separately from style edits.
4. **Guarded pilot:** Permit a small group of trained agents to review and stage private ticket notes. Set acceptance criteria with the support lead before rollout. Track draft acceptance, edit rate, time to approved note, stale-draft blocks, escalation accuracy, and customer follow-ups.
5. **Scale decision:** Review failures, prompt and runbook changes, tenant isolation tests, outage playbook, cost per case, and support-team feedback. Only then consider production writeback or automatic customer messaging.

The most important negative result to publish would be a case where a 2xx reply was incorrectly interpreted as successful downstream processing. That failure is exactly why this system keeps the finding separate from generated prose and forces review.
