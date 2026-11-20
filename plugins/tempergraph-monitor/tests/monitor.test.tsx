// Session tests for the monitor mod, run by `claude plugin test plugins/tempergraph-monitor` against the engine.
// The engine's documents come from tests/fixtures (written by make_fixtures.py from a scripted engine run).
// Every hook here stands for Claude Code; `process.run` stands for the tempergraph CLI.

import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import { detailPaused, status } from './fixtures/documents'

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

function engine(on: On, onRegister = () => {}) {
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
    const doc = e.argv.includes('--detail') ? detailPaused : status
    return { value: { exitCode: 0, stdout: JSON.stringify(doc), stderr: '', isStdoutTruncated: false,
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
  for (const argv of ran) expect(['status', 'events']).toContain(argv[1])
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
  for (const argv of ran) expect(['status', 'events']).toContain(argv[1])
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
