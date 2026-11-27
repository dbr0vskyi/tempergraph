// Session tests for the monitor mod, run by `claude plugin test plugins/tempergraph-monitor` against the engine.
// The engine's documents come from tests/fixtures (written by make_fixtures.py from a scripted engine run).
// Every hook here stands for Claude Code; `process.run` stands for the tempergraph CLI.

import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'
import { detailPaused, status, statsProjection } from './fixtures/documents'

const BAND = {
  plugin: 'tempergraph-monitor',
  component: 'AbovePrompt',
  props: { hasSurvey: false, isCollapsed: false, isWorking: false, maxRows: 10, bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

const PANE = {
  plugin: 'tempergraph-monitor',
  component: 'Pane',
  requestId: 'tempergraph',
  props: { title: 'tempergraph', isFocused: true, bodyColumns: 100, placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const ran: string[][] = []

declare const setTimeout: (run: (value?: unknown) => void, ms: number) => unknown

/** The first read runs unawaited from `session.start`; a test lets it finish before it looks. */
async function settle(): Promise<void> {
  for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 5))
}

type Reply = { exitCode: number; stdout: string }

/** What the engine prints: the status document, or the detail and projection documents. */
function fixtureReply(argv: readonly string[]): Reply {
  const doc = argv.includes('--detail') ? detailPaused : argv.includes('--projection') ? statsProjection : status
  return { exitCode: 0, stdout: JSON.stringify(doc) }
}

function engine(on: On, onRegister = () => {}, answer: (argv: readonly string[]) => Reply = fixtureReply) {
  on('command.register', () => {
    onRegister()
    return { value: { command: 'tg' } }
  })
  on('clock.every', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.notify', () => ({ value: { isSent: false, reason: 'no-channel' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('clock.now', () => ({ value: Date.parse('2026-11-20T09:22:00Z') }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 0, mtimeMs: 0, isLink: false } }))
  on('process.run', (_, e) => {
    ran.push([...e.argv])
    const r = answer(e.argv)
    return { value: { exitCode: r.exitCode, stdout: r.stdout, stderr: '', isStdoutTruncated: false,
      isStderrTruncated: false } }
  })
}

test('the band names the paused run and the monitor only runs read-only verbs', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const row = await ui.find({ key: 'tg-band' })
    expect(row?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
    await ui.unmount()
  }
  expect(ran.length).toBeGreaterThan(0)
  for (const argv of ran) {
    expect(['status', 'events', 'stats']).toContain(argv[1])
    expect(argv.some(a => ['flush', 'sync', '--sync'].includes(a))).toBe(false)
  }
})

test('/tg opens the run list and a run opens its unit rows', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/work/repo', surface: 'desktop', isInteractive: true })
  const out = await $.command.run({ command: 'tg', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  expect(out.text).toBe('Monitor opened.')
  await settle()
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'run:demo/T-1' })
  expect((await ui.find({ key: 'unit:review' })) ?? null).not.toBeNull()
  await ui.unmount()
})

test('a headless session starts no timers and registers no command', async ($, on) => {
  let registered = false
  engine(on, () => {
    registered = true
  })
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: false })
  expect(registered).toBe(false)
})

test('a decision fills the prompt and nothing runs (MAC-B1)', async ($, on) => {
  const filled: string[] = []
  engine(on)
  on('prompt.read', () => ({ value: { text: '', cursor: 0 } }))
  on('prompt.fill', (_, e) => {
    filled.push(e.text)
    return { isFilled: true }
  })
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await settle()
  await $.command.run({ command: 'tg', args: 'demo/T-1', origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 } })
  await settle()
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'gate' })
    await ui.press({ key: 'decide:1' })
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
  expect(filled).toEqual(['!tempergraph resume demo T-1 --decision retry', '!tempergraph resume demo T-1 --decision retry'])
  for (const argv of ran) {
    expect(['status', 'events', 'stats']).toContain(argv[1])
    expect(argv.some(a => ['flush', 'sync', '--sync'].includes(a))).toBe(false)
  }
})

test('the cost tab reads reported money as rep (MCF §2.1, M4)', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/work/repo', surface: 'desktop', isInteractive: true })
  await settle()
  await $.command.run({ command: 'tg', args: 'demo/T-1', origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 } })
  await settle()
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'cost' })
  expect((await ui.find({ type: 'Text', text: /^total/ }))?.text).toBe('total $0.10 rep · complete')
  await ui.unmount()
})

test('the cost tab shows the workflow\'s projection (MCF §2.1)', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/work/repo', surface: 'desktop', isInteractive: true })
  await settle()
  await $.command.run({ command: 'tg', args: 'demo/T-1', origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 } })
  await settle()
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'cost' })
  expect((await ui.find({ type: 'Text', text: /^projection/ }))?.text).toBe('projection median $0.04 · p90 $0.04 est · 1 run (thin)')
  await ui.unmount()
})

