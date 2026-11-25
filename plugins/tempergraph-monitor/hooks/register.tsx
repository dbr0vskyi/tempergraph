// tempergraph-monitor: the band, status line and alerts (MBA), the run list and run view (MRV), the drill-down
// (MDD), the cost tab and the fleet tab (MCF), other repositories on this machine (`scope = machine`, MDS §2.1)
// and the prompt-fill actions (MAC). It reads engine documents through read-only
// verbs and file reads on its own timers, never inside a drawing (MDS §1), and it sends nothing: every action
// fills the prompt for the person to send (contract M2).

import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register } from 'claude-code'

import type { MonitorEngine, MonitorExtra, MonitorFleet, MonitorOther, MonitorPrefs, MonitorRun, MonitorView } from '../types'
import { askFill, driverFill, resumeFills, stopFills } from './lib/actions'
import type { Fill } from './lib/actions'
import { costTab } from './lib/cost'
import type { DetailDoc, RunRecord, Session, StatusDoc } from './lib/engine'
import { isReadable } from './lib/engine'
import {
  fleetAlerts, fleetRows, missingRoots, monthRows, projectionText, repoName, syncedText,
} from './lib/fleet'
import type { LiveDoc, ProjectionDoc, StatsDoc } from './lib/fleet'
import {
  alertsFrom, attemptRows, bandRow, duration, findAttempt, healthAlerts, inFlight, listRow, nextFilter, nodeStrip,
  levelText, narrator, runList, sessionInfo, sessionNow, shownRuns, statusLine, summarise, touchStrip, unitRows, unitRowText,
} from './lib/model'
import type { Filter, RunSummary } from './lib/model'
import { callsFrom, callText, LOG_TAIL_BYTES, processTree, procText, PS_ARGV, tailLines } from './lib/session'
import {
  detailArgv, enginePlaces, fleetArgv, HOME_ARGV, homeKnown, isReadOnly, keepTail, learnHome, lookedAt, nextRead,
  parseChunk, projectionArgv, RATES, statusArgv, statusEvery, useEngine, useProgram,
} from './lib/sources'
import type { TailState } from './lib/sources'

const PANE = 'tempergraph'
const SHAPE = 'm1'
const STALE_AFTER_MS = 60_000
const PROJECTION_EVERY_MS = 10 * 60_000
const FLEET_EVERY_MS = 60_000

const runs = atom({ plugin: 'tempergraph-monitor', key: 'runs' } as const, [] as MonitorRun[], { shape: SHAPE })
const view = atom({ plugin: 'tempergraph-monitor', key: 'view' } as const, { level: 'runs' } as MonitorView, { shape: SHAPE })
const detail = atom({ plugin: 'tempergraph-monitor', key: 'detail' } as const, null as unknown, { shape: SHAPE })
const engine = atom({ plugin: 'tempergraph-monitor', key: 'engine' } as const,
  { installed: true, staleSince: null, error: null, looked: [] } as MonitorEngine, { shape: SHAPE })
const endedAgo = atom({ plugin: 'tempergraph-monitor', key: 'endedAgo' } as const, {} as Record<string, number>, { shape: SHAPE })
const prefs = atom({ plugin: 'tempergraph-monitor', key: 'prefs' } as const,
  { filter: 'all', pinned: [] } as MonitorPrefs, { shape: SHAPE })
const extra = atom({ plugin: 'tempergraph-monitor', key: 'extra' } as const,
  { key: '', tab: '', lines: [], note: null } as MonitorExtra, { shape: SHAPE })
const fleet = atom({ plugin: 'tempergraph-monitor', key: 'fleet' } as const,
  { live: null, month: null, byWorkflow: null, projection: null, missing: [], others: [], readAt: null, error: null } as MonitorFleet,
  { shape: SHAPE })

type $ = EngineInterface

/** The mod's settings (MAC §2.3), from the manifest's `userConfig`; a reload brings new values. */
type Settings = { alertsFinished: boolean; showInputs: boolean; showLogTails: boolean; machine: boolean;
  fleetSink: string; alertsFleet: boolean }

let settings: Settings = { alertsFinished: false, showInputs: true, showLogTails: true, machine: false, fleetSink: '',
  alertsFleet: false }

function readSettings(options: PluginOptions): Settings {
  useEngine(typeof options.engine_path === 'string' ? options.engine_path : '')
  return {
    alertsFinished: options.alerts_finished === true,
    showInputs: options.show_tool_inputs !== false,
    showLogTails: options.show_log_tails !== false,
    machine: options.scope === 'machine',
    fleetSink: typeof options.fleet_sink === 'string' && /^[a-z0-9-]{1,40}$/.test(options.fleet_sink) ? options.fleet_sink : '',
    alertsFleet: options.alerts_fleet === true,
  }
}

