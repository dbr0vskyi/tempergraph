// @ts-nocheck: run by bun, whose types the plugin validator does not load.
// Pure model rules against engine fixtures (run `bun test ./tests/*.spec.ts` from the plugin folder;
// `claude plugin test .` runs the session tests in monitor.test.tsx).
// The fixtures are written by tests/fixtures/make_fixtures.py from a scripted-executor engine run.

import { describe, expect, test } from 'bun:test'

import type { DetailDoc, RunRecord, StatusDoc, StatusRow } from '../hooks/lib/engine'
import { isReadable } from '../hooks/lib/engine'
import {
  alertsFrom, attemptRows, bandRow, healthAlerts, levelText, listRow, money, narrator, runLabel, runList, sessionNow,
  statusLine, summarise, touchStrip, unitRowText, unitRows,
} from '../hooks/lib/model'
import type { RunSummary } from '../hooks/lib/model'
import {
  detailArgv, fleetArgv, isReadOnly, keepTail, nextRead, parseChunk, READ_ONLY_VERBS, statusArgv, statusEvery, WRITING_VERBS,
} from '../hooks/lib/sources'

const dir = new URL('./fixtures/', import.meta.url).pathname
const status = (await Bun.file(dir + 'status.json').json()) as StatusDoc
const paused = (await Bun.file(dir + 'detail-paused.json').json()) as DetailDoc
const logText = await Bun.file(dir + 'run-paused.jsonl').text()
const NOW = Date.parse(paused.generated_at ?? '2026-11-20T00:00:00Z')

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

/** The paused fixture turned into a live one: review's judge session open, a Grep running for 12 s. */
function running(): DetailDoc {
  const d = clone(paused)
  d.run.alive = true
  d.run.state = 'running'
  d.run.pending_gates = []
  d.pause = null
  const review = d.units.find(u => u.name === 'review')!
  review.state = 'running'
  const att = review.visits[review.visits.length - 1]!.attempts[0]!
  att.gate = null
  att.check = { result: 'PASS' }
  att.judge = { sessions: [{ session_key: 'review.2.judge', kind: 'judge', executor: 'claude', ended_at: null,
    live: { open_tool: { name: 'Grep', capability: 'search', input_summary: 'TODO', elapsed: 12 }, recent: [],
      last_event_age_s: 9 } }] }
  return d
}

function summary(over: Partial<RunSummary>): RunSummary {
  return { threadId: 'demo/T-9', workflow: 'demo', label: 'x', mark: '▶', state: 'running', alive: true, unit: 'code',
    node: 'J', attempt: 1, passed: 1, planned: 3, elapsed: 60, waiting: null, cost: '$1.00 est', question: null,
    resume: null, ...over }
}

describe('engine documents', () => {
  test('fixtures are readable and a newer schema is not', () => {
    expect(isReadable(status, 'status')).toBe(true)
    expect(isReadable(paused, 'detail')).toBe(true)
    expect(isReadable({ schema_version: 2 }, 'detail')).toBe(false)
  })
})

describe('labels and money (MBA §2.1, contract M4)', () => {
  test('alias, then label, then repo/branch and a hash', () => {
    const row = status.threads[0]!
    expect(runLabel({ ...row, alias: 'auth-fix' })).toBe('auth-fix')
    expect(runLabel({ ...row, label: 'docs' })).toBe('docs')
    expect(runLabel(row, 'tempergraph')).toMatch(/^tempergraph\/tg\/demo\/T-1·[0-9a-f]{4}$/)
  })
  test('estimates and gaps are never shown as reported', () => {
    expect(money({ reported: 0.1, completeness: 'complete' })).toBe('$0.10')
    expect(money({ estimated: 3.1, completeness: 'estimated' })).toBe('$3.10 est') // MBA-B3
    expect(money({ reported: 1, estimated: 2, figure: 1.5, completeness: 'incomplete' })).toBe('$1.50 est, incomplete')
    expect(money({})).toBe('unmeasured')
    expect(money(undefined)).toBe('unmeasured')
  })
})

