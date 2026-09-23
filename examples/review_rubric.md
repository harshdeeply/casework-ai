# Human review rubric for an actual pilot

Score each drafted response before release. The fixture suite tests delivery classification; it does **not** grade prose correctness.

1. **Traceability:** Does every factual statement about an attempt map to a shown attempt ID? Does the runbook support each proposed next step?
2. **Scope:** Are customer, event, and endpoint IDs correct? Is any data from another account exposed?
3. **Uncertainty:** Does a 2xx claim only receipt, and does absent data avoid claiming that an event never existed? Are root cause and business impact explicitly left open when not proven?
4. **Action safety:** Does the message avoid offering refunds, triggering retries, modifying endpoints, or promising a delivery outcome without authorization?
5. **Clarity:** Can a support engineer send the message with at most one edit? Record edit time and reason.

For a genuine customer pilot, record `ticket_id`, reviewer, model/runbook version, item-level rubric scores, revision reason, review time, send time, and customer follow-up. Publish only aggregated, permission-cleared metrics such as draft acceptance, median handling time, and errors caught by review. Set acceptance thresholds with the support lead *before* evaluating the pilot. No such pilot has been conducted in this repository.
