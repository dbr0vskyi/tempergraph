// @ts-nocheck: run by bun, whose types the plugin validator does not load.
// Actions (MAC), the cost tab (MCF §2.1), session tabs (MDD §2.4), filter and pin (MRV §2.2) and the band's
// error rows (MBA §4), against the engine fixtures. Run `bun test ./tests/*.spec.ts` from the plugin folder.

import { describe, expect, test } from 'bun:test'

import { askFill, driverFill, resumeFills, stopFills } from '../hooks/lib/actions'
import { costTab, figure } from '../hooks/lib/cost'
import type { DetailDoc } from '../hooks/lib/engine'
import { bandRow, shownRuns, nextFilter } from '../hooks/lib/model'
import type { RunSummary } from '../hooks/lib/model'
import { callsFrom, callText, processTree, procText, tailLines } from '../hooks/lib/session'
import {
  enginePlaces, HOME_ARGV, homeShimPath, isReadOnly, learnHome, lookedAt, statusArgv, useEngine, useProgram,
} from '../hooks/lib/sources'

const dir = new URL('./fixtures/', import.meta.url).pathname
const paused = (await Bun.file(dir + 'detail-paused.json').json()) as DetailDoc
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T

function summary(over: Partial<RunSummary>): RunSummary {
  return { threadId: 'demo/T-9', workflow: 'demo', label: 'x', mark: '▶', state: 'running', alive: true, unit: 'code',
    node: 'J', attempt: 1, passed: 1, planned: 3, elapsed: 60, waiting: null, cost: '$1.00 est', question: null,
    resume: null, ...over }
}

describe('actions fill the prompt (MAC §2.1, contract M2)', () => {
  test('one resume fill per decision word, from the engine resume line (MAC-B1, MAC-AC-3)', () => {
    const fills = resumeFills(paused.pause)
    expect(fills.map(f => f.text)).toEqual([
      '!tempergraph resume demo T-1 --decision proceed',
      '!tempergraph resume demo T-1 --decision retry',
      '!tempergraph resume demo T-1 --decision back:draft',
      '!tempergraph resume demo T-1 --decision stop',
    ])
    expect(fills.map(f => f.hotkey)).toEqual(['1', '2', '3', '4'])
  })
  test('a resume line without a placeholder gets --decision; a bad word or line is dropped', () => {
    const p = { unit: 'u', kind: 'approval', resume: ['tempergraph resume wf T-2'], decisions: ['approve', 'x; rm -rf ~'] }
    expect(resumeFills(p).map(f => f.text)).toEqual(['!tempergraph resume wf T-2 --decision approve'])
    expect(resumeFills({ ...p, resume: ['rm -rf / --decision <a>'] })).toEqual([])
    expect(() => resumeFills({ ...p, resume: ['tempergraph resume wf $(id) --decision <a>'] })).toThrow()
  })
  test('stop fills hold only the thread id (MAC-B4)', () => {
    expect(stopFills({ thread_id: 'demo/T-1' }).map(f => f.text))
      .toEqual(['!tempergraph stop demo/T-1', '!tempergraph stop demo/T-1 --now'])
    expect(() => stopFills({ thread_id: 'demo/T-1; rm -rf ~' })).toThrow()
  })
  test('the run driver and "ask Claude" fills name engine values only', () => {
    expect(driverFill(paused)?.text).toBe('/tempergraph:run demo/T-1 is paused at review; walk me through the decision.')
    const s = paused.units[0].visits[0].attempts[0].step.sessions[0]
    expect(askFill(s, 'draft', 1, 'RETRY')?.text)
      .toBe(`Read ${s.transcript.engine} and explain why the step of draft attempt 1 returned RETRY.`)
    expect(askFill({ ...s, transcript: null }, 'draft', 1, null)).toBeNull()
  })
  test('the hooks module never sends: no prompt submit, command run or tool (MAC-AC-1, MAC-B2)', async () => {
    const src = await Bun.file(new URL('../hooks/register.tsx', import.meta.url).pathname).text()
    expect(src).not.toMatch(/\$\.prompt\.submit|\$\.command\.run|\$\.tool\.register|\$\.session\.append/)
  })
})

