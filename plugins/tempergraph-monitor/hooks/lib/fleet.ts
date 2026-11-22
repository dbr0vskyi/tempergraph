// The fleet tab (MCF §2.2), the projection line of the cost tab (MCF §2.1) and the other repositories of
// `scope = machine` (MDS §2.1, MRV §2.3), as pure functions over the engine's `stats` and `status --all-roots`
// documents (engine CST-B14, CST-B15, CST-B16, CST-B8). Contract M4: reported and estimated money stay apart, and a figure the
// engine did not record is `—`, never 0.

import { duration } from './model'

/** One row of `stats --projection` (engine CST-B14, CST-B15, CST-B16). */
export type Projection = { workflow: string; runs: number; median_usd: number; p90_usd: number; thin: boolean }
export type ProjectionDoc = { schema_version: number; projection?: Projection[] }

/** A thread of a heartbeat as `stats --live` prints it (engine CST-B9 `heartbeat`). */
export type LiveThread = {
  thread_id?: string // this machine's own threads only; another machine's carry a hash at most
  thread_hash?: string
  repo_id?: string | null
  workflow?: string
  alias?: string | null
  state?: string
  unit?: string | null
  attempt?: number | null
  estimated_cost_usd?: number | null
  waiting_for_person_s?: number | null
  waiting_on?: string | null
  machine_id: string
  label?: string | null
  stale?: boolean
}
export type LiveDoc = {
  schema_version: number
  machines?: { machine_id: string; label?: string | null; at?: string; age_s?: number | null; stale?: boolean; this_machine?: boolean }[]
  runs?: LiveThread[]
}

export type Totals = { runs: number; reported_usd: number | null; estimated_usd: number | null; completeness?: string;
  lower_bound?: boolean; exits?: Record<string, number> }
export type StatsDoc = {
  schema_version: number
  source?: string
  totals?: Totals
  by?: { key: string; groups: Record<string, Totals> }
  synced?: Record<string, { synced_at?: string | null; machines?: Record<string, { label?: string | null; ago_s?: number | null }> }> | null
}

/** `$1.20 rep · $3.40 est`, `≥` when the engine says the total is a lower bound, `—` when nothing was measured. */
export function totalsText(t: Totals | undefined): string {
  if (!t) return '—'
  const floor = t.lower_bound ? '≥ ' : ''
  const parts: string[] = []
  if (typeof t.reported_usd === 'number') parts.push(`${floor}$${t.reported_usd.toFixed(2)} rep`)
  if (typeof t.estimated_usd === 'number') parts.push(`${floor}$${t.estimated_usd.toFixed(2)} est`)
  const exits = Object.entries(t.exits ?? {}).map(([code, n]) => `${EXIT[code] ?? `exit ${code}`} ${n}`).join(', ')
  return [`${t.runs} run${t.runs === 1 ? '' : 's'}`, parts.join(' · ') || '—', t.completeness ?? '', exits]
    .filter(Boolean).join(' · ')
}

const EXIT: Record<string, string> = { '0': 'finished', '3': 'paused', '4': 'stopped', '5': 'budget or infra', '1': 'internal' }

/** The cost tab's projection line for one workflow (MCF §2.1, §4). */
export function projectionText(doc: ProjectionDoc | null, workflow: string): string {
  if (!doc) return 'unavailable'
  const p = (doc.projection ?? []).find(x => x.workflow === workflow || x.workflow.startsWith(`${workflow}@`))
  if (!p) return 'no finished run yet'
  return `median $${p.median_usd.toFixed(2)} · p90 $${p.p90_usd.toFixed(2)} est · ${p.runs} run${p.runs === 1 ? '' : 's'}${p.thin ? ' (thin)' : ''}`
}

export type FleetRow = { key: string; text: string; mine: boolean; threadId: string | null; card: string[] }

const MARK: Record<string, string> = { running: '▶', paused: '⏸' }

function short(id: string | null | undefined): string {
  return id ? (id.length > 16 ? `${id.slice(0, 8)}…` : id) : '—'
}

