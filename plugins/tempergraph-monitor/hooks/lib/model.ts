// What the band, the status line, the alerts and the pane show, derived from engine documents only.
// Pure functions: no `$`, no clock but the `now` passed in, so every rule is tested without a session.
// Specs: MBA §2 (band, status line, alerts), MRV §2.3–§2.4 (run list, run view), MDD §2 (drill-down),
// MCF contract M4 (cost shown honestly).

import type { Attempt, Cost, DetailDoc, RunRecord, Session, StatusRow, UnitDetail } from './engine'

// -- labels, marks, money ----------------------------------------------------------------------------------

/** FNV-1a, 32 bits: 4 hex of the thread id for a label (MBA §2.1); not a security hash. */
function hash4(text: string): string {
  let h = 0x811c9dc5
  for (const ch of new TextEncoder().encode(text)) {
    h ^= ch
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0').slice(0, 4)
}

/** MBA §2.1: alias, else label, else `<repo>/<branch-or-worktree>·<4 hex>`. */
export function runLabel(row: StatusRow, repo = 'repo'): string {
  if (row.alias) return row.alias
  if (row.label) return row.label
  const where = row.workspace?.branch || row.workspace?.path?.split('/').pop() || row.workflow
  return `${repo}/${where}·${hash4(row.thread_id)}`
}

export type Mark = '▶' | '⏸' | '✗' | '✓' | '⚠' | '·'

export function runMark(row: StatusRow, health?: DetailDoc['health']): Mark {
  if (health?.suspect_stall || (health?.cap_eta_min != null && health.cap_eta_min < 10)) return '⚠'
  if (row.state === 'paused') return '⏸'
  if (health?.orphaned) return '✗'
  if (row.alive || row.state === 'running') return '▶'
  if (row.state === 'finished') return row.exit_code === 0 || row.exit_code === undefined ? '✓' : '✗'
  if (row.state === 'stopped' || row.state === 'unfinished') return '✗'
  return '·'
}

/**
 * Contract M4: an estimate reads `est`, an incomplete figure says so, nothing measured reads `unmeasured`;
 * never a bare 0 or an estimate shown as reported.
 */
export function money(cost: Cost | undefined | null): string {
  if (!cost) return 'unmeasured'
  const reported = typeof cost.reported === 'number' ? cost.reported : null
  const estimated = typeof cost.estimated === 'number' ? cost.estimated : null
  const flag = cost.completeness ?? (cost.incomplete ? 'incomplete' : null)
  const figure = typeof cost.figure === 'number' ? cost.figure : (reported ?? estimated)
  if (figure === null) return 'unmeasured'
  const text = `$${figure.toFixed(2)}`
  if (flag === 'complete' && reported !== null) return text
  if (flag === 'incomplete') return `${text} est, incomplete`
  return `${text} est`
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '–'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`
}

export function since(ts: string | null | undefined, now: number): number | null {
  if (!ts) return null
  const t = Date.parse(ts)
  return Number.isNaN(t) ? null : Math.max(0, (now - t) / 1000)
}

// -- the node in flight ------------------------------------------------------------------------------------------

export type Node = 'S' | 'C' | 'J' | 'G'
export type Cell = 'done' | 'running' | 'failed' | 'not_run' | 'none'

export function lastAttempt(u: UnitDetail | undefined): Attempt | undefined {
  if (!u) return undefined
  for (let i = u.visits.length - 1; i >= 0; i--) {
    const a = u.visits[i]!.attempts
    if (a.length) return a[a.length - 1]
  }
  return undefined
}

function sessionsDone(sessions: Session[] | undefined): boolean {
  return !!sessions?.length && sessions.every(s => !!s.ended_at)
}

/** The S C J G strip of one attempt (MRV §2.4). `gated` false draws `–` cells for C J G. */
export function nodeStrip(a: Attempt | undefined, gated = true, running = false): Record<Node, Cell> {
  const strip: Record<Node, Cell> = { S: 'not_run', C: 'not_run', J: 'not_run', G: 'not_run' }
  if (!gated) Object.assign(strip, { C: 'none', J: 'none', G: 'none' })
  if (!a) return strip
  const stepSessions = a.step?.sessions
  const stepOk = stepSessions?.every(s => s.outcome?.ok !== false) ?? true
  if (a.scripts?.length && !stepSessions?.length) strip.S = a.scripts.every(s => s.exit_code === 0) ? 'done' : 'failed'
  else if (sessionsDone(stepSessions)) strip.S = stepOk ? 'done' : 'failed'
  else if (stepSessions?.length) strip.S = 'running'
  if (gated) {
    if (a.check) strip.C = a.check.result === 'FAIL' ? 'failed' : 'done'
    const js = a.judge?.sessions
    if (a.judge?.criteria) strip.J = (a.judge.blockers?.length ?? 0) > 0 ? 'failed' : 'done'
    else if (js?.length) strip.J = sessionsDone(js) ? 'done' : 'running'
    if (a.gate) strip.G = a.gate.verdict === 'PROCEED' ? 'done' : 'failed'
  }
  if (running && !a.gate) {
    const order: Node[] = ['S', 'C', 'J', 'G']
    const at = order.find(n => strip[n] === 'running') ?? order.find(n => strip[n] === 'not_run')
    if (at) strip[at] = 'running'
  }
  return strip
}

export function inFlight(strip: Record<Node, Cell>): Node | null {
  return (['S', 'C', 'J', 'G'] as const).find(n => strip[n] === 'running') ?? null
}

// -- one run, summarised -------------------------------------------------------------------------------------------

export type RunSummary = {
  threadId: string
  workflow: string
  label: string
  mark: Mark
  state: string
  alive: boolean
  unit: string | null // the unit in flight, or the one paused at
  node: Node | null
  attempt: number | null
  passed: number
  planned: number
  elapsed: number | null // seconds
  waiting: number | null // seconds a person has been waited on
  cost: string
  question: string | null
  resume: string | null
}

export function summarise(row: StatusRow, detail: DetailDoc | undefined, now: number, repo?: string): RunSummary {
  const units = detail?.units ?? []
  const planned = detail?.plan?.filter(p => p.kind !== 'finalizer').length ?? units.length
  const current = units.find(u => u.state === 'running') ?? units.find(u => u.state === 'paused')
    ?? (row.pending_gates?.[0] ? units.find(u => u.name === row.pending_gates![0]!.unit) : undefined)
  const plan = detail?.plan?.find(p => p.name === current?.name)
  const att = lastAttempt(current)
  const strip = nodeStrip(att, plan?.gated ?? true, current?.state === 'running')
  const first = units.flatMap(u => u.visits.flatMap(v => v.attempts)).map(a => a.started_at).filter(Boolean).sort()[0]
  const pause = detail?.pause
  return {
    threadId: row.thread_id,
    workflow: row.workflow,
    label: runLabel(row, repo),
    mark: runMark(row, detail?.health),
    state: row.state,
    alive: !!row.alive,
    unit: current?.name ?? row.pending_gates?.[0]?.unit ?? null,
    node: current?.state === 'running' ? inFlight(strip) : null,
    attempt: att?.attempt ?? null,
    passed: units.filter(u => u.state === 'passed').length,
    planned,
    elapsed: since(first, now),
    waiting: row.state === 'paused' ? (pause?.waiting_s ?? detail?.health?.waiting_for_person_s ?? null) : null,
    cost: money(detail ? sumCost(detail) : row.cost),
    question: pause?.question ?? null,
    resume: pause?.resume?.[0] ?? row.pending_gates?.[0]?.resume ?? null,
  }
}

function sumCost(d: DetailDoc): Cost {
  const run = d.run.cost
  if (run && (typeof run.reported === 'number' || typeof run.estimated === 'number')) {
    const figure = d.units.reduce((n, u) => n + (u.cost?.figure ?? 0), 0)
    return { ...run, figure: figure || (run.reported ?? run.estimated ?? null) }
  }
  return run ?? {}
}

// -- band and status line (MBA §2.2, §2.3) ---------------------------------------------------------------------------

const ENDED_RECENTLY_S = 10 * 60
const NAMED_FROM = 80

function segment(r: RunSummary, long: boolean): string {
  if (r.mark === '⏸') return `⏸ ${r.label} waits ${duration(r.waiting)}`
  const where = r.unit ? ` ${r.unit}${r.node ? `·${r.node}` : ''}` : ''
  if (!long) return `${r.mark} ${r.label}${where}`
  const node = { S: 'step', C: 'check', J: 'judge', G: 'gate' } as const
  const parts = [`${r.mark} ${r.label}`]
  if (r.unit) parts.push(`${r.unit} ${Math.min(r.passed + 1, r.planned)}/${r.planned}`)
  if (r.node) parts.push(node[r.node])
  if (r.attempt && r.attempt > 1) parts.push(`attempt ${r.attempt}`)
  if (r.elapsed != null) parts.push(duration(r.elapsed))
  parts.push(r.cost)
  return parts.join(' · ')
}

function isLive(r: RunSummary): boolean {
  return r.alive || r.mark === '⏸' || r.mark === '⚠'
}

/**
 * The band row, or null for none. Waiting runs come first (MBA-B1). `endedAgo` gives, per thread, seconds
 * since its last segment ended, for the 10-minute "finished" row.
 */
export function bandRow(runs: readonly RunSummary[], columns: number, endedAgo: Record<string, number> = {},
                        stale = false): string | null {
  const row = bandText(runs, columns - (stale ? STALE.length : 0), endedAgo)
  return row === null ? null : stale && columns >= 20 ? row + STALE : row
}

const STALE = ' · stale'

function bandText(runs: readonly RunSummary[], columns: number, endedAgo: Record<string, number>): string | null {
  const live = runs.filter(isLive).sort((a, b) => Number(b.mark === '⏸') - Number(a.mark === '⏸'))
  if (columns < 20 && live.length) {
    // MBA §4: under 20 columns, `tg ⏸1` when anything waits, else `tg ▶n`
    const waiting = live.filter(r => r.mark === '⏸').length
    return waiting ? `tg ⏸${waiting}` : `tg ▶${live.length}`
  }
  if (live.length === 0) {
    const recent = runs.filter(r => (endedAgo[r.threadId] ?? Infinity) <= ENDED_RECENTLY_S && r.mark !== '·')
      .sort((a, b) => (endedAgo[a.threadId] ?? 0) - (endedAgo[b.threadId] ?? 0))[0]
    if (!recent) return null
    const word = recent.mark === '✓' ? 'finished' : 'stopped'
    return fit(`tg ${recent.mark} ${recent.label} ${word} · ${recent.cost}`, columns)
  }
  if (live.length === 1) return fit(`tg ${segment(live[0]!, true)}`, columns)
  if (live.length <= 3) {
    const row = `tg ${live.map(r => segment(r, false)).join('  ')}`
    if (row.length <= columns) return row
  }
  return fit(countsRow(runs, live, columns), columns)
}

function countsRow(runs: readonly RunSummary[], live: readonly RunSummary[], columns: number): string {
  const n = (m: Mark) => live.filter(r => r.mark === m).length
  const failed = runs.filter(r => r.mark === '✗').length
  const parts = [`${live.length}`]
  if (n('▶') + n('⚠')) parts.push(`▶ ${n('▶') + n('⚠')}`)
  if (n('⏸')) parts.push(`⏸ ${n('⏸')}`)
  if (failed) parts.push(`✗ ${failed}`)
  const total = live.reduce((t, r) => t + (Number(r.cost.replace(/[^0-9.]/g, '').split(' ')[0]) || 0), 0)
  const cost = live.some(r => r.cost === 'unmeasured') ? '' : ` · $${total.toFixed(2)} est`
  const head = `tg ${parts.join(' ')}${cost}`
  const waiting = live.filter(r => r.mark === '⏸').sort((a, b) => (b.waiting ?? 0) - (a.waiting ?? 0))
  // From 80 columns the oldest waiting run is named after the counts, with its wait time (MBA-B1).
  const named = waiting.length && columns >= NAMED_FROM ? `  ${segment(waiting[0]!, false)}` : ''
  return head.length + named.length <= columns ? head + named : head
}

function fit(text: string, columns: number): string {
  return text.length <= columns ? text : `${text.slice(0, Math.max(1, columns - 1))}…`
}

/** MBA §2.3: `tg 2▶ 1⏸`, or undefined to clear it. */
export function statusLine(runs: readonly RunSummary[]): string | undefined {
  const running = runs.filter(r => r.alive && r.mark !== '⏸').length
  const waiting = runs.filter(r => r.mark === '⏸').length
  if (!running && !waiting) return undefined
  return ['tg', running ? `${running}▶` : '', waiting ? `${waiting}⏸` : ''].filter(Boolean).join(' ')
}

// -- alerts (MBA §2.4) -------------------------------------------------------------------------------------------------

export type Alert = { threadId: string; seq: number; toast: string; notify: boolean; title: string; body: string;
  kind: 'pause' | 'failed' | 'finished' | 'stall' | 'cap' }

export type AlertSettings = { finished: boolean }

/**
 * New alerts from run-log records after the last alerted `seq` of the thread. Each `(thread, seq)` is raised
 * once: the caller keeps the highest `seq` returned per thread in `$.store` (MBA-B2).
 */
export function alertsFrom(threadId: string, label: string, records: readonly RunRecord[], lastAlerted: number,
                           settings: AlertSettings = { finished: false }): Alert[] {
  const out: Alert[] = []
  for (const r of records) {
    if (r.seq <= lastAlerted) continue
    if (r.kind === 'pause') {
      const q = clip(String(r.question ?? r.reason ?? r.pause_kind ?? 'a decision'), 80)
      out.push({ threadId, seq: r.seq, kind: 'pause', title: label, notify: true,
        toast: `${label}: ${r.unit} waits for you`, body: `${r.unit} waits: ${q}` })
    } else if (r.kind === 'run_exit') {
      const code = Number(r.exit_code)
      if (code === 4 || code === 5) {
        out.push({ threadId, seq: r.seq, kind: 'failed', title: label, notify: true,
          toast: `${label} stopped (exit ${code}, ${String(r.reason ?? '')})`,
          body: `stopped: ${String(r.reason ?? `exit ${code}`)}` })
      } else if (code === 0) {
        out.push({ threadId, seq: r.seq, kind: 'finished', title: label, notify: settings.finished,
          toast: `${label} finished`, body: 'finished' })
      }
    }
  }
  return out
}

/** Health alerts are keyed by the detail's `last_seq`, so a stall is raised once per record seen. */
export function healthAlerts(threadId: string, label: string, d: DetailDoc, was: { stall: boolean; cap: boolean }): Alert[] {
  const seq = d.run.last_seq ?? 0
  const out: Alert[] = []
  if (d.health?.suspect_stall && !was.stall) {
    out.push({ threadId, seq, kind: 'stall', title: label, notify: false, toast: `${label} looks stalled`, body: '' })
  }
  const eta = d.health?.cap_eta_min
  if (eta != null && eta < 10 && !was.cap) {
    out.push({ threadId, seq, kind: 'cap', title: label, notify: true,
      toast: `${label} reaches its cost cap in ${Math.round(eta)} min`, body: `cost cap in ${Math.round(eta)} min` })
  }
  return out
}

export function clip(text: string, limit: number): string {
  const one = text.replace(/\s+/g, ' ').trim()
  return one.length <= limit ? one : `${one.slice(0, limit - 1)}…`
}

// -- run list (MRV §2.3) ---------------------------------------------------------------------------------------------------

const ORDER: Record<Mark, number> = { '⏸': 0, '⚠': 1, '▶': 1, '✗': 2, '✓': 3, '·': 4 }

export function runList(runs: readonly RunSummary[]): RunSummary[] {
  return [...runs].sort((a, b) => ORDER[a.mark] - ORDER[b.mark] || a.label.localeCompare(b.label))
}

export function listRow(r: RunSummary): string {
  const where = r.unit ? `${r.unit}${r.node ? `·${r.node}` : ''}` : ''
  const att = r.attempt ? `a${r.attempt}${r.attempt > 1 ? ' ↻' : ''}` : ''
  const time = r.mark === '⏸' ? `waits ${duration(r.waiting)}` : duration(r.elapsed)
  return [`${r.mark} ${r.label}`, r.workflow, `${r.passed}/${r.planned}`, where, att, time, r.cost]
    .filter(Boolean).join('  ')
}

// -- run view (MRV §2.4) ------------------------------------------------------------------------------------------------------

const UNIT_MARK: Record<string, string> = { passed: '✓', running: '▶', paused: '⏸', failed: '✗', not_reached: '·',
  skipped: '⊘' }

export type UnitRow = {
  name: string
  mark: string
  dim: boolean
  kind: string
  strip: Record<Node, Cell>
  visits: number
  attempt: number | null
  from: string | null // `←plan` when the last visit came from a trip back
  judge: string | null // `5/6 · 0.82`
  share: number | null
  cost: string
  time: string
  backLines: string[]
}

export function unitRows(d: DetailDoc): UnitRow[] {
  return d.units.map(u => {
    const plan = d.plan.find(p => p.name === u.name)
    const att = lastAttempt(u)
    const lastVisit = u.visits[u.visits.length - 1]
    const judged = [...u.visits].reverse().flatMap(v => [...v.attempts].reverse()).find(a => a.judge?.criteria)?.judge
    const unverifiable = judged?.criteria?.filter(c => c.status === 'UNVERIFIABLE').length ?? 0
    const back = lastVisit?.entered_from.startsWith('back:') ? lastVisit.entered_from.slice(5) : null
    return {
      name: u.name,
      mark: UNIT_MARK[u.state] ?? '·',
      dim: u.state === 'not_reached' || u.state === 'skipped',
      kind: plan?.kind && plan.kind !== 'step' ? plan.kind : '',
      strip: nodeStrip(att, plan?.gated ?? true, u.state === 'running'),
      visits: u.visits.length,
      attempt: att?.attempt ?? null,
      from: back ? `←${back}` : null,
      judge: judged ? `${judged.met}/${judged.total}${judged.confidence != null ? ` · ${judged.confidence.toFixed(2)}` : ''}`
        + (unverifiable ? ` · ${unverifiable} UNVERIFIABLE` : '') : null,
      share: u.share ?? null,
      cost: money(u.cost),
      time: duration(u.duration_s),
      backLines: u.visits.filter(v => v.entered_from.startsWith('back:')).map(v => {
        const from = v.entered_from.slice(5)
        const sender = d.units.find(x => x.name === from)
        const gate = sender?.visits.flatMap(x => x.attempts).find(a => a.gate?.verdict === 'BACK' && a.gate.route_target === u.name)
        const why = gate?.judge?.blockers?.map(b => b.id).join(', ')
        return `↩ from ${from} (gate BACK${why ? `: ${why}` : ''})`
      }),
    }
  })
}

export function stripText(strip: Record<Node, Cell>): string {
  const glyph: Record<Cell, (n: Node) => string> = {
    done: n => n, running: n => `[${n}]`, failed: n => `${n}!`, not_run: () => '·', none: () => '–' }
  return (['S', 'C', 'J', 'G'] as const).map(n => glyph[strip[n]](n)).join(' ')
}

export function unitRowText(r: UnitRow): string {
  const va = r.attempt ? `${r.visits > 1 ? `v${r.visits} ` : ''}a${r.attempt}` : ''
  return [`${r.mark} ${r.name}${r.kind ? ` ${r.kind}` : ''}`, stripText(r.strip), va, r.from ?? '', r.judge ?? '',
    r.share != null ? `${Math.round(r.share * 100)}%` : '', r.time].filter(Boolean).join('  ')
}

/** MRV §2.4 touch strip: one mark per touch, `<class letter>·<decider>`. */
export function touchStrip(d: DetailDoc): string {
  const touches = d.supervision?.touches ?? []
  return touches.map(t => `${(t.class ?? t.action ?? '?').slice(0, 1).toUpperCase()}·${t.decider ?? t.caller_kind ?? '?'}`)
    .join(' ')
}

/** Up to five narrator lines, newest last, as `HH:MM text` (MRV §2.4). */
export function narrator(d: DetailDoc, n = 5): string[] {
  return (d.events_tail ?? []).slice(-n).map(line => {
    const [, ts = '', ...rest] = line.split(' ')
    const hhmm = /T(\d\d:\d\d)/.exec(ts)?.[1] ?? ''
    return `${hhmm} ${rest.join(' ')}`.trim()
  })
}

// -- drill-down (MDD §2) -------------------------------------------------------------------------------------------------------

export type AttemptRow = { visit: number; from: string; attempt: number | null; strip: string; check: string; judge: string;
  gate: string; cause: string; time: string }

export function attemptRows(d: DetailDoc, unit: string): AttemptRow[] {
  const u = d.units.find(x => x.name === unit)
  const gated = d.plan.find(p => p.name === unit)?.gated ?? true
  if (!u) return []
  return u.visits.flatMap(v => v.attempts.map((a, i) => ({
    visit: v.visit,
    from: i === 0 ? v.entered_from : '',
    attempt: a.attempt,
    strip: stripText(nodeStrip(a, gated, u.state === 'running' && a === lastAttempt(u))),
    check: a.check?.result ?? '–',
    judge: a.judge?.criteria ? `${a.judge.met}/${a.judge.total}` : '–',
    gate: a.gate ? `${a.gate.verdict}${a.gate.route_target && a.gate.verdict !== 'PROCEED' ? ` → ${a.gate.route_target}` : ''}` : '–',
    cause: a.repeat_cause ?? '',
    time: duration(spanS(a.started_at, a.ended_at)),
  })))
}

function spanS(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null
  const s = (Date.parse(b) - Date.parse(a)) / 1000
  return Number.isNaN(s) ? null : s
}

export function findAttempt(d: DetailDoc, unit: string, visit: number, attempt: number | null): Attempt | undefined {
  return d.units.find(u => u.name === unit)?.visits.find(v => v.visit === visit)?.attempts.find(a => a.attempt === attempt)
}

/** MDD §2.4 Now tab of a session, as lines; `showInputs` false hides every input summary (MDD-B5). */
export function sessionNow(s: Session, showInputs: boolean, idleLimit?: number | null): string[] {
  const lines: string[] = []
  const live = s.live
  if (live) {
    const t = live.open_tool
    if (t) {
      const what = showInputs && t.input_summary ? ` · ${t.input_summary}` : ''
      lines.push(`${t.name}${what} · ${duration(t.elapsed)}`)
    } else {
      lines.push('no tool open')
    }
    if (live.last_text) lines.push(`“${live.last_text}”`)
    if (live.tokens_so_far != null || live.turns_so_far != null) {
      lines.push(`${live.tokens_so_far ?? '?'} tokens · ${live.turns_so_far ?? '?'} turns so far`)
    }
    const age = live.last_event_age_s
    if (age != null) {
      const pct = idleLimit ? Math.min(100, Math.round((age / idleLimit) * 100)) : null
      lines.push(`last event ${duration(age)} ago${pct != null ? ` · idle ${pct}%${pct >= 80 ? ' ⚠' : ''}` : ''}`)
    }
    for (const c of live.recent ?? []) {
      const what = showInputs && c.input_summary ? ` ${c.input_summary}` : ''
      lines.push(`  ${c.ok === false ? '✗' : '✓'} ${c.name}${what} ${duration(c.duration_s)}`)
    }
    return lines
  }
  const o = s.outcome
  if (!o) return ['not finished']
  const word = o.timed_out ? 'timed out' : o.stalled ? 'stalled' : o.partial ? 'partial'
    : o.infra_cause ? `infra: ${o.infra_cause}` : o.error_kind ? `error: ${o.error_kind}` : o.ok ? 'ok' : 'failed'
  lines.push(`outcome ${word}`)
  if (s.tool_calls != null) lines.push(`${s.tool_calls} tool calls`)
  return lines
}

export function sessionInfo(s: Session): string[] {
  const usage = s.usage ?? {}
  const cost = money({ reported: usage.reported_cost_usd ?? null, estimated: usage.estimated_cost_usd ?? null,
    completeness: usage.reported_cost_usd != null ? 'complete' : usage.estimated_cost_usd != null ? 'estimated' : null })
  return [
    `${s.session_key} · ${s.kind ?? ''} on ${s.executor ?? '?'} (${s.model ?? s.alias ?? 'model not reported'})`,
    `session id ${s.session_id ?? 'not reported'}`,
    `engine log ${s.transcript?.engine ?? 'none'}`,
    `native transcript ${s.transcript?.native ?? 'not linked'}`,
    `activity ${s.activity_path ?? '–'}`,
    `cost ${cost}`,
  ]
}

// -- filter and pin (MRV §2.2 `f`, `p`) ---------------------------------------------------------------------------------

export const FILTERS = ['all', 'live', 'waiting', 'failed', 'finished today'] as const
export type Filter = (typeof FILTERS)[number]

export function nextFilter(f: Filter): Filter {
  return FILTERS[(FILTERS.indexOf(f) + 1) % FILTERS.length]!
}

/**
 * The run list under a filter, pinned runs first (MRV §2.3). `endedAgo` holds seconds since each ended run's
 * `run_exit`; `todayS` is the seconds since local midnight, so "finished today" needs no clock of its own.
 */
export function shownRuns(runs: readonly RunSummary[], filter: Filter, pinned: readonly string[],
                          endedAgo: Record<string, number>, todayS: number): RunSummary[] {
  const keep = (r: RunSummary): boolean => {
    if (filter === 'live') return isLive(r)
    if (filter === 'waiting') return r.mark === '⏸'
    if (filter === 'failed') return r.mark === '✗'
    if (filter === 'finished today') return r.mark === '✓' && (endedAgo[r.threadId] ?? Infinity) <= todayS
    return true
  }
  const sorted = runList(runs.filter(keep))
  return [...sorted.filter(r => pinned.includes(r.threadId)), ...sorted.filter(r => !pinned.includes(r.threadId))]
}