describe('cost tab (MCF §2.1, contract M4)', () => {
  test('the fixture run: reported totals, by unit with repeats, by kind and executor', () => {
    const c = costTab(paused)
    expect(c.total).toBe('$0.10 rep')
    expect(c.completeness).toBe('complete')
    expect(c.units.map(u => u.name)).toEqual(['draft', 'review'])
    expect(c.units[0].repeats.length).toBeGreaterThan(0)
    expect(c.kinds.map(k => k.kind).sort()).toEqual(['judge', 're-ask', 'step'])
    expect(c.units[1].repeats).toEqual([{ cause: 'visit 2 (proceed)', cost: '$0.02 rep' }])
    expect(c.executors[0].tokens).toContain('cache read —')
    expect(c.budget).toBe('no run cost cap')
    expect(c.supervision).toBe('level observer · cost not recorded') // not closed yet: no SCO figures
  })
  test('the supervision line from SCO closed figures (MCF §2.1)', () => {
    const fig = (usd: number) => ({ tokens: {}, estimated_usd: usd })
    const closed = { ...paused, supervision: { ...paused.supervision, cost: {
      marginal: { by_category: { start: fig(0.01), rewake: fig(0.3) }, total: fig(0.31) },
      turn: { by_category: {}, total: fig(0.9) }, completeness: 'complete' } } } as DetailDoc
    expect(costTab(closed).supervision)
      .toBe('level observer · marginal $0.31 est · turn $0.90 est · complete (start $0.01 est, rewake $0.30 est)')
    const unmeasured = { ...paused, supervision: { ...paused.supervision, cost: {
      marginal: null, turn: null, completeness: 'incomplete' } } } as DetailDoc
    expect(costTab(unmeasured).supervision).toBe('level observer · cost not measured (incomplete)')
  })
  test('never zero, never summed (MCF-B1, MCF-B2)', () => {
    expect(figure({ rep: 0, est: 4.1, reported: 0, estimated: 2, unmeasured: 1, sessions: 3 })).toBe('≥ $4.10 est')
    expect(figure({ rep: 0.22, est: 0.95, reported: 1, estimated: 2, unmeasured: 0, sessions: 3 }))
      .toBe('$0.22 rep (1 of 3 sessions) · $0.95 est')
    expect(figure({ rep: 0, est: 0, reported: 0, estimated: 0, unmeasured: 2, sessions: 2 })).toBe('—')
  })
  test('cap warning line (MCF-B3)', () => {
    const d = clone(paused)
    d.budgets.run_cost_cap = { limit: 20, left: 3 }
    d.health = { ...d.health, burn_usd_per_h: 9, cap_eta_min: 20 }
    expect(costTab(d).budget).toBe('$3.00 left of $20.00 · ~20 min at $9/h')
  })
})

describe('session tabs (MDD §2.4)', () => {
  const journal = [
    '{"t":1.0,"n":1,"ev":"tool_started","name":"Bash","call_id":"a","capability":"shell","input_summary":"make test"}',
    '{"t":2.0,"n":2,"ev":"text","last_line":"hi"}',
    '{"t":3.5,"n":3,"ev":"tool_finished","call_id":"a","ok":true,"duration_s":2.5}',
    '{"t":4.0,"n":4,"ev":"tool_started","name":"Read","call_id":"b","capability":"read","input_summary":"src/a.py","subagent":true}',
    'not json',
  ].join('\n')
  test('calls pair start and finish; an open call is marked', () => {
    expect(callsFrom(journal, true).map(callText)).toEqual(['✓   1s Bash · make test  3s', '  ▶   4s Read · src/a.py'])
  })
  test('hidden inputs show names only (MDD-B5)', () => {
    expect(callsFrom(journal, false).map(callText).join('\n')).not.toMatch(/make test|src\/a\.py/)
  })
  test('the process tree keeps only the session group, program names only (MDD-AC-3)', () => {
    const ps = ['  100   100     1   07:02 /bin/bash', '  101   100   100   07:01 make', '  102   100   101   06:59 pytest',
      '  900   900     1   01:00 decoy'].join('\n')
    expect(processTree(ps, 100).map(procText)).toEqual(['bash (100) 07:02', '  make (101) 07:01', '    pytest (102) 06:59'])
  })
  test('a log tail drops the cut first line', () => {
    expect(tailLines('ut line\nwhole 1\nwhole 2\n', true)).toEqual(['whole 1', 'whole 2'])
  })
})

describe('run list filter and pins (MRV §2.2)', () => {
  const list = [summary({ threadId: 'a/1', label: 'a', mark: '▶' }), summary({ threadId: 'b/1', label: 'b', mark: '⏸' }),
    summary({ threadId: 'c/1', label: 'c', mark: '✓', alive: false }), summary({ threadId: 'd/1', label: 'd', mark: '✗', alive: false })]
  test('filters cycle and select', () => {
    expect(nextFilter('all')).toBe('live')
    expect(nextFilter('finished today')).toBe('all')
    expect(shownRuns(list, 'waiting', [], {}, 3600).map(r => r.label)).toEqual(['b'])
    expect(shownRuns(list, 'failed', [], {}, 3600).map(r => r.label)).toEqual(['d'])
    expect(shownRuns(list, 'finished today', [], { 'c/1': 100 }, 3600).map(r => r.label)).toEqual(['c'])
    expect(shownRuns(list, 'finished today', [], { 'c/1': 7200 }, 3600)).toEqual([])
  })
  test('pinned runs come first', () => {
    expect(shownRuns(list, 'all', ['d/1'], {}, 0).map(r => r.label)).toEqual(['d', 'b', 'a', 'c'])
  })
})