test('with no fleet sink the fleet tab says how to set one up (MCF-B5)', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await settle()
  await $.command.run({ command: 'tg', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'fleet' })
  expect((await ui.find({ type: 'Text', text: /^No fleet sink/ })) ?? null).not.toBeNull()
  expect((await ui.find({ type: 'Text', text: 'This month by machine' })) ?? null).not.toBeNull()
  await ui.unmount()
})

// -- finding the engine: the setting, then PATH, then the engine home (MAC-B5, MAC-B6, MAC-B7) ---------------------

const SETTING = '/opt/tg/bin/tempergraph'
const HOME = '/home/me/.tempergraph'
const NOT_FOUND: Reply = { exitCode: 127, stdout: '' }

const withSetting = (engine_path: string) => ({ options: { engine_path } })

/** Every program exits 127 except `program` (the engine) and the one constant probe of the engine home. */
function only(program: string, home = HOME) {
  return (argv: readonly string[]): Reply =>
    argv[0] === 'sh' ? { exitCode: 0, stdout: home } : argv[0] === program ? fixtureReply(argv) : NOT_FOUND
}

/** The engine verbs the monitor ran: not the `ps` listing and not the engine-home probe. */
const verbs = () => ran.filter(a => a[0] !== 'ps' && a[0] !== 'sh')
const probes = () => ran.filter(a => a[0] === 'sh')

test('MAC-AC-4 AC 1 AC 3 AC 4: the program of the engine_path setting answers', withSetting(SETTING), async ($, on) => {
  ran.length = 0
  engine(on, () => {}, only(SETTING))
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await settle()
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
  await ui.unmount()
  expect(verbs().length).toBeGreaterThan(0)
  for (const argv of verbs()) expect(argv[0]).toBe(SETTING)
  expect(probes()).toEqual([]) // the engine home is only asked after the setting and PATH exited 127
})

test('MAC-AC-4 AC 1 AC 3 AC 4: tempergraph on PATH answers after the setting exited 127', withSetting(SETTING), async ($, on) => {
  ran.length = 0
  engine(on, () => {}, only('tempergraph'))
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await settle()
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
  await ui.unmount()
  expect(verbs()[0]).toEqual([SETTING, 'status', '--json'])
  expect(verbs()[1]).toEqual(['tempergraph', 'status', '--json'])
  expect(verbs().filter(a => a[0] === SETTING).length).toBe(1) // MAC-B5: the setting is not tried again
  expect(verbs().filter(a => a[0] === 'tempergraph').length).toBeGreaterThan(1)
  expect(probes()).toEqual([])
})

test('MAC-AC-4 MAC-AC-5 AC 1 AC 3 AC 4: the shim of the engine home answers and is kept for later verbs', withSetting(SETTING),
  async ($, on) => {
    ran.length = 0
    const shim = `${HOME}/bin/tempergraph`
    engine(on, () => {}, only(shim))
    await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
    await settle()
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
    await ui.unmount()
    expect(verbs().slice(0, 3)).toEqual([[SETTING, 'status', '--json'], ['tempergraph', 'status', '--json'],
      [shim, 'status', '--json']])
    expect(verbs().length).toBeGreaterThan(3) // the projection verb of the same read went on
    expect(verbs().filter(a => a[0] === SETTING).length).toBe(1)
    expect(verbs().filter(a => a[0] === 'tempergraph').length).toBe(1)
    expect(verbs().slice(3).every(a => a[0] === shim)).toBe(true)
    expect(probes().length).toBe(1) // the home is asked once per session
  })

test('MAC-AC-4 AC 1 AC 3 AC 4: a setting whose run rejects is passed over like a program that does not exist', withSetting(SETTING),
  async ($, on) => {
    ran.length = 0
    engine(on, () => {}, argv => {
      if (argv[0] === SETTING) throw new Error('spawn ENOENT')
      return only('tempergraph')(argv)
    })
    await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
    await settle()
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
    await ui.unmount()
    expect(verbs()[0]).toEqual([SETTING, 'status', '--json'])
    expect(verbs()[1]).toEqual(['tempergraph', 'status', '--json'])
    expect(verbs().filter(a => a[0] === SETTING).length).toBe(1)
    expect(probes()).toEqual([])
  })