// Module variables start over at a reload; what must survive is in $.state and $.store.
const tails = new Map<string, TailState>()
const records = new Map<string, RunRecord[]>()
const details = new Map<string, DetailDoc>()
const health = new Map<string, { stall: boolean; cap: boolean }>()
const logPaths = new Map<string, string>()
let lastStatus = 0
let lastDetail = 0
let lastExtra = 0
let lastProjection = 0
let lastFleet = 0
let busy = false
/** Set when every place of MAC-B5 exited 127: the engine is marked not installed and no engine verb is run (MDS-B6). */
let notFound = false

/** The place after `current` in the order of MAC-B5; the engine home is asked for once, only when PATH is the place that failed. */
async function nextPlace($: $, current: string): Promise<string | null> {
  if (!homeKnown() && enginePlaces().at(-1) === current) {
    learnHome(await run($, HOME_ARGV).catch(() => null))
  }
  const places = enginePlaces()
  const at = places.indexOf(current)
  return at >= 0 && at + 1 < places.length ? places[at + 1]! : null
}

/**
 * Runs a read-only engine verb, the constant `ps` listing or the engine-home probe; refuses any other argv (contract M1).
 * An engine verb that exits 127 is run again through the next place of MAC-B5; the first place that does not exit 127
 * stays the program of every later verb.
 */
async function run($: $, argv: readonly string[]): Promise<string | null> {
  if (!isReadOnly(argv)) throw new Error(`refused: ${argv.join(' ')}`)
  const isEngineVerb = argv[0] !== PS_ARGV[0] && argv[0] !== HOME_ARGV[0]
  if (isEngineVerb && notFound) return null // every place exited 127: no engine verb is run again (MDS-B6)
  for (;;) {
    const out = await $.process.run(argv, { timeoutMs: 20_000 })
    if (out.exitCode === 127 && isEngineVerb) {
      const place = await nextPlace($, argv[0]!)
      if (place === null || !useProgram(place)) {
        notFound = true
        const looked = lookedAt()
        await update($, engine, e => ({ ...e, installed: false, error: 'tempergraph not found', looked }))
        return null
      }
      argv = [place, ...argv.slice(1)]
      if (!isReadOnly(argv)) throw new Error(`refused: ${argv.join(' ')}`)
      continue
    }
    if (out.exitCode !== 0) {
      if (isEngineVerb) {
        const now = await $.clock.now()
        await update($, engine, e => ({ ...e, staleSince: e.staleSince ?? now, error: `exit ${out.exitCode}` }))
      }
      return null
    }
    return out.stdout
  }
}

async function verb<T>($: $, argv: readonly string[]): Promise<T | null> {
  const text = await run($, argv)
  if (text === null) return null
  try {
    return JSON.parse(text) as T
  } catch {
    return null
  }
}

/** Fills the prompt for the person to send (MAC §2.1, §4); a draft already there is kept. */
async function fill($: $, f: Fill): Promise<void> {
  const box = await $.prompt.read().catch(() => null)
  const draft = (box?.text ?? '').trim().length > 0
  const done = await $.prompt.fill({ text: draft ? `\n${f.text}` : f.text, mode: draft ? 'append' : 'replace' })
    .catch(() => null)
  if (!done?.isFilled) {
    await $.ui.copy({ text: f.text }).catch(() => undefined)
    $.ui.toast('No prompt to fill here: the command is copied instead.')
  }
}

async function copy($: $, text: string): Promise<void> {
  const r = await $.ui.copy({ text }).catch(() => null)
  $.ui.toast(r?.isCopied ? 'Copied.' : 'Copying is not available here.')
}

async function lastAlerted($: $, tid: string): Promise<number> {
  return Number((await $.store.get(`alerted:${tid}`)) ?? 0)
}

async function raise($: $, alerts: ReturnType<typeof alertsFrom>): Promise<void> {
  for (const a of alerts) {
    $.ui.toast(a.toast)
    if (a.notify) {
      // MBA-B4: a channel that is off resolves not sent; nothing is retried.
      await $.ui.notify(a.body, { title: a.title, key: `${a.threadId}:${a.seq}` }).catch(() => undefined)
    }
  }
  const top = new Map<string, number>()
  for (const a of alerts) top.set(a.threadId, Math.max(top.get(a.threadId) ?? 0, a.seq))
  for (const [tid, seq] of top) await $.store.set(`alerted:${tid}`, seq)
}

