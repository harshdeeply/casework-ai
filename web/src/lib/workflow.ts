import incident from '../../../examples/incident.json'
import policy from '../../../examples/runbook.json'

export type Finding = 'NO_RECORD' | 'ACKNOWLEDGED' | 'MULTIPLE_ACKS' | 'RETRY_SCHEDULED' | 'RETRY_UNOBSERVED' | 'FAILED_UNRESOLVED'
export type Attempt = { attempt_id: string; customer_id: string; event_id: string; endpoint_id: string; sequence: number; sent_at: string; outcome: 'timeout' | 'http_error' | 'acknowledged'; http_status: number | null; next_retry_at: string | null }
export type Ticket = { ticket_id: string; customer_id: string; event_id: string; endpoint_id: string; subject: string; description: string }
export type Coverage = { customer_id: string; endpoint_id: string; source: string; complete_from: string; complete_through: string }
export type Audit = { action: string; actor: string; at: string; detail?: string }
export type Case = Ticket & { id: string; finding: Finding; evidenceIds: string[]; evidenceSignature: string; evidenceSnapshot: Attempt[]; coverageSnapshot: Coverage | null; draft: string; finalMessage?: string; status: 'pending_review' | 'approved' | 'rejected' | 'handed_off'; reviewer?: string; createdAt: string; audit: Audit[] }
export type State = { version: 2; attempts: Attempt[]; coverage: Coverage[]; cases: Case[]; desk: { handoffId: string; ticketId: string; message: string; at: string }[] }

const now = () => new Date().toISOString()
const id = () => crypto.randomUUID()
export const scopedAttempts = (state: State, ticket: Ticket) => state.attempts.filter(a => a.customer_id === ticket.customer_id && a.event_id === ticket.event_id && a.endpoint_id === ticket.endpoint_id).sort((a, b) => a.sequence - b.sequence || a.sent_at.localeCompare(b.sent_at) || a.attempt_id.localeCompare(b.attempt_id))
export const signature = (attempts: Attempt[]) => JSON.stringify(attempts)
export const coverageFor = (state: State, ticket: Ticket) => state.coverage.find(x => x.customer_id === ticket.customer_id && x.endpoint_id === ticket.endpoint_id) || null
export const evidenceSignature = (attempts: Attempt[], coverage: Coverage | null) => JSON.stringify({ attempts, coverage })
export const coverageState = (finding: Finding, attempts: Attempt[], coverage: Coverage | null): 'NOT_APPLICABLE' | 'NOT_REPORTED' | 'BEHIND_RETRY' | 'WINDOW_GAP' | 'THROUGH_RETRY' => {
  if (finding !== 'RETRY_UNOBSERVED') return 'NOT_APPLICABLE'
  if (!coverage) return 'NOT_REPORTED'
  const latest = attempts.at(-1)!
  if (Date.parse(coverage.complete_from) > Date.parse(latest.sent_at)) return 'WINDOW_GAP'
  return Date.parse(coverage.complete_through) >= Date.parse(latest.next_retry_at!) ? 'THROUGH_RETRY' : 'BEHIND_RETRY'
}
export const findingFor = (attempts: Attempt[], asOf = now()): Finding => {
  if (!attempts.length) return 'NO_RECORD'
  const acknowledgments = attempts.filter(a => a.outcome === 'acknowledged').length
  if (acknowledgments > 1) return 'MULTIPLE_ACKS'
  if (acknowledgments) return 'ACKNOWLEDGED'
  const latest = [...attempts].sort((a, b) => b.sequence - a.sequence || b.sent_at.localeCompare(a.sent_at))[0]
  if (latest.next_retry_at) return latest.next_retry_at <= asOf ? 'RETRY_UNOBSERVED' : 'RETRY_SCHEDULED'
  return 'FAILED_UNRESOLVED'
}
export const runbookFor = (finding: Finding) => {
  const entry = policy.runbooks.find(r => r.findings.includes(finding))
  if (!entry) throw Error('No runbook for finding')
  return entry
}
export const draftFor = (ticket: Ticket, finding: Finding, attempts: Attempt[], coverage: Coverage | null = null): string => {
  const latest = attempts.at(-1)
  switch (finding) {
    case 'NO_RECORD': return 'We could not locate a matching delivery attempt in the available logs. We are investigating and will confirm what happened before suggesting a fix.'
    case 'ACKNOWLEDGED': { const a = attempts.find(x => x.outcome === 'acknowledged')!; return `Our logs show your endpoint acknowledged event ${ticket.event_id} with HTTP ${a.http_status} at ${a.sent_at}. This does not confirm how your application processed it.` }
    case 'MULTIPLE_ACKS': return `Our logs show more than one acknowledged delivery attempt for event ${ticket.event_id}. We are investigating the delivery history. Please use the event ID when checking how your application handled the event.`
    case 'RETRY_SCHEDULED': return `The most recent attempt for event ${ticket.event_id} was not acknowledged. Our logs show a retry scheduled for ${latest?.next_retry_at}. We will check the next result.`
    case 'RETRY_UNOBSERVED': {
      const state = coverageState(finding, attempts, coverage)
      if (state === 'BEHIND_RETRY') return `A retry for event ${ticket.event_id} was scheduled for ${latest?.next_retry_at}, but the delivery export currently covers only through ${coverage!.complete_through}. We cannot yet confirm whether that retry occurred.`
      if (state === 'WINDOW_GAP') return `A retry for event ${ticket.event_id} was scheduled for ${latest?.next_retry_at}, but the available export does not cover the earlier attempt. We are checking the missing window before confirming the outcome.`
      return `A retry for event ${ticket.event_id} was scheduled for ${latest?.next_retry_at}, but no later attempt appears in the available logs. We are investigating the gap rather than assuming delivery succeeded or failed.`
    }
    case 'FAILED_UNRESOLVED': return `The available logs show an unacknowledged delivery attempt for event ${ticket.event_id} and no recorded next retry. We are investigating before confirming a resolution.`
  }
}
export const evidenceIds = (finding: Finding, attempts: Attempt[]) => [...attempts.map(a => `attempt:${a.attempt_id}`), `runbook:${runbookFor(finding).id}`]
export const isCurrent = (state: State, c: Case) => evidenceSignature(scopedAttempts(state, c), coverageFor(state,c)) === c.evidenceSignature
export const uncertain = (finding: Finding) => finding === 'NO_RECORD' || finding === 'RETRY_UNOBSERVED' || finding === 'FAILED_UNRESOLVED' || finding === 'MULTIPLE_ACKS'