test('MAC-AC-4 MAC-AC-5 AC 1 AC 3 AC 4: a kept program that exits 127 starts the lookup again from the setting', withSetting(SETTING),
  async ($, on) => {
    ran.length = 0
    const shim = `${HOME}/bin/tempergraph`
    let moved = false // the engine moves from the home shim to PATH after the shim answered once
    engine(on, () => {}, argv => {
      if (argv[0] === 'sh') return { exitCode: 0, stdout: HOME }
      if (argv[0] === shim) {
        if (moved) return NOT_FOUND
        moved = true
        return fixtureReply(argv)
      }
      return argv[0] === 'tempergraph' && moved ? fixtureReply(argv) : NOT_FOUND
    })
    await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
    await settle()
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
    await ui.unmount()
    expect(verbs().slice(0, 6).map(a => a[0])).toEqual([SETTING, 'tempergraph', shim, shim, SETTING, 'tempergraph'])
    expect(verbs().slice(6).every(a => a[0] === 'tempergraph')).toBe(true) // the new program is kept
    expect(verbs().filter(a => a[0] === shim).length).toBe(2) // the shim is not run again in the restarted lookup
    expect(probes().length).toBe(1) // the home is not asked again
  })

for (const [what, home] of [['TEMPERGRAPH_HOME set to a folder that holds the shim', '/srv/tg-home'],
  ['TEMPERGRAPH_HOME unset, the shim in ~/.tempergraph/bin', HOME]] as const) {
  test(`MAC-AC-6 AC 1: the engine home is read from ${what}`, async ($, on) => {
    ran.length = 0
    const shim = `${home}/bin/tempergraph`
    engine(on, () => {}, only(shim, home))
    await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
    await settle()
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
    await ui.unmount()
    expect(verbs()).toContainEqual([shim, 'status', '--json'])
    expect(probes()[0]?.slice(0, 2)).toEqual(['sh', '-c'])
  })
}

/** Every program exits 127; the probe of the engine home answers. */
const nobody = (argv: readonly string[]): Reply => (argv[0] === 'sh' ? { exitCode: 0, stdout: HOME } : NOT_FOUND)

test('MDS-AC-5 MDS-AC-6 AC 2 AC 4: no place holds the engine: each place once, then nothing, and the pane names them',
  withSetting(SETTING), async ($, on) => {
    ran.length = 0
    const shim = `${HOME}/bin/tempergraph`
    engine(on, () => {}, nobody)
    await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
    await settle()
    expect(verbs()).toEqual([[SETTING, 'status', '--json'], ['tempergraph', 'status', '--json'], [shim, 'status', '--json']])
    await settle()
    expect(verbs().length).toBe(3) // polling stopped: no engine verb after the first lookup
    const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect((await band.find({ type: 'Text', text: 'tempergraph not found' })) ?? null).not.toBeNull()
    await band.unmount()
    const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
    expect((await ui.find({ type: 'Text', text: 'tempergraph is not installed here.' })) ?? null).not.toBeNull()
    expect((await ui.find({ type: 'Text', text: new RegExp(SETTING) })) ?? null).not.toBeNull()
    expect((await ui.find({ type: 'Text', text: /PATH/ })) ?? null).not.toBeNull()
    expect((await ui.find({ type: 'Text', text: new RegExp(shim) })) ?? null).not.toBeNull()
    await ui.unmount()
  })

test('MDS-AC-5 MDS-AC-6 AC 2 AC 4: with no setting the pane names PATH and the engine home, and no setting path', async ($, on) => {
  ran.length = 0
  const shim = `${HOME}/bin/tempergraph`
  engine(on, () => {}, nobody)
  await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
  await settle()
  expect(verbs()).toEqual([['tempergraph', 'status', '--json'], [shim, 'status', '--json']])
  await settle()
  expect(verbs().length).toBe(2)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: 'tempergraph is not installed here.' })) ?? null).not.toBeNull()
  expect((await ui.find({ type: 'Text', text: /PATH/ })) ?? null).not.toBeNull()
  expect((await ui.find({ type: 'Text', text: new RegExp(shim) })) ?? null).not.toBeNull()
  expect((await ui.find({ type: 'Text', text: /engine_path/ })) ?? null).toBeNull()
  await ui.unmount()
})

for (const setting of ['bin/tempergraph', '/usr/local/bin/other']) {
  test(`MAC-AC-7 AC 1 AC 4: the engine_path setting ${setting} is not run`, withSetting(setting), async ($, on) => {
    ran.length = 0
    engine(on, () => {}, only('tempergraph'))
    await $.session.start({ cwd: '/work/repo', surface: 'terminal', isInteractive: true })
    await settle()
    const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
    expect((await ui.find({ key: 'tg-band' }))?.text ?? '').toContain('⏸ repo/tg/demo/T-1')
    await ui.unmount()
    expect(ran.some(a => a[0] === setting)).toBe(false)
    expect(verbs().length).toBeGreaterThan(0)
    for (const argv of verbs()) expect(argv[0]).toBe('tempergraph')
  })
}

// -- scope = machine: other state roots (MDS-B4, MRV §2.3, issue 145) ------------------------------------------------

/** A machine-scope status document: this root, two other roots holding the same ended thread id, one live run in
 * another root, and five indexed roots that are gone. */