describe('band error rows (MBA §4)', () => {
  test('under 20 columns, and stale after 60 s', () => {
    const list = [summary({ threadId: 'a/1', mark: '▶' }), summary({ threadId: 'b/1', mark: '⏸' })]
    expect(bandRow(list, 12)).toBe('tg ⏸1')
    expect(bandRow([list[0]], 12)).toBe('tg ▶1')
    expect(bandRow(list, 120, {}, true)).toEndWith(' · stale')
  })
})

describe('engine path setting (MAC §2.3)', () => {
  test('an absolute path to the shim is used; anything else keeps PATH', () => {
    expect(useEngine('/opt/tg/bin/tempergraph')).toBe('/opt/tg/bin/tempergraph')
    expect(isReadOnly(statusArgv())).toBe(true)
    expect(useEngine('sh -c evil')).toBe('tempergraph')
    expect(useEngine('/usr/bin/python')).toBe('tempergraph')
    expect(useEngine('')).toBe('tempergraph')
  })
  test('MAC-AC-7 AC 1: a setting that is not the shim is taken as empty, so only PATH and the engine home are places', () => {
    for (const bad of ['bin/tempergraph', '/usr/local/bin/other', 'sh -c evil']) {
      useEngine(bad)
      expect(enginePlaces()).toEqual(['tempergraph'])
    }
    useEngine('  /opt/tg/bin/tempergraph  ')
    expect(enginePlaces()).toEqual(['/opt/tg/bin/tempergraph', 'tempergraph'])
  })
  test('MAC-AC-6 AC 1: the places are the setting, PATH, then the shim of the engine home', () => {
    useEngine('/opt/tg/bin/tempergraph')
    learnHome('/srv/tg-home/')
    expect(enginePlaces()).toEqual(['/opt/tg/bin/tempergraph', 'tempergraph', '/srv/tg-home/bin/tempergraph'])
    expect(lookedAt()).toEqual(['engine_path setting: /opt/tg/bin/tempergraph', 'PATH: tempergraph',
      'engine home: /srv/tg-home/bin/tempergraph'])
    useEngine('')
    expect(enginePlaces()).toEqual(['tempergraph']) // a reload forgets the answered home
    learnHome('/home/me/.tempergraph')
    expect(enginePlaces()).toEqual(['tempergraph', '/home/me/.tempergraph/bin/tempergraph'])
    expect(lookedAt()[0]).toBe('PATH: tempergraph')
  })
  test('MAC-AC-6 AC 1: the shim path of the engine home from a probe answer', () => {
    expect(homeShimPath('/home/me/.tempergraph')).toBe('/home/me/.tempergraph/bin/tempergraph')
    expect(homeShimPath('  /srv/tg-home/\n')).toBe('/srv/tg-home/bin/tempergraph')
    expect(homeShimPath('')).toBe('~/.tempergraph/bin/tempergraph')
    expect(homeShimPath(null)).toBe('~/.tempergraph/bin/tempergraph')
    useEngine('')
    learnHome('') // no usable answer: the label is named in the pane but no program is run
    expect(enginePlaces()).toEqual(['tempergraph'])
    expect(lookedAt()).toEqual(['PATH: tempergraph', 'engine home: ~/.tempergraph/bin/tempergraph'])
  })
  test('MAC-AC-6 AC 3: one place becomes the program of every verb, and only a place of the list can', () => {
    useEngine('/opt/tg/bin/tempergraph')
    learnHome('/srv/tg-home')
    expect(useProgram('/srv/tg-home/bin/tempergraph')).toBe(true)
    expect(statusArgv()[0]).toBe('/srv/tg-home/bin/tempergraph')
    expect(isReadOnly(statusArgv())).toBe(true)
    expect(isReadOnly(['tempergraph', 'status', '--json'])).toBe(false) // the old place is not the program any more
    expect(useProgram('/usr/bin/evil')).toBe(false)
    expect(statusArgv()[0]).toBe('/srv/tg-home/bin/tempergraph')
    useEngine('')
  })
  test('MAC-AC-6 AC 1: the engine-home probe is one constant read-only argv; no other shell command is', () => {
    expect(isReadOnly(HOME_ARGV)).toBe(true)
    expect(isReadOnly(['sh', '-c', 'evil'])).toBe(false)
    expect(isReadOnly([...HOME_ARGV, 'x'])).toBe(false)
  })
})
