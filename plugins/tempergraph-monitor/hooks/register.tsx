// tempergraph-monitor: the read-only parts (MBA band, status line and alerts; MRV run list and run view;
// MDD drill-down). Reads engine documents through read-only verbs and file reads on its own timers,
// never inside a drawing (MDS §1). Actions that fill the prompt (MAC) and the cost and fleet views
// (MCF) are not in this module yet.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { MonitorEngine, MonitorRun, MonitorView } from '../types'
import type { DetailDoc, RunRecord, Session, StatusDoc } from './lib/engine'
import { isReadable } from './lib/engine'
import {
  alertsFrom, attemptRows, bandRow, findAttempt, healthAlerts, listRow, narrator, runList, sessionInfo, sessionNow,
  statusLine, stripText, summarise, touchStrip, unitRows, unitRowText,
} from './lib/model'
import type { RunSummary } from './lib/model'
import { detailArgv, isReadOnly, keepTail, nextRead, parseChunk, RATES, statusArgv, statusEvery } from './lib/sources'
import type { TailState } from './lib/sources'

const PANE = 'tempergraph'
const SHAPE = 'm1'

const runs = atom({ plugin: 'tempergraph-monitor', key: 'runs' } as const, [] as MonitorRun[], { shape: SHAPE })
const view = atom({ plugin: 'tempergraph-monitor', key: 'view' } as const, { level: 'runs' } as MonitorView, { shape: SHAPE })
const detail = atom({ plugin: 'tempergraph-monitor', key: 'detail' } as const, null as unknown, { shape: SHAPE })
const engine = atom({ plugin: 'tempergraph-monitor', key: 'engine' } as const,
  { installed: true, staleSince: null, error: null } as MonitorEngine, { shape: SHAPE })
const endedAgo = atom({ plugin: 'tempergraph-monitor', key: 'endedAgo' } as const, {} as Record<string, number>, { shape: SHAPE })

type $ = EngineInterface

/** Runs a read-only engine verb and parses its JSON; refuses any other argv (contract M1). */
async function verb<T>($: $, argv: readonly string[]): Promise<T | null> {
  if (!isReadOnly(argv)) throw new Error(`refused: ${argv.join(' ')}`)
  const out = await $.process.run(argv, { timeoutMs: 20_000 })
  if (out.exitCode === 127) {
    await update($, engine, e => ({ ...e, installed: false, error: 'tempergraph not found' }))
    return null
  }
  if (out.exitCode !== 0) {
    const now = await $.clock.now()
    await update($, engine, e => ({ ...e, staleSince: e.staleSince ?? now, error: `exit ${out.exitCode}` }))
    return null
  }
  try {
    return JSON.parse(out.stdout) as T
  } catch {
    return null
  }
}

// Module variables start over at a reload; what must survive is in $.state and $.store.
const tails = new Map<string, TailState>()
const records = new Map<string, RunRecord[]>()
const details = new Map<string, DetailDoc>()
const health = new Map<string, { stall: boolean; cap: boolean }>()
let lastStatus = 0
let lastDetail = 0
let busy = false

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

/** Reads what each live run's log added since the last read (stat first, read second: MADR-0002). */
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
  await raise($, alertsFrom(tid, label, parsed.records, await lastAlerted($, tid)))
  return parsed.records.length > 0
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
      const row = (await read($, runs)).find(x => x.threadId === r.threadId)
      const path = logPaths.get(r.threadId)
      if (row && path) grown = (await tailLog($, r.threadId, path, r.label)) || grown
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
  } finally {
    busy = false
  }
}

const logPaths = new Map<string, string>()