/** Reads what each live run's log added since the last read (stat first, read second: MADR `poll-files-and-read-only-verbs`). */
async function tailLog($: $, tid: string, path: string, label: string): Promise<boolean> {
  const st = await $.fs.stat(path).catch(() => null)
  if (!st) return false
  const held = tails.get(tid) ?? { offset: 0, size: 0 }
  if (st.size === held.size) return false
  const { offset, length } = nextRead(held, st.size)
  const text = length > 0 ? await $.fs.read(path, { offset, length }) : ''
  const parsed = parseChunk(String(text), offset)
  tails.set(tid, { offset: parsed.offset, size: st.size })
  records.set(tid, keepTail(records.get(tid) ?? [], parsed.records))
  await raise($, alertsFrom(tid, label, parsed.records, await lastAlerted($, tid),
    { finished: settings.alertsFinished }))
  return parsed.records.length > 0
}

/** The last `bytes` of a file, and whether the read began past its start (so its first line may be cut). */
async function readTail($: $, path: string, bytes: number): Promise<{ text: string; cut: boolean } | null> {
  const st = await $.fs.stat(path).catch(() => null)
  if (!st) return null
  const offset = Math.max(0, st.size - bytes)
  const text = await $.fs.read(path, { offset, length: st.size - offset }).catch(() => null)
  return text === null ? null : { text: String(text), cut: offset > 0 }
}

/** What an open session tab needs beyond the detail document: the journal, `ps`, or log tails (MDD §2.4). */
async function readExtra($: $, v: MonitorView, d: DetailDoc | undefined): Promise<void> {
  if (v.level !== 'session' || !d || !v.unit || !v.session) return
  const tab = v.tab ?? 'now'
  if (tab !== 'calls' && tab !== 'processes' && tab !== 'log') return
  const att = v.visit != null ? findAttempt(d, v.unit, v.visit, v.attempt ?? null) : undefined
  const s = [...(att?.step?.sessions ?? []), ...(att?.judge?.sessions ?? [])].find(x => x.session_key === v.session)
  if (!s) return
  let lines: string[] = []
  let note: string | null = null
  if (tab === 'calls') {
    const got = s.activity_path ? await readTail($, s.activity_path, 1024 * 1024) : null
    if (got) lines = callsFrom(got.text, settings.showInputs).slice(-2000).map(callText)
    else note = 'No activity journal for this session.'
  } else if (tab === 'processes') {
    const pgid = s.live?.pgid
    if (pgid == null) note = s.live ? 'The session has not reported its process group.' : 'Not shown: the session has ended.'
    else {
      const ps = await run($, PS_ARGV).catch(() => null)
      if (ps === null) note = 'Not available on this system.'
      else {
        lines = processTree(ps, pgid).map(procText)
        if (!lines.length) note = 'ended'
      }
    }
  } else {
    if (!settings.showLogTails) note = 'Log tails are hidden by the show_log_tails setting.'
    else {
      const raw = s.transcript?.engine
      const dir = raw ? raw.slice(0, raw.lastIndexOf('/')) : null
      for (const [name, path] of [['raw.jsonl', raw], ['stderr.log', dir ? `${dir}/stderr.log` : null]] as const) {
        if (!path) continue
        const got = await readTail($, path, LOG_TAIL_BYTES)
        lines.push(`— ${name}${got ? '' : ': not found (pruned, or never written)'}`)
        if (got) lines.push(...tailLines(got.text, got.cut, 30))
      }
    }
  }
  await update($, extra, () => ({ key: s.session_key, tab, lines, note }))
}

async function refreshStatus($: $, now: number): Promise<void> {
  const doc = await verb<StatusDoc>($, statusArgv(settings.machine))
  if (!doc) return
  if (!isReadable(doc, 'status')) {
    await update($, engine, e => ({ ...e, error: 'update the monitor: newer status document' }))
    return
  }
  await update($, engine, e => ({ ...e, staleSince: null, error: null }))
  const out: RunSummary[] = []
  const others: MonitorOther[] = []
  const ended: Record<string, number> = {}
  const here = doc.roots?.[0]?.path
  for (const row of doc.threads) {
    if (here && row.state_root && row.state_root !== here) {
      // another repository on this machine: listed with a card, never drilled into or acted on from here
      const s = summarise(row, undefined, now)
      const repo = repoName(row.state_root)
      others.push({ key: `other:${row.state_root}|${row.thread_id}`, repo, text: listRow(s), card: [
        `${row.thread_id} in ${repo}`, `state ${row.state}${s.unit ? ` at ${s.unit}` : ''}`,
        ...(row.pending_gates ?? []).map(g => `waits at ${g.unit}: ${g.resume}`),
        `Open Claude Code in ${row.state_root.replace(/[\\/]\.tempergraph$/, '')} to follow or answer this run.`] })
      continue
    }
    if (row.log_path) logPaths.set(row.thread_id, row.log_path)
    const live = row.alive || row.state === 'paused'
    let d = details.get(row.thread_id)
    if (live && (!d || d.run.last_seq !== (records.get(row.thread_id)?.at(-1)?.seq ?? d.run.last_seq))) {
      const fresh = await verb<DetailDoc>($, detailArgv(row.thread_id))
      if (fresh && isReadable(fresh, 'detail')) {
        d = fresh
        details.set(row.thread_id, fresh)
      }
    }
    if (!live && row.log_path && !tails.has(row.thread_id)) {
      // first sight of an ended run: read its log once, so alerts start after what is already there
      const st = await $.fs.stat(row.log_path).catch(() => null)
      if (st) tails.set(row.thread_id, { offset: st.size, size: st.size })
    }
    const s = summarise(row, d, now)
    out.push(s)
    const exit = (records.get(row.thread_id) ?? []).filter(r => r.kind === 'run_exit').at(-1)
    if (exit && !row.alive) ended[row.thread_id] = (now - Date.parse(exit.ts)) / 1000
  }
  await update($, runs, () => out)
  await update($, fleet, f => ({ ...f, others, missing: missingRoots(doc.roots) }))
  await update($, endedAgo, () => ended)
  $.ui.status(statusLine(out))
}