function machineReply(argv: readonly string[]): Reply {
  if (!argv.includes('--all-roots')) return fixtureReply(argv)
  const here = '/work/repo/.tempergraph'
  const row = status.threads[0]!
  const other = (root: string, extra: object) => ({ ...row, state_root: root, alias: undefined, label: undefined, ...extra })
  const threads = [
    { ...row, state_root: here },
    other('/w/alpha/.tempergraph', { state: 'finished', alive: false, exit_code: 0, pending_gates: [] }),
    other('/w/beta/.tempergraph', { state: 'finished', alive: false, exit_code: 0, pending_gates: [] }),
    other('/w/gamma/.tempergraph', { state: 'running', alive: true, pending_gates: [] }),
  ]
  const roots = [{ path: here, missing: false }, ...['a', 'b', 'c', 'd', 'e'].map(n => ({ path: `/w/${n}/.tempergraph`, missing: true }))]
  return { exitCode: 0, stdout: JSON.stringify({ ...status, threads, roots }) }
}

test('rows of other roots name their repository, ended ones fold and missing roots are one line', { options: { scope: 'machine' } },
  async ($, on) => {
    engine(on, () => {}, machineReply)
    await $.session.start({ cwd: '/work/repo', surface: 'desktop', isInteractive: true })
    await settle()
    await $.command.run({ command: 'tg', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
    await settle()
    const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
    expect((await ui.find({ type: 'Text', text: '5 state roots missing: a, b, c, +2 more' })) ?? null).not.toBeNull()
    expect((await ui.find({ key: 'others-fold' }))?.text ?? '').toContain('2 ended runs in other repositories')
    expect((await ui.find({ key: 'other:/w/gamma/.tempergraph|demo/T-1' }))?.text ?? '').toContain('gamma  ▶ gamma/')
    expect((await ui.find({ key: 'other:/w/alpha/.tempergraph|demo/T-1' })) ?? null).toBeNull()
    await ui.press({ key: 'others-fold' })
    const a = (await ui.find({ key: 'other:/w/alpha/.tempergraph|demo/T-1' }))?.text ?? ''
    const b = (await ui.find({ key: 'other:/w/beta/.tempergraph|demo/T-1' }))?.text ?? ''
    expect(a).toContain('alpha/')
    expect(b).toContain('beta/')
    const hash = (t: string) => /·([0-9a-f]{4})/.exec(t)?.[1]
    expect(hash(a)).toBeDefined()
    expect(hash(a)).not.toBe(hash(b))
    await ui.unmount()
  })

// -- a sign of life during a long session (MRV §2.3, MDS §2.1, issue 142) ------------------------------------------

test('MRV-AC-4: a long session with no new run-log record still moves its row, and a stall is marked', async ($, on) => {
  const clock = mock.clock(on, { now: Date.parse('2026-11-20T09:22:00Z') })
  let reads = 0
  const row = { ...status.threads[0]!, state: 'running', alive: true as boolean, pending_gates: [] }
  const detail = (): unknown => {
    reads += 1
    type Loose = { health: Record<string, unknown>; units: { name: string; state: string;
      visits: { attempts: { step: { sessions: Record<string, unknown>[] } }[] }[] }[] }
    const d = structuredClone(detailPaused) as unknown as Loose
    const unit = d.units.find(u => u.name === 'review')!
    unit.state = 'running'
    const session = unit.visits.at(-1)!.attempts.at(-1)!.step.sessions[0]!
    session.live = { open_tool: null, recent: [], last_event_age_s: reads * 10 }
    d.health = { ...d.health, alive: true, suspect_stall: reads >= 3 }
    return d
  }
  on('command.register', () => ({ value: { command: 'tg' } }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.notify', () => ({ value: { isSent: false, reason: 'no-channel' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 0, mtimeMs: 0, isLink: false } }))
  on('process.run', (_, e) => {
    const doc = e.argv.includes('--detail') ? detail() : e.argv.includes('--projection') ? statsProjection
      : { ...status, threads: [row] }
    return { value: { exitCode: 0, stdout: JSON.stringify(doc), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  await $.session.start({ cwd: '/work/repo', surface: 'desktop', isInteractive: true })
  await clock.settle()
  await $.command.run({ command: 'tg', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } })
  await clock.advance(1_000)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  const first = (await ui.find({ key: 'run:demo/T-1' }))?.text ?? ''
  expect(first).toContain('quiet 10s')
  await clock.advance(10_000)
  const second = (await ui.find({ key: 'run:demo/T-1' }))?.text ?? ''
  expect(second).not.toBe(first)
  expect(second).toContain('quiet 20s')
  await clock.advance(10_000)
  expect((await ui.find({ key: 'run:demo/T-1' }))?.text ?? '').toContain('stall? quiet 30s')
  await ui.unmount()
})