async function refreshStatus($: $, now: number): Promise<void> {
  const doc = await verb<StatusDoc>($, statusArgv())
  if (!doc) return
  if (!isReadable(doc, 'status')) {
    await update($, engine, e => ({ ...e, error: 'update the monitor: newer status document' }))
    return
  }
  await update($, engine, e => ({ ...e, staleSince: null, error: null }))
  const out: RunSummary[] = []
  const ended: Record<string, number> = {}
  for (const row of doc.threads) {
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
  await update($, endedAgo, () => ended)
  $.ui.status(statusLine(out))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    if (!e.isInteractive) return started // headless (`-p`, SDK): no timers, no tool, no surfaces (MAC §2.2)
    await $.command.register({ name: 'tg', description: 'Open the tempergraph run monitor' })
    // Runs already in the state root alert only for what comes after this session started (MBA-B2).
    $.clock.every(RATES.change, () => tick($))
    void tick($)
    return started
  })

  on('command.run', { command: 'tg' }, async ($, e) => {
    const wanted = e.args.trim()
    const match = wanted ? (await read($, runs)).find(r => r.label === wanted || r.threadId === wanted) : undefined
    await update($, view, () => (match ? { level: 'run', thread: match.threadId } : { level: 'runs' }))
    await $.ui.open({ id: PANE, title: 'tempergraph · repo' })
    return { text: match ? `Monitor opened on ${match.label}.` : 'Monitor opened.' }
  })

  // -- band (MBA §2.2) -------------------------------------------------------------------------------------------
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const eng = await read($, engine)
    const { Box, Button, Text } = $.ui.resolve(e)
    if (!eng.installed) return <Box><Text dimColor>tempergraph not found</Text></Box>
    const list = await read($, runs)
    const row = bandRow(list, e.props.bodyColumns, await read($, endedAgo))
    if (row === null) return next(e)
    const first = runList(list)[0]
    return (
      <Box>
        <Button key="tg-band" label={row} plain onPress={async () => {
          await update($, view, () => (first ? { level: 'run', thread: first.threadId } : { level: 'runs' }))
          await $.ui.open({ id: PANE, title: 'tempergraph · repo' })
        }} />
      </Box>
    )
  })

  // -- pane (MRV, MDD) ----------------------------------------------------------------------------------------------
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const v = await read($, view)
    const eng = await read($, engine)
    const list = await read($, runs)
    const d = (await read($, detail)) as DetailDoc | null
    const go = (to: MonitorView) => () => update($, view, () => to)
    const back = (): MonitorView => {
      if (v.level === 'session') return { ...v, level: 'attempt', session: undefined }
      if (v.level === 'attempt') return { level: 'unit', thread: v.thread, unit: v.unit }
      if (v.level === 'unit') return { level: 'run', thread: v.thread }
      return { level: 'runs' }
    }
    const crumbs = ['Runs', list.find(r => r.threadId === v.thread)?.label, v.unit,
      v.attempt != null && v.level !== 'unit' ? `attempt ${v.attempt}` : undefined, v.session].filter(Boolean).join(' › ')
    const fresh = eng.staleSince ? 'stale' : 'live'
    const header = (
      <Box flexDirection="column">
        <Text bold>{crumbs}</Text>
        <Text dimColor>{fresh}{eng.error ? ` · ${eng.error}` : ''}</Text>
      </Box>
    )
    const footer = v.level === 'runs' ? null : (
      <Box><Button key="back" label="Back" hotkey="b" onPress={go(back())} /></Box>
    )

    if (!eng.installed) {
      return <Box flexDirection="column"><Text>tempergraph is not installed here.</Text>
        <Text dimColor>The tempergraph plugin's install skill sets it up.</Text></Box>
    }

    if (v.level === 'runs' || !v.thread) {
      const sorted = runList(list)
      return (
        <Box flexDirection="column">
          {header}
          {sorted.length === 0 && <Text dimColor>No tempergraph runs in this repository.</Text>}
          {sorted.map(r => <Button key={`run:${r.threadId}`} label={listRow(r)} plain
            onPress={go({ level: 'run', thread: r.threadId })} />)}
        </Box>
      )
    }

    if (!d || d.run.thread_id !== v.thread) {
      return <Box flexDirection="column">{header}<Text dimColor>Reading the run…</Text>{footer}</Box>
    }

    if (v.level === 'run') {
      const rows = unitRows(d)
      const touches = touchStrip(d)
      return (
        <Box flexDirection="column">
          {header}
          {d.plan_stale && <Text color="yellow">plan changed since this run started</Text>}
          {touches && <Text dimColor>touches {touches}</Text>}
          {narrator(d).map(line => <Text dimColor>{line}</Text>)}
          {rows.map(r => (
            <Box flexDirection="column">
              <Button key={`unit:${r.name}`} label={unitRowText(r)} plain dimColor={r.dim}
                onPress={go({ level: 'unit', thread: v.thread, unit: r.name })} />
              {r.backLines.map(line => <Text dimColor>{`   ${line}`}</Text>)}
            </Box>
          ))}
          {d.pause && <Text color="yellow">{`⏸ ${d.pause.unit} waits: ${d.pause.question ?? d.pause.kind}`}</Text>}
          {d.pause?.resume?.map(cmd => <Text dimColor>{cmd}</Text>)}
          {footer}
        </Box>
      )
    }

    if (v.level === 'unit' && v.unit) {
      const plan = d.plan.find(p => p.name === v.unit)
      return (
        <Box flexDirection="column">
          {header}
          <Text>{`${v.unit} · ${plan?.kind ?? 'step'} · ${plan?.executor ?? '–'} / judge ${plan?.judge_executor ?? '–'}`}</Text>
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
      const j = att.judge
      return (
        <Box flexDirection="column">
          {header}
          <Text>{`step ${stripText({ S: 'done', C: 'none', J: 'none', G: 'none' }).slice(0, 1)} · check ${att.check?.result ?? '–'}${att.check?.environmental ? ' (environmental)' : ''}`}</Text>
          {att.check?.evidence && <Text dimColor>{att.check.evidence}</Text>}
          {j?.criteria && <Text>{`judge ${j.met}/${j.total}${j.confidence != null ? ` · confidence ${j.confidence} (${j.confidence_source ?? '?'})` : ''}${j.gap ? ' · gap' : ''}`}</Text>}
          {(j?.criteria ?? []).map(c => <Text>{`  ${c.n}. ${c.id ?? ''} ${c.status}`}</Text>)}
          {(j?.blockers ?? []).map(b => <Text dimColor>{`  ${b.id}: ${b.evidence ?? 'no evidence line'}${b.fix ? ` → ${b.fix}` : ''}`}</Text>)}
          <Text>{`gate ${att.gate?.verdict ?? '–'}${att.gate?.route_target ? ` → ${att.gate.route_target}` : ''} · guard ${att.gate?.guard ?? '–'}`}</Text>
          {sessions.map(s => <Button key={`ses:${s.session_key}`} plain label={`session ${s.session_key}${s.live ? ' (live)' : ''}`}
            onPress={go({ ...v, level: 'session', session: s.session_key })} />)}
          {footer}
        </Box>
      )
    }

    const s = sessions.find(x => x.session_key === v.session)
    if (!s) return <Box flexDirection="column">{header}<Text dimColor>That session is not in the document.</Text>{footer}</Box>
    const showInputs = true // MDD §2.5 `show.tool_inputs`: a mod setting once MAC's settings land
    return (
      <Box flexDirection="column">
        {header}
        {sessionNow(s, showInputs).map(line => <Text>{line}</Text>)}
        {sessionInfo(s).map(line => <Text dimColor>{line}</Text>)}
        {footer}
      </Box>
    )
  })
}