async function tick($: $): Promise<void> {
  if (busy) return
  busy = true
  try {
    const now = await $.clock.now()
    const eng = await read($, engine)
    if (!eng.installed) return
    const shown = await read($, view)
    const held = await read($, runs)
    const anyAlive = held.some(r => r.alive || r.mark === '⏸')
    let grown = false
    for (const r of held.filter(x => x.alive)) {
      const path = logPaths.get(r.threadId)
      if (path) grown = (await tailLog($, r.threadId, path, r.label)) || grown
    }
    if (grown || now - lastStatus >= statusEvery(anyAlive, shown.level !== 'runs')) {
      lastStatus = now
      await refreshStatus($, now)
    }
    const open = shown.thread
    if (open && (grown || now - lastDetail >= RATES.detail * (anyAlive ? 1 : 15))) {
      lastDetail = now
      const d = await verb<DetailDoc>($, detailArgv(open))
      if (d && isReadable(d, 'detail')) {
        details.set(open, d)
        await update($, detail, () => d as unknown)
        const label = (await read($, runs)).find(r => r.threadId === open)?.label ?? open
        const was = health.get(open) ?? { stall: false, cap: false }
        await raise($, healthAlerts(open, label, d, was))
        health.set(open, { stall: !!d.health?.suspect_stall, cap: (d.health?.cap_eta_min ?? 99) < 10 })
      }
    }
    if (now - lastProjection >= PROJECTION_EVERY_MS) {
      lastProjection = now
      const proj = await verb<ProjectionDoc>($, projectionArgv())
      await update($, fleet, f => ({ ...f, projection: proj as unknown }))
    }
    const fleetOpen = shown.level === 'fleet' || (shown.level === 'card' && !shown.card?.startsWith('other:'))
    if ((fleetOpen || settings.alertsFleet) && now - lastFleet >= FLEET_EVERY_MS) {
      lastFleet = now
      await refreshFleet($, now)
    }
    if (shown.level === 'session' && now - lastExtra >= RATES.detail) {
      lastExtra = now
      await readExtra($, shown, open ? details.get(open) : undefined)
    }
  } finally {
    busy = false
  }
}

/** The fleet tab's documents (MCF §2.2): live heartbeats, and the month by machine and by workflow. */
async function refreshFleet($: $, now: number): Promise<void> {
  const live = settings.fleetSink ? await verb<LiveDoc>($, fleetArgv('live', settings.fleetSink)) : null
  const month = await verb<StatsDoc>($, fleetArgv('machine', settings.fleetSink))
  const byWorkflow = await verb<StatsDoc>($, fleetArgv('workflow', settings.fleetSink))
  await update($, fleet, f => ({ ...f, live: (live ?? f.live) as unknown, month: (month ?? f.month) as unknown,
    byWorkflow: (byWorkflow ?? f.byWorkflow) as unknown, readAt: now,
    error: settings.fleetSink && !live ? 'the fleet copy could not be read; showing the last copy' : null }))
  if (settings.alertsFleet && live) {
    const seen = new Set(((await $.store.get('fleetAlerted').catch(() => null)) as string[] | null) ?? [])
    const fresh = fleetAlerts(live, seen)
    for (const a of fresh) {
      $.ui.toast(a.toast)
      seen.add(a.key)
    }
    if (fresh.length) await $.store.set('fleetAlerted', [...seen].slice(-200))
  }
}

async function openPane($: $, to: MonitorView): Promise<void> {
  await update($, view, () => to)
  await $.ui.open({ id: PANE, title: 'tempergraph' })
}

