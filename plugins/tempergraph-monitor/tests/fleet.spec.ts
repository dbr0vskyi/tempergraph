// @ts-nocheck: run by bun, whose types the plugin validator does not load.
// The fleet tab, the projection line and `scope = machine` (MCF §2.1, §2.2, MDS §2.1) against engine fixtures
// written by make_fixtures.py from two simulated machines sharing one sink folder.

import { describe, expect, test } from 'bun:test'

import {
  fleetAlerts, fleetRows, missingRoots, monthRows, otherRows, projectionText, repoName, syncedText, totalsText,
} from '../hooks/lib/fleet'
import type { LiveDoc, ProjectionDoc, StatsDoc } from '../hooks/lib/fleet'
import { fleetArgv, isReadOnly, projectionArgv, statusArgv } from '../hooks/lib/sources'

const dir = new URL('./fixtures/', import.meta.url).pathname
const live = (await Bun.file(dir + 'stats-live.json').json()) as LiveDoc
const month = (await Bun.file(dir + 'stats-machine.json').json()) as StatsDoc
const projection = (await Bun.file(dir + 'stats-projection.json').json()) as ProjectionDoc

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

describe('fleet tab (MCF §2.2)', () => {
  test('a run waiting on another machine is listed with its label and opens a card (MCF-B4)', () => {
    const doc = clone(live)
    const other = doc.runs!.find(r => !doc.machines!.find(m => m.machine_id === r.machine_id)?.this_machine)!
    other.waiting_for_person_s = 40 * 60
    const row = fleetRows(doc).find(r => !r.mine)!
    expect(row.text).toContain('⏸ 40m')
    expect(row.text).toContain('desk-b')
    expect(row.threadId).toBeNull()
    expect(row.card.at(-1)).toBe('logs are on desk-b')
  })
  test('a figure the engine did not record reads —, never $0.00 (M4)', () => {
    for (const r of fleetRows(live)) expect(r.text).not.toContain('$0.00')
    expect(totalsText({ runs: 2, reported_usd: null, estimated_usd: null })).toBe('2 runs · —')
  })
  test('this machine\'s rows open the run view', () => {
    const mine = fleetRows(live).filter(r => r.mine)
    expect(mine.length).toBeGreaterThan(0)
    for (const r of mine) expect(r.threadId).toMatch(/^demo\//)
  })
  test('the month keeps reported and estimated apart and names each exit', () => {
    const lines = monthRows(month)
    expect(lines.length).toBe(2)
    expect(lines.join('\n')).toContain('rep')
    expect(lines.join('\n')).toMatch(/finished 1|paused 1/)
    expect(totalsText({ runs: 1, reported_usd: 1, estimated_usd: 2, lower_bound: true })).toBe('1 run · ≥ $1.00 rep · ≥ $2.00 est')
  })
  test('the header says when the copy was synced (CST-B7)', () => {
    const at = Date.parse(Object.values(month.synced ?? {})[0]?.synced_at ?? '')
    expect(syncedText(month, at + 3_600_000)).toBe('team synced 1h00m ago')
    expect(syncedText({ schema_version: 1 }, 0)).toBe('not synced yet')
  })
  test('alerts_fleet raises once for a wait over 30 min on another machine (MBA §2.4)', () => {
    const doc = clone(live)
    for (const r of doc.runs!) r.waiting_for_person_s = 31 * 60
    const first = fleetAlerts(doc, new Set())
    const elsewhere = doc.runs!.filter(r => !doc.machines!.find(m => m.machine_id === r.machine_id)?.this_machine)
    expect(first.length).toBe(elsewhere.length)
    expect(first.length).toBeGreaterThan(0)
    expect(first[0]!.toast).toContain('desk-b')
    expect(fleetAlerts(doc, new Set(first.map(a => a.key)))).toEqual([])
  })
})

describe('projection line (MCF §2.1)', () => {
  test('median, p90 and the sample size, marked thin under 5 runs', () => {
    expect(projectionText(projection, 'demo')).toBe('median $0.04 · p90 $0.04 est · 1 run (thin)')
    expect(projectionText(projection, 'other')).toBe('no finished run yet')
    expect(projectionText(null, 'demo')).toBe('unavailable')
  })
})

describe('sources for the fleet and the machine scope (MDS §2.1, M1)', () => {
  test('every argv built is read-only', () => {
    for (const argv of [statusArgv(true), projectionArgv(), fleetArgv('live', 'team'), fleetArgv('machine', ''),
      fleetArgv('workflow', 'team')]) expect(isReadOnly(argv)).toBe(true)
    expect(fleetArgv('machine', '')).toContain('--local') // MCF-B5: no sink, this machine's month only
    expect(statusArgv(true)).toContain('--all-roots')
  })
  test('a missing root is shown, named by its repository (MDS-B4)', () => {
    expect(missingRoots([{ path: '/w/a/.tempergraph', missing: false }, { path: '/w/gone/.tempergraph', missing: true }]))
      .toEqual(['gone: missing (/w/gone/.tempergraph)'])
    expect(repoName('C:\\w\\proj\\.tempergraph')).toBe('proj')
  })
  test('many missing roots are one line with their count (MDS-B4, issue 145)', () => {
    const gone = ['a', 'b', 'c', 'd', 'e'].map(n => ({ path: `/w/${n}/.tempergraph`, missing: true }))
    expect(missingRoots(gone)).toEqual(['5 state roots missing: a, b, c, +2 more'])
  })
  test('ended runs of other roots fold under one line with their count (MRV §2.3, issue 145)', () => {
    const rows = [{ live: true, k: 1 }, { live: false, k: 2 }, { live: false, k: 3 }]
    expect(otherRows(rows, false)).toEqual({ shown: [rows[0]], fold: '▸ 2 ended runs in other repositories' })
    expect(otherRows(rows, true).shown).toHaveLength(3)
    expect(otherRows([rows[0]!], false).fold).toBeNull()
  })
})