describe('band and status line (MBA §2.2, §2.3)', () => {
  test('a paused fixture run reads waiting, with the unit and question', () => {
    const s = summarise(status.threads[0]!, paused, NOW)
    expect(s.mark).toBe('⏸')
    expect(s.unit).toBe('review')
    expect(s.resume).toBe('tempergraph resume demo T-1 --decision <proceed|retry|back:draft|stop>')
    expect(bandRow([s], 120)).toMatch(/^tg ⏸ .* waits \d+s$/)
    expect(statusLine([s])).toBe('tg 1⏸')
  })
  test('one running run names unit, place, node and attempt', () => {
    const d = running()
    const s = summarise(d.run as StatusRow, d, NOW)
    expect(s.node).toBe('J')
    expect(bandRow([{ ...s, label: 'auth-fix' }], 200)).toMatch(/^tg ▶ auth-fix · review 2\/2 · judge · attempt 2 · /)
  })
  test('waiting first, counts when crowded (MBA-B1)', () => {
    const runs = [summary({ label: 'a' }), summary({ label: 'b', threadId: 'd/b' }), summary({ label: 'c', threadId: 'd/c' }),
      summary({ label: 'docs-sync', threadId: 'd/w', mark: '⏸', state: 'paused', waiting: 720, cost: '$5.10 est' })]
    expect(bandRow(runs, 60)).toBe('tg 4 ▶ 3 ⏸ 1 · $8.10 est')
    expect(bandRow(runs, 120)).toBe('tg 4 ▶ 3 ⏸ 1 · $8.10 est  ⏸ docs-sync waits 12m')
    const two = bandRow(runs.slice(2), 120)!
    expect(two.indexOf('⏸ docs-sync')).toBeLessThan(two.indexOf('▶ c'))
    expect(statusLine(runs)).toBe('tg 3▶ 1⏸')
  })
  test('no live run: a row only for a run that ended in the last 10 minutes', () => {
    const done = summary({ alive: false, mark: '✓', state: 'finished', label: 'auth-fix', cost: '$3.10 est' })
    expect(bandRow([done], 80, { 'demo/T-9': 120 })).toBe('tg ✓ auth-fix finished · $3.10 est')
    expect(bandRow([done], 80, { 'demo/T-9': 3600 })).toBeNull()
    expect(statusLine([done])).toBeUndefined()
  })
})

describe('alerts (MBA §2.4)', () => {
  const recs = parseChunk(logText, 0).records
  test('a pause raises one toast and one notification, once per seq (MBA-B2)', () => {
    const first = alertsFrom('demo/T-1', 'notes', recs, 0)
    const pause = first.filter(a => a.kind === 'pause')
    expect(pause).toHaveLength(1)
    expect(pause[0]!.notify).toBe(true)
    expect(pause[0]!.body.startsWith('review waits: ')).toBe(true)
    const last = Math.max(...first.map(a => a.seq))
    expect(alertsFrom('demo/T-1', 'notes', recs, last)).toEqual([])
  })
  test('exit 4 or 5 notifies; exit 0 only when asked', () => {
    const exit = (code: number): RunRecord => ({ seq: 9, ts: 't', kind: 'run_exit', exit_code: code, reason: 'infra' })
    expect(alertsFrom('t/1', 'x', [exit(5)], 0)[0]!.notify).toBe(true)
    expect(alertsFrom('t/1', 'x', [exit(0)], 0)[0]!.notify).toBe(false)
    expect(alertsFrom('t/1', 'x', [exit(0)], 0, { finished: true })[0]!.notify).toBe(true)
    expect(alertsFrom('t/1', 'x', [exit(3)], 0)).toEqual([])
  })
  test('a stall toasts without a notification; a near cap notifies', () => {
    const d = running()
    d.health = { ...d.health, suspect_stall: true, cap_eta_min: 7 }
    const got = healthAlerts('demo/T-1', 'x', d, { stall: false, cap: false })
    expect(got.map(a => [a.kind, a.notify])).toEqual([['stall', false], ['cap', true]])
    expect(healthAlerts('demo/T-1', 'x', d, { stall: true, cap: true })).toEqual([])
  })
})

describe('run list and run view (MRV §2.3, §2.4)', () => {
  test('waiting runs sort first', () => {
    const list = runList([summary({ label: 'b' }), summary({ label: 'a', mark: '⏸', waiting: 30 })])
    expect(list.map(r => r.label)).toEqual(['a', 'b'])
    expect(listRow(list[0]!)).toContain('waits 30s')
  })
  test('unit rows: marks, strip, trip back, judge (MRV-B3)', () => {
    const rows = unitRows(paused)
    const draft = rows.find(r => r.name === 'draft')!
    const review = rows.find(r => r.name === 'review')!
    expect(draft.mark).toBe('✓')
    expect(draft.from).toBe('←review')
    expect(draft.backLines).toEqual(['↩ from review (gate BACK: c-review)'])
    expect(unitRowText(draft)).toMatch(/^✓ draft {2}S C J G {2}v2 a3 {2}←review {2}1\/1 · 0.80/)
    expect(review.mark).toBe('⏸')
    expect(review.judge).toBe('0/1 · 0.80 · 1 UNVERIFIABLE')
    expect(review.strip).toEqual({ S: 'done', C: 'done', J: 'failed', G: 'failed' })
  })
  test('a running judge is highlighted (MRV-B1)', () => {
    const review = unitRows(running()).find(r => r.name === 'review')!
    expect(review.mark).toBe('▶')
    expect(review.strip.J).toBe('running')
  })
  test('narrator lines and the touch strip', () => {
    const lines = narrator(paused)
    expect(lines).toHaveLength(5)
    expect(lines[lines.length - 1]).toMatch(/^\d\d:\d\d paused at review \(escalation\)/)
    expect(touchStrip(paused)).toBe('')
  })
  test('attempt rows show causes and routes (MDD §2.1)', () => {
    const rows = attemptRows(paused, 'draft')
    expect(rows.map(r => [r.visit, r.from, r.attempt, r.gate, r.cause])).toEqual([
      [1, 'start', 1, 'RETRY → draft', 'blocker:c-file'], [1, '', 2, 'PROCEED', ''], [2, 'back:review', 3, 'PROCEED', '']])
  })
  test('session Now tab, with inputs hidden on request (MDD-B5, MDD-B3)', () => {
    const s = running().units.find(u => u.name === 'review')!.visits.at(-1)!.attempts[0]!.judge!.sessions![0]!
    expect(sessionNow(s, true, 10)).toEqual(['Grep · TODO · 12s', 'last event 9s ago · idle 90% ⚠'])
    expect(sessionNow(s, false, 10)[0]).toBe('Grep · 12s')
  })
})