async function togglePin($: $, tid: string): Promise<void> {
  const next = await update($, prefs, p => ({ ...p,
    pinned: p.pinned.includes(tid) ? p.pinned.filter(x => x !== tid) : [...p.pinned, tid] }))
  await $.store.set('pinned', next.pinned)
}

function todaySeconds(now: number): number {
  const d = new Date(now)
  return d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds()
}

export const register: Register = (on, options) => {
  settings = readSettings(options)
  for (const m of [tails, records, details, health, logPaths]) m.clear()
  lastStatus = lastDetail = lastExtra = lastProjection = lastFleet = 0
  busy = false
  notFound = false

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    if (!e.isInteractive) return started // headless (`-p`, SDK): no timers, no command, no tool (MAC §2.2, M3)
    await $.command.register({ name: 'tg', description: 'Open the tempergraph run monitor' })
    const pinned = await $.store.get('pinned').catch(() => null)
    if (Array.isArray(pinned)) await update($, prefs, p => ({ ...p, pinned: pinned.map(String) }))
    // Runs already in the state root alert only for what comes after this session started (MBA-B2).
    $.clock.every(RATES.change, () => tick($))
    void tick($)
    return started
  })

  on('command.run', { command: 'tg' }, async ($, e) => {
    const wanted = e.args.trim()
    const match = wanted ? (await read($, runs)).find(r => r.label === wanted || r.threadId === wanted) : undefined
    await openPane($, match ? { level: 'run', thread: match.threadId } : { level: 'runs' })
    return { text: match ? `Monitor opened on ${match.label}.` : 'Monitor opened.' }
  })

  // -- band (MBA §2.2) -------------------------------------------------------------------------------------------
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const eng = await read($, engine)
    const { Box, Button, Text } = $.ui.resolve(e)
    if (!eng.installed) return <Box><Text dimColor>tempergraph not found</Text></Box>
    const list = await read($, runs)
    const stale = eng.staleSince != null && (await $.clock.now()) - eng.staleSince > STALE_AFTER_MS
    const row = bandRow(list, e.props.bodyColumns, await read($, endedAgo), stale)
    if (row === null) return next(e)
    const first = runList(list)[0]
    return (
      <Box>
        <Button key="tg-band" label={row} plain
          onPress={() => openPane($, first ? { level: 'run', thread: first.threadId } : { level: 'runs' })} />
      </Box>
    )
  })

  // -- pane (MRV, MDD, MCF §2.1, MAC §2.1) --------------------------------------------------------------------------
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const v = await read($, view)
    const eng = await read($, engine)
    const list = await read($, runs)
    const pr = await read($, prefs)
    const d = (await read($, detail)) as DetailDoc | null
    const go = (to: MonitorView) => () => update($, view, () => to)
    const back = (): MonitorView => {
      if (v.level === 'session') return { ...v, level: 'attempt', session: undefined, tab: undefined }
      if (v.level === 'attempt') return { level: 'unit', thread: v.thread, unit: v.unit }
      if (v.level === 'unit' || v.level === 'pause' || v.level === 'cost') return { level: 'run', thread: v.thread }
      if (v.level === 'card' && !v.card?.startsWith('other:')) return { level: 'fleet' }
      return { level: 'runs' }
    }
    const label = list.find(r => r.threadId === v.thread)?.label
    const place = v.level === 'pause' ? 'pause' : v.level === 'cost' ? 'cost' : v.level === 'fleet' ? 'fleet'
      : v.level === 'card' ? (v.card?.startsWith('other:') ? 'other repository' : 'fleet › card') : undefined
    const crumbs = ['Runs', label, place, v.unit, v.attempt != null && v.level !== 'unit' ? `attempt ${v.attempt}` : undefined,
      v.session].filter(Boolean).join(' › ')
    const header = (
      <Box flexDirection="column">
        <Text bold>{crumbs}</Text>
        <Text dimColor>{eng.staleSince ? 'stale' : 'live'}{eng.error ? ` · ${eng.error}` : ''}</Text>
      </Box>
    )
    const footer = v.level === 'runs' ? null : (
      <Box><Button key="back" label="Back" hotkey="b" onPress={go(back())} /></Box>
    )
    const fillButton = (f: Fill, key: string) => (
      <Button key={key} label={f.label} hotkey={f.hotkey} onPress={() => fill($, f)} />
    )

    if (!eng.installed) {
      return <Box flexDirection="column"><Text>tempergraph is not installed here.</Text>
        {eng.looked.map(place => <Text dimColor>{`looked at ${place}`}</Text>)}
        <Text dimColor>The tempergraph plugin's install skill sets it up.</Text></Box>
    }

    const fl = await read($, fleet)

    if (v.level === 'fleet') {
      const now = await $.clock.now()
      const month = fl.month as StatsDoc | null
      const rows = fleetRows(fl.live as LiveDoc | null)
      return (
        <Box flexDirection="column">
          {header}
          {settings.fleetSink
            ? <Text dimColor>{`sink ${settings.fleetSink} · ${syncedText(month, now)}${fl.error ? ` · ${fl.error}` : ''}`}</Text>
            : <Box flexDirection="column">
                <Text>No fleet sink is set for the monitor.</Text>
                <Text dimColor>List a directory sink in ~/.tempergraph/config/sinks.json for the engine, then set the monitor's fleet_sink to its name. Below: this machine's month from local stats.</Text>
              </Box>}
          {fl.readAt === null && <Text dimColor>Reading…</Text>}
          {settings.fleetSink && <Text bold>Live now</Text>}
          {settings.fleetSink && rows.length === 0 && fl.readAt !== null && <Text dimColor>Nothing is running or waiting on any machine.</Text>}
          {rows.map(r => (
            <Button key={`fleet:${r.key}`} plain label={r.text}
              onPress={go(r.mine && r.threadId && list.some(x => x.threadId === r.threadId)
                ? { level: 'run', thread: r.threadId } : { level: 'card', card: r.key })} />
          ))}
          <Text bold>This month by machine</Text>
          {monthRows(month).map(line => <Text>{`  ${line}`}</Text>)}
          <Text bold>This month by workflow</Text>
          {monthRows(fl.byWorkflow as StatsDoc | null).map(line => <Text>{`  ${line}`}</Text>)}
          {footer}
        </Box>
      )
    }

    if (v.level === 'card') {
      const lines = v.card?.startsWith('other:') ? fl.others.find(o => o.key === v.card)?.card
        : fleetRows(fl.live as LiveDoc | null).find(r => r.key === v.card)?.card
      return (
        <Box flexDirection="column">
          {header}
          {(lines ?? ['That run is no longer listed.']).map(line => <Text>{line}</Text>)}
          {footer}
        </Box>
      )
    }

    if (v.level === 'runs' || !v.thread) {
      const now = await $.clock.now()
      const sorted = shownRuns(list, pr.filter as Filter, pr.pinned, await read($, endedAgo), todaySeconds(now))
      return (
        <Box flexDirection="column">
          {header}
          <Box>
            <Button key="filter" label={`filter: ${pr.filter}`} hotkey="f"
              onPress={() => update($, prefs, p => ({ ...p, filter: nextFilter(p.filter as Filter) }))} />
            <Button key="fleet" label="fleet" hotkey="m" onPress={async () => {
              lastFleet = 0
              await update($, view, () => ({ level: 'fleet' }))
            }} />
          </Box>
          {sorted.length === 0 && <Text dimColor>{list.length ? `No run is ${pr.filter}.` : 'No tempergraph runs in this repository.'}</Text>}
          {sorted.map(r => (
            <Box>
              <Button key={`run:${r.threadId}`} label={`${pr.pinned.includes(r.threadId) ? '📌 ' : ''}${listRow(r)}`} plain
                onPress={go({ level: 'run', thread: r.threadId })} />
              <Button key={`pin:${r.threadId}`} label={pr.pinned.includes(r.threadId) ? 'unpin' : 'pin'} plain
                onPress={() => togglePin($, r.threadId)} />
            </Box>
          ))}
          {fl.others.length > 0 && <Text bold>Other repositories on this machine</Text>}
          {fl.others.map(o => (
            <Button key={o.key} plain label={`${o.repo}  ${o.text}`} onPress={go({ level: 'card', card: o.key })} />
          ))}
          {fl.missing.map(line => <Text dimColor>{line}</Text>)}
        </Box>
      )
    }

    if (!d || d.run.thread_id !== v.thread) {
      return <Box flexDirection="column">{header}<Text dimColor>Reading the run…</Text>{footer}</Box>
    }

    if (v.level === 'run') {
      const rows = unitRows(d)
      const touches = touchStrip(d)
      const live = d.run.alive || d.run.state === 'running'
      return (
        <Box flexDirection="column">
          {header}
          {d.plan_stale && <Text color="yellow">plan changed since this run started</Text>}
          {(touches || levelText(d)) && <Text dimColor>{[levelText(d) ? `level ${levelText(d)}` : '', touches ? `touches ${touches}` : ''].filter(Boolean).join(' · ')}</Text>}
          {narrator(d).map(line => <Text dimColor>{line}</Text>)}
          {rows.map(r => (
            <Box flexDirection="column">
              <Button key={`unit:${r.name}`} label={unitRowText(r)} plain dimColor={r.dim}
                onPress={go({ level: 'unit', thread: v.thread, unit: r.name })} />
              {r.backLines.map(line => <Text dimColor>{`   ${line}`}</Text>)}
            </Box>
          ))}
          {d.truncated?.length ? <Text dimColor>{`summary only for ${d.truncated.join(', ')}: open the unit for its attempts`}</Text> : null}
          {d.pause && <Text color="yellow">{`⏸ ${d.pause.unit} waits: ${d.pause.question ?? d.pause.kind}`}</Text>}
          <Box>
            {d.pause && <Button key="gate" label="pause" hotkey="g" onPress={go({ level: 'pause', thread: v.thread })} />}
            <Button key="cost" label="cost" hotkey="c" onPress={go({ level: 'cost', thread: v.thread })} />
            {live && fillButton(stopFills(d.run)[0]!, 'stop')}
            {live && fillButton(stopFills(d.run)[1]!, 'stop-now')}
          </Box>
          {footer}
        </Box>
      )
    }

    if (v.level === 'pause') {
      const p = d.pause
      if (!p) return <Box flexDirection="column">{header}<Text dimColor>The run is not waiting for a person.</Text>{footer}</Box>
      const driver = driverFill(d)
      return (
        <Box flexDirection="column">
          {header}
          <Text>{`${p.unit} · ${p.kind ?? 'pause'} · waiting ${duration(p.waiting_s)}`}</Text>
          {p.question && <Text>{p.question}</Text>}
          {(p.artifacts ?? []).map(a => a.path
            ? <Button key={`art:${a.key}`} plain label={`${a.key}: ${a.path}`} onPress={() => copy($, a.path!)} />
            : <Text dimColor>{`${a.key}: a value, no file`}</Text>)}
          <Text dimColor>Each decision fills the prompt; nothing runs until you send it.</Text>
          <Box flexDirection="column">{resumeFills(p).map((f, i) => fillButton(f, `decide:${i}`))}</Box>
          {driver && fillButton(driver, 'driver')}
          {footer}
        </Box>
      )
    }

    if (v.level === 'cost') {
      const c = costTab(d)
      return (
        <Box flexDirection="column">
          {header}
          <Text bold>{`total ${c.total} · ${c.completeness}`}</Text>
          <Text dimColor>by unit (first visit, then each repeat and its cause)</Text>
          {c.units.map(u => <Text>{`  ${u.name}  ${u.first}${u.share != null ? `  ${Math.round(u.share * 100)}%` : ''}${u.repeats.map(r => `  +${r.cause} ${r.cost}`).join('')}`}</Text>)}
          <Text dimColor>by kind</Text>
          {c.kinds.map(k => <Text>{`  ${k.kind}  ${k.cost}`}</Text>)}
          <Text dimColor>by executor and model</Text>
          {c.executors.map(x => <Text>{`  ${x.key}  ${x.cost}  ${x.tokens}`}</Text>)}
          <Text>{`budget ${c.budget}`}</Text>
          <Text dimColor>{`supervision ${c.supervision}`}</Text>
          <Text dimColor>{`projection ${projectionText(fl.projection as ProjectionDoc | null, d.run.workflow)}`}</Text>
          {footer}
        </Box>
      )
    }

    if (v.level === 'unit' && v.unit) {
      const plan = d.plan.find(p => p.name === v.unit)
      const counters = Object.entries(d.budgets?.counters ?? {}).filter(([k]) => k.startsWith(`${v.unit}.`))
        .map(([k, c]) => `${k.slice(v.unit!.length + 1)} ${c.limit != null && c.used != null ? c.limit - c.used : '?'} left`)
      return (
        <Box flexDirection="column">
          {header}
          <Text>{`${v.unit} · ${plan?.kind ?? 'step'} · ${plan?.executor ?? '–'} / judge ${plan?.judge_executor ?? '–'}${plan?.alias ? ` · ${plan.alias}` : ''}`}</Text>
          {counters.length > 0 && <Text dimColor>{`gate budget: ${counters.join(', ')}`}</Text>}
          {attemptRows(d, v.unit).map(a => (
            <Button key={`att:${a.visit}:${a.attempt}`} plain
              label={`v${a.visit}${a.from ? ` (${a.from})` : ''} a${a.attempt}  ${a.strip}  check ${a.check}  judge ${a.judge}  ${a.gate}${a.cause ? `  ${a.cause}` : ''}  ${a.time}`}
              onPress={go({ level: 'attempt', thread: v.thread, unit: v.unit, visit: a.visit, attempt: a.attempt })} />
          ))}
          {footer}
        </Box>
      )
    }

    const att = v.unit && v.visit != null ? findAttempt(d, v.unit, v.visit, v.attempt ?? null) : undefined
    if (!att) return <Box flexDirection="column">{header}<Text dimColor>That attempt is not in the document.</Text>{footer}</Box>
    const sessions: Session[] = [...(att.step?.sessions ?? []), ...(att.judge?.sessions ?? [])]

    if (v.level === 'attempt') {
      // MDD §2.2: open on the node in flight, else on the node that decided the route
      const node = inFlight(nodeStrip(att, d.plan.find(p => p.name === v.unit)?.gated ?? true, att.ended_at == null))
      const tab = v.tab ?? (node === 'S' ? 'step' : node === 'C' ? 'check' : node === 'J' ? 'judge'
        : att.judge?.blockers?.length ? 'judge' : 'gate')
      const tabs = ['step', 'check', 'judge', 'gate'].map((t, i) => (
        <Button key={`tab:${t}`} label={t === tab ? `[${t}]` : t} hotkey={String(i + 1)} plain onPress={go({ ...v, tab: t })} />
      ))
      const j = att.judge
      const sessionButtons = (list: Session[]) => list.map(s => (
        <Button key={`ses:${s.session_key}`} plain label={`session ${s.session_key}${s.live ? ' (live)' : ''}`}
          onPress={go({ ...v, level: 'session', session: s.session_key, tab: 'now' })} />))
      const body = tab === 'step' ? (
        <Box flexDirection="column">
          {sessionButtons(att.step?.sessions ?? [])}
          {(att.scripts ?? []).map(sc => <Text dimColor>{`script ${sc.name} (${sc.phase ?? 'step'}) exit ${sc.exit_code ?? '–'}`}</Text>)}
        </Box>
      ) : tab === 'check' ? (
        <Box flexDirection="column">
          <Text>{`check ${att.check?.result ?? '–'}${att.check?.environmental ? ' (environmental)' : ''} · ${duration(att.check?.duration_s)}`}</Text>
          {att.check?.evidence && <Text dimColor>{att.check.evidence}</Text>}
        </Box>
      ) : tab === 'judge' ? (
        <Box flexDirection="column">
          {j?.criteria ? <Text>{`judge ${j.met}/${j.total}${j.confidence != null ? ` · confidence ${j.confidence} (${j.confidence_source ?? '?'})` : ''}${j.gap ? ' · gap' : ''}`}</Text>
            : <Text dimColor>No judgement in this attempt.</Text>}
          {(j?.criteria ?? []).map(c => <Text>{`  ${c.n}. ${c.id ?? ''} ${c.status}`}</Text>)}
          {(j?.blockers ?? []).map(b => <Text dimColor>{`  ${b.id}: ${b.evidence ?? 'no evidence line'}${b.fix ? ` → ${b.fix}` : ''}`}</Text>)}
          {sessionButtons(j?.sessions ?? [])}
        </Box>
      ) : (
        <Box flexDirection="column">
          <Text>{`gate ${att.gate?.verdict ?? '–'}${att.gate?.route_target ? ` → ${att.gate.route_target}` : ''}`}</Text>
          <Text dimColor>{`guard ${att.gate?.guard ?? j?.guard ?? '–'}${att.repeat_cause ? ` · repeat cause ${att.repeat_cause}` : ''}`}</Text>
        </Box>
      )
      return <Box flexDirection="column">{header}<Box>{tabs}</Box>{body}{footer}</Box>
    }

    const s = sessions.find(x => x.session_key === v.session)
    if (!s) return <Box flexDirection="column">{header}<Text dimColor>That session is not in the document.</Text>{footer}</Box>
    const tab = v.tab ?? 'now'
    const tabs = ['now', 'calls', 'processes', 'log', 'info'].map((t, i) => (
      <Button key={`stab:${t}`} label={t === tab ? `[${t}]` : t} hotkey={String(i + 1)} plain onPress={async () => {
        await update($, view, () => ({ ...v, tab: t }))
        await readExtra($, { ...v, tab: t }, d)
      }} />
    ))
    const ex = await read($, extra)
    const mine = ex.key === s.session_key && ex.tab === tab
    const ask = askFill(s, v.unit ?? '', v.attempt ?? null, att.gate?.verdict)
    const body = tab === 'now' ? sessionNow(s, settings.showInputs).map(line => <Text>{line}</Text>)
      : tab === 'info' ? sessionInfo(s).map(line => <Text dimColor>{line}</Text>)
      : !mine ? [<Text dimColor>Reading…</Text>]
      : [...(ex.note ? [<Text dimColor>{ex.note}</Text>] : []), ...ex.lines.map(line => <Text>{line}</Text>)]
    return (
      <Box flexDirection="column">
        {header}
        <Box>{tabs}</Box>
        {body}
        <Box>
          {ask && fillButton(ask, 'ask')}
          {s.transcript?.engine && <Button key="copy-path" label="copy transcript path" onPress={() => copy($, s.transcript!.engine!)} />}
        </Box>
        {footer}
      </Box>
    )
  })
}
