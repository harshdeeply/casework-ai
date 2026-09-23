import { describe, expect, it } from 'vitest'
import { addAttempt, decideCase, findingFor, handoff, isCurrent, nextAttempt, openCase, refreshCase, scopedAttempts, seedState, type Attempt } from './workflow'

describe('public sandbox workflow', () => {
  it('starts with an overdue retry that has no observed result', () => {
    const state = seedState(), c = state.cases.find(x => x.ticket_id === 'T-1042')!
    expect(c.finding).toBe('RETRY_UNOBSERVED')
    expect(c.evidenceIds).toContain('runbook:RB-06')
    expect(c.evidenceSnapshot).toHaveLength(2)
  })
  it('blocks stale review, then refreshes the snapshot and citation', () => {
    const state = addAttempt(seedState(), nextAttempt), c = state.cases.find(x => x.ticket_id === 'T-1042')!
    expect(isCurrent(state,c)).toBe(false)
    expect(() => decideCase(state,c.id,'approve','Reviewer',c.draft,true)).toThrow(/Refresh/)
    const updated = refreshCase(state,c.id), fresh = updated.cases.find(x => x.id === c.id)!
    expect(fresh.finding).toBe('ACKNOWLEDGED')
    expect(fresh.evidenceIds).toContain('attempt:attempt-103')
    expect(fresh.evidenceSnapshot).toHaveLength(3)
    expect(isCurrent(updated,fresh)).toBe(true)
  })
  it('requires acknowledgment for uncertain findings', () => {
    const state = seedState(), c = state.cases.find(x => x.ticket_id === 'T-1042')!
    expect(() => decideCase(state,c.id,'approve','Reviewer',c.draft,false)).toThrow(/uncertainty/)
  })
  it('requires approval before handoff and deduplicates delivery', () => {
    const state = seedState(), c = state.cases.find(x => x.ticket_id === 'T-1042')!
    expect(() => handoff(state,c.id)).toThrow(/Approve/)
    const approved = decideCase(state,c.id,'approve','Reviewer',c.draft,true)
    const delivered = handoff(approved,c.id)
    expect(delivered.desk).toHaveLength(1)
    expect(delivered.desk[0].handoffId).toBe(c.id)
    expect(handoff(delivered,c.id)).toBe(delivered)
  })
  it('rejects without creating a support desk message', () => {
    const state = seedState(), c = state.cases[0]
    const rejected = decideCase(state,c.id,'reject','Reviewer','',false)
    expect(rejected.desk).toHaveLength(0)
    expect(() => handoff(rejected,c.id)).toThrow(/Approve/)
  })
  it('isolates attempts by customer, event, and endpoint', () => {
    const state = seedState(), ticket = state.cases.find(c=>c.ticket_id==='T-1042')!
    const other: Attempt = { ...nextAttempt, attempt_id:'other-customer', customer_id:'other' }
    const altered = addAttempt(state,other)
    expect(scopedAttempts(altered,ticket)).toHaveLength(2)
    expect(isCurrent(altered,ticket)).toBe(true)
    expect(findingFor(scopedAttempts(altered,ticket))).toBe('RETRY_UNOBSERVED')
  })
  it('treats repeated attempt IDs as idempotent only when payload matches', () => {
    const state = seedState()
    expect(addAttempt(state,state.attempts[0])).toBe(state)
    expect(() => addAttempt(state,{...state.attempts[0],sequence:9})).toThrow(/reused/)
  })
  it('validates attempt outcomes and timezone-aware timestamps', () => {
    const state = seedState()
    expect(() => addAttempt(state,{...nextAttempt,attempt_id:'bad',http_status:503})).toThrow(/2xx/)
    expect(() => addAttempt(state,{...nextAttempt,attempt_id:'bad',sent_at:'2026-09-22T17:06:00'})).toThrow(/timezone/)
  })
  it('preserves ticket idempotency and rejects conflicting reuse', () => {
    const state = seedState(), c = state.cases[0]
    const ticket = { ticket_id:c.ticket_id, customer_id:c.customer_id, event_id:c.event_id, endpoint_id:c.endpoint_id, subject:c.subject, description:c.description }
    expect(openCase(state,ticket)).toBe(state)
    expect(() => openCase(state,{...ticket,subject:'different'})).toThrow(/reused/)
  })
  it('never infers a downstream charge from two HTTP acknowledgments', () => {
    const c = seedState().cases.find(x => x.ticket_id === 'T-772')!
    expect(c.finding).toBe('MULTIPLE_ACKS')
    expect(c.draft).not.toMatch(/charged twice|duplicate charge/i)
    expect(c.draft).toMatch(/delivery history/)
  })
})