describe('sources (MDS §2, contract M1)', () => {
  test('only read-only verbs are built (MDS-AC-2)', () => {
    for (const argv of [statusArgv(), detailArgv('demo/T-1'), detailArgv('demo/T-1', 'review')]) {
      expect(isReadOnly(argv)).toBe(true)
    }
    for (const v of WRITING_VERBS) expect((READ_ONLY_VERBS as readonly string[]).includes(v)).toBe(false)
    for (const w of [['tempergraph', 'stats', 'flush'], ['tempergraph', 'stats', 'sync'], ['tempergraph', 'stats', '--sync', '--json']])
      expect(isReadOnly(w)).toBe(false) // stats writes only as flush and sync (engine CST §2.5)
    expect(() => fleetArgv('live', 'team; rm')).toThrow()
    expect(() => detailArgv('demo/T-1; rm -rf /')).toThrow()
    expect(() => detailArgv('demo/T-1', '--now')).toThrow()
  })
  test('the hooks module runs a process in one place, behind the read-only guard (MDS-AC-2)', async () => {
    const src = await Bun.file(new URL('../hooks/register.tsx', import.meta.url).pathname).text()
    expect(src.match(/\$\.process\.(run|spawn)\(/g) ?? []).toEqual(['$.process.run('])
    const guard = src.indexOf('if (!isReadOnly(argv)) throw')
    expect(guard).toBeGreaterThan(-1)
    expect(guard).toBeLessThan(src.indexOf('$.process.run('))
    const built = [...src.matchAll(/verb<\w+>\(\$, (\w+)\(/g)].map(m => m[1])
    expect(built.length).toBeGreaterThan(0)
    for (const b of built) expect(['statusArgv', 'detailArgv', 'projectionArgv', 'fleetArgv']).toContain(b)
    expect([...src.matchAll(/[^.]run\(\$, (\w+)\)/g)].map(m => m[1]).sort()).toEqual(['PS_ARGV', 'argv'])
    expect(src).not.toMatch(/\$\.fs\.(write|mkdir|remove|rename|append)/)
  })
  test('a record written in two pieces is yielded once (MDS-AC-3)', () => {
    const a = '{"seq": 1, "ts": "t", "kind": "check"}\n{"seq": 2, "ts": "t", "ki'
    const first = parseChunk(a, 0)
    expect(first.records.map(r => r.seq)).toEqual([1])
    const rest = '{"seq": 2, "ts": "t", "kind": "gate"}\n'
    const second = parseChunk(rest, first.offset)
    expect(second.records.map(r => r.seq)).toEqual([2])
    expect(keepTail(first.records, [...first.records, ...second.records]).map(r => r.seq)).toEqual([1, 2])
  })
  test('a shrunk file is read again from 0; reads are bounded', () => {
    expect(nextRead({ offset: 500, size: 500 }, 200)).toEqual({ offset: 0, length: 200 })
    expect(nextRead({ offset: 100, size: 100 }, 300)).toEqual({ offset: 100, length: 200 })
    expect(nextRead({ offset: 0, size: 0 }, 10 * 1024 * 1024).length).toBe(4 * 1024 * 1024)
  })
  test('poll rates (MDS-B1)', () => {
    expect(statusEvery(false, false)).toBe(30_000)
    expect(statusEvery(true, false)).toBe(5_000)
    expect(3600_000 / statusEvery(false, false)).toBe(120)
  })
  test('the fixture log parses whole', () => {
    const { records } = parseChunk(logText, 0)
    expect(records.length).toBe(logText.trim().split('\n').length - 1) // the schema line has no seq
  })
})

describe('supervision level (SUP §2.3, MRV §2.4)', () => {
  test('the paused fixture has a level from the engine\'s record, and a missing record shows none', () => {
    expect(levelText(paused)).toMatch(/^(observer|approver|consultant|collaborator|operator)/)
    const d = clone(paused)
    d.supervision = { touches: [] }
    expect(levelText(d)).toBeNull()
    d.supervision = { level: 'consultant', level_by: 'agent' }
    expect(levelText(d)).toBe('consultant by agent')
  })
})