/** Live now (MCF §2.2): one row per live run on any machine; a row of another machine opens a card (MCF-B4). */
export function fleetRows(doc: LiveDoc | null): FleetRow[] {
  return (doc?.runs ?? []).map((t, i) => {
    const mine = !!doc?.machines?.find(m => m.machine_id === t.machine_id)?.this_machine
    const where = t.unit ? `${t.unit}${t.attempt ? ` a${t.attempt}` : ''}` : ''
    const wait = t.state === 'paused' ? `${MARK.paused} ${duration(t.waiting_for_person_s)}` : MARK[t.state ?? ''] ?? '·'
    const cost = typeof t.estimated_cost_usd === 'number' ? `$${t.estimated_cost_usd.toFixed(2)} est` : '—'
    const label = t.label ?? short(t.machine_id)
    const text = [wait, label, short(t.repo_id), t.workflow, t.alias ?? '', where, cost, t.stale ? 'stale' : '']
      .filter(Boolean).join('  ')
    const card = [
      `${t.workflow ?? '?'}${t.alias ? ` · ${t.alias}` : ''} on ${label}`,
      `state ${t.state ?? '?'}${t.unit ? ` at ${t.unit}` : ''}${t.attempt ? `, attempt ${t.attempt}` : ''}`,
      `repository ${short(t.repo_id)}`,
      t.state === 'paused' ? `waiting for a person ${duration(t.waiting_for_person_s)}` : '',
      `cost so far ${cost}`,
      t.stale ? 'heartbeat stale: the machine has not reported for over 5 minutes' : '',
      mine ? '' : `logs are on ${label}`,
    ].filter(Boolean)
    return { key: `${t.machine_id}:${t.thread_hash ?? t.thread_id ?? i}`, text, mine, threadId: mine ? t.thread_id ?? null : null, card }
  })
}

/** This month (MCF §2.2): one line per group of a `stats --by` document. */
export function monthRows(doc: StatsDoc | null): string[] {
  if (!doc?.by) return []
  return Object.entries(doc.by.groups).map(([k, t]) => `${k}  ${totalsText(t)}`)
}

/** The fleet header: when each sink's copy was last synced (CST-B7: another machine's figures are as of then). */
export function syncedText(doc: StatsDoc | null, now: number): string {
  const s = doc?.synced
  if (!s || !Object.keys(s).length) return 'not synced yet'
  return Object.entries(s).map(([sink, v]) => {
    const t = v.synced_at ? Date.parse(v.synced_at) : NaN
    return `${sink} synced ${Number.isFinite(t) ? `${duration((now - t) / 1000)} ago` : 'never'}`
  }).join(' · ')
}

export type FleetAlert = { key: string; toast: string }

/** `alerts_fleet`: a run waiting over 30 min on another machine, once per run and pause (MBA §2.4). */
export function fleetAlerts(doc: LiveDoc | null, seen: ReadonlySet<string>): FleetAlert[] {
  return (doc?.runs ?? []).filter(t => t.state === 'paused' && (t.waiting_for_person_s ?? 0) > 1800
    && !doc?.machines?.find(m => m.machine_id === t.machine_id)?.this_machine)
    .map(t => ({ key: `${t.machine_id}:${t.thread_hash ?? ''}`, toast:
      `${t.workflow ?? 'A run'}${t.alias ? ` (${t.alias})` : ''} has waited ${duration(t.waiting_for_person_s)} on ${t.label ?? 'another machine'}` }))
    .filter(a => !seen.has(a.key))
}

// -- scope = machine (MDS §2.1, MDS-B4) ----------------------------------------------------------------------------

export type RootEntry = { path: string; missing: boolean }

/** The repository of a state root (`…/<repo>/.tempergraph`), as the run list's group name. */
export function repoName(stateRoot: string): string {
  const parts = stateRoot.replace(/[\\/]+$/, '').split(/[\\/]/)
  return (parts.at(-1) === '.tempergraph' ? parts.at(-2) : parts.at(-1)) ?? stateRoot
}

/** `missing` lines for indexed roots whose folder is gone; the index itself is never touched. */
export function missingRoots(roots: readonly RootEntry[] | undefined): string[] {
  return (roots ?? []).filter(r => r.missing).map(r => `${repoName(r.path)}: missing (${r.path})`)
}