function assertText(value: string, label: string, max = 128) { if (typeof value !== 'string' || !value.trim() || value.trim().length > max) throw Error(`${label} must be 1–${max} characters`) }
export function validateAttempt(a: Attempt) {
  for (const k of ['attempt_id', 'customer_id', 'event_id', 'endpoint_id'] as const) assertText(a[k], k)
  if (!Number.isInteger(a.sequence) || a.sequence < 1 || a.sequence > 1000) throw Error('Sequence must be 1–1000')
  if (!a.sent_at || !/([zZ]|[+-]\d\d:\d\d)$/.test(a.sent_at) || !Number.isFinite(Date.parse(a.sent_at))) throw Error('Attempt needs a timezone-aware timestamp')
  if (a.next_retry_at && (!/([zZ]|[+-]\d\d:\d\d)$/.test(a.next_retry_at) || !Number.isFinite(Date.parse(a.next_retry_at)) || Date.parse(a.next_retry_at) <= Date.parse(a.sent_at))) throw Error('Retry must follow attempt')
  if (a.outcome === 'acknowledged' && (!(a.http_status && a.http_status >= 200 && a.http_status < 300) || a.next_retry_at)) throw Error('Acknowledgment requires 2xx and no retry')
  if (a.outcome === 'http_error' && (!(a.http_status && a.http_status >= 400 && a.http_status <= 599))) throw Error('HTTP error requires 4xx or 5xx')
  if (a.outcome === 'timeout' && a.http_status !== null) throw Error('Timeout has no HTTP status')
  if (!['acknowledged', 'http_error', 'timeout'].includes(a.outcome)) throw Error('Unknown outcome')
}
export function addAttempt(state: State, attempt: Attempt): State {
  validateAttempt(attempt)
  const prior = state.attempts.find(a => a.attempt_id === attempt.attempt_id)
  if (prior) { if (JSON.stringify(prior) !== JSON.stringify(attempt)) throw Error('Attempt ID reused with different data'); return state }
  return { ...state, attempts: [...state.attempts, attempt] }
}
export function setCoverage(state: State, coverage: Coverage): State {
  for (const k of ['customer_id','endpoint_id','source'] as const) assertText(coverage[k], k)
  for (const k of ['complete_from','complete_through'] as const) if (!/([zZ]|[+-]\d\d:\d\d)$/.test(coverage[k]) || !Number.isFinite(Date.parse(coverage[k]))) throw Error('Coverage needs timezone-aware timestamps')
  if (Date.parse(coverage.complete_from) > Date.parse(coverage.complete_through) || Date.parse(coverage.complete_through) > Date.now()) throw Error('Invalid coverage window')
  const prior = state.coverage.find(x => x.customer_id === coverage.customer_id && x.endpoint_id === coverage.endpoint_id)
  if (prior && JSON.stringify(prior) === JSON.stringify(coverage)) return state
  return { ...state, coverage: [...state.coverage.filter(x => x.customer_id !== coverage.customer_id || x.endpoint_id !== coverage.endpoint_id), coverage] }
}
export function openCase(state: State, ticket: Ticket): State {
  for (const k of ['ticket_id', 'customer_id', 'event_id', 'endpoint_id', 'subject', 'description'] as const) assertText(ticket[k], k, k === 'description' ? 2000 : k === 'subject' ? 200 : 128)
  const prior = state.cases.find(c => c.customer_id === ticket.customer_id && c.ticket_id === ticket.ticket_id)
  if (prior) { if (['ticket_id','customer_id','event_id','endpoint_id','subject','description'].some(k => prior[k as keyof Ticket] !== ticket[k as keyof Ticket])) throw Error('Ticket ID reused with different data'); return state }
  const attempts = scopedAttempts(state, ticket), coverage = coverageFor(state, ticket), finding = findingFor(attempts)
  return { ...state, cases: [{ ...ticket, id: id(), finding, evidenceIds: evidenceIds(finding, attempts), evidenceSignature: evidenceSignature(attempts, coverage), evidenceSnapshot: attempts, coverageSnapshot: coverage, draft: draftFor(ticket, finding, attempts, coverage), status: 'pending_review', createdAt: now(), audit: [{ action: 'opened', actor: 'system', at: now(), detail: finding }] }, ...state.cases] }
}
export function refreshCase(state: State, caseId: string): State {
  const c = state.cases.find(x => x.id === caseId)
  if (!c) throw Error('Case not found')
  if (c.status !== 'pending_review') throw Error('Only pending cases can be refreshed')
  const attempts = scopedAttempts(state, c), coverage = coverageFor(state, c), finding = findingFor(attempts)
  return { ...state, cases: state.cases.map(x => x.id === caseId ? { ...x, finding, evidenceIds: evidenceIds(finding, attempts), evidenceSignature: evidenceSignature(attempts, coverage), evidenceSnapshot: attempts, coverageSnapshot: coverage, draft: draftFor(c, finding, attempts, coverage), audit: [...x.audit, { action: 'refreshed', actor: 'system', at: now(), detail: finding }] } : x) }
}
export function decideCase(state: State, caseId: string, decision: 'approve' | 'reject', reviewer: string, message: string, acknowledgeUncertainty: boolean): State {
  const c = state.cases.find(x => x.id === caseId)
  if (!c) throw Error('Case not found')
  if (c.status !== 'pending_review') throw Error('This case has already been reviewed')
  if (!isCurrent(state, c)) throw Error('New evidence arrived. Refresh the case before review.')
  assertText(reviewer, 'Reviewer')
  if (decision === 'approve') {
    assertText(message, 'Final message', 1500)
    if (uncertain(c.finding) && !acknowledgeUncertainty) throw Error('Acknowledge the uncertainty before approving')
  }
  return { ...state, cases: state.cases.map(x => x.id === caseId ? { ...x, status: decision === 'approve' ? 'approved' as const : 'rejected' as const, reviewer, finalMessage: decision === 'approve' ? message.trim() : undefined, audit: [...x.audit, { action: decision === 'approve' ? 'approved' : 'rejected', actor: reviewer, at: now() }] } : x) }
}
export function handoff(state: State, caseId: string): State {
  const c = state.cases.find(x => x.id === caseId)
  if (!c) throw Error('Case not found')
  if (c.status === 'handed_off') return state
  if (c.status !== 'approved' || !c.finalMessage) throw Error('Approve the case before handoff')
  return { ...state, cases: state.cases.map(x => x.id === caseId ? { ...x, status: 'handed_off' as const, audit: [...x.audit, { action: 'handed_off', actor: 'demo-desk', at: now() }] } : x), desk: [...state.desk, { handoffId: c.id, ticketId: c.ticket_id, message: c.finalMessage, at: now() }] }
}
export function seedState(): State {
  const ticket = incident.ticket as Ticket
  let state: State = { version: 2, attempts: incident.attempts as Attempt[], coverage: [{ customer_id: 'acme-demo', endpoint_id: 'endpoint-billing', source: 'Synthetic delivery export', complete_from: '2026-09-22T16:55:00Z', complete_through: '2026-09-22T17:04:00Z' }], cases: [], desk: [] }
  state = openCase(state, ticket)
  state = addAttempt(state, { attempt_id: 'attempt-201', customer_id: 'acme-demo', event_id: 'evt-payment-772', endpoint_id: 'endpoint-payments', sequence: 1, sent_at: '2026-09-22T15:24:00Z', outcome: 'acknowledged', http_status: 200, next_retry_at: null })
  state = addAttempt(state, { attempt_id: 'attempt-202', customer_id: 'acme-demo', event_id: 'evt-payment-772', endpoint_id: 'endpoint-payments', sequence: 2, sent_at: '2026-09-22T15:26:00Z', outcome: 'acknowledged', http_status: 200, next_retry_at: null })
  state = openCase(state, { ticket_id: 'T-772', customer_id: 'acme-demo', event_id: 'evt-payment-772', endpoint_id: 'endpoint-payments', subject: 'Duplicate payment notifications', description: 'We received two notifications for the same payment. Were we charged twice?' })
  state = openCase(state, { ticket_id: 'T-389', customer_id: 'acme-demo', event_id: 'evt-onboarding-389', endpoint_id: 'endpoint-events', subject: 'Onboarding event missing', description: 'Our downstream workflow is missing the onboarding event. Can you trace the delivery?' })
  return state
}
export const nextAttempt = incident.next_attempt as Attempt
