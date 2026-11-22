// The engine documents the monitor reads, as far as it reads them (MOV §5: the engine owns every document).
// Status rows: engine DUR-B11. Detail document: engine RDD-B7 to RDD-B11, RDD-B13, RDD-B15. Run-log records: engine EVT-B8, EVT-B9, EVT-B10 to EVT-B16.
// Every reader here skips what it does not know (engine OVR-B14) and treats a missing figure as
// "not recorded", never as zero (monitor contract M4).

export const KNOWN_SCHEMA = { status: 1, detail: 1, run_log: 1 } as const

export type Cost = {
  reported?: number | null
  estimated?: number | null
  figure?: number | null
  completeness?: 'complete' | 'estimated' | 'incomplete' | null
  incomplete?: boolean
}

export type PendingGate = { unit: string; item?: string | null; kind: string; resume: string }

export type StatusRow = {
  thread_id: string
  workflow: string
  state: string // running, paused, stopped, unfinished, finished, none, unreadable
  alive?: boolean
  pending_gates?: PendingGate[]
  alias?: string
  label?: string | null
  last_verdict?: string
  cost?: Cost
  exit_code?: number
  exit_reason?: string
  workspace?: { mode?: string; path?: string; branch?: string; state?: string }
  executors?: Record<string, string>
  log_path?: string
  state_root?: string // with `--all-roots` (engine CST-B8)
}

export type StatusDoc = { schema_version: number; generated_at?: string; threads: StatusRow[];
  roots?: { path: string; missing: boolean }[] }

export type RunRecord = {
  seq: number
  ts: string
  kind: string
  thread_id?: string
  segment?: number
  unit?: string | null
  item?: string | null
  attempt?: number | null
  session_key?: string | null
  [field: string]: unknown
}

export type LiveBlock = {
  open_tool?: { name?: string; capability?: string | null; input_summary?: string | null; elapsed?: number | null } | null
  recent?: { name?: string; input_summary?: string | null; ok?: boolean | null; duration_s?: number | null }[]
  last_text?: string | null
  tokens_so_far?: number | null
  turns_so_far?: number | null
  pgid?: number | null
  last_event_age_s?: number | null
}

export type Session = {
  session_key: string
  kind?: string
  executor?: string
  alias?: string
  model?: string | null
  session_id?: string | null
  transcript?: { engine?: string | null; native?: string | null } | null
  activity_path?: string
  live_path?: string
  usage?: Record<string, number | null> | null
  tool_calls?: number | null
  outcome?: { ok?: boolean | null; timed_out?: boolean | null; stalled?: boolean | null; partial?: boolean | null;
    infra_cause?: string | null; error_kind?: string | null } | null
  started_at?: string | null
  ended_at?: string | null
  live?: LiveBlock
}

export type Blocker = { id: string; evidence?: string | null; fix?: string | null }

export type Attempt = {
  attempt: number | null
  item?: string | null
  started_at?: string | null
  ended_at?: string | null
  step?: { sessions?: Session[] } | null
  check?: { result?: string; environmental?: boolean; duration_s?: number | null; evidence?: string | null } | null
  judge?: { sessions?: Session[]; criteria?: { n?: number; id?: string | null; status?: string }[]; met?: number;
    total?: number; blockers?: Blocker[]; confidence?: number | null; confidence_source?: string | null;
    gap?: boolean | null; guard?: string | null } | null
  gate?: { verdict?: string | null; route_target?: string | null; guard?: string | null } | null
  repeat_cause?: string | null
  scripts?: { name?: string; phase?: string; exit_code?: number | null }[]
}

export type Visit = { visit: number; entered_from: string; attempts: Attempt[]; attempts_count?: number }

export type UnitDetail = {
  name: string
  state: 'not_reached' | 'running' | 'passed' | 'failed' | 'paused' | 'skipped' | string
  visits: Visit[]
  cost?: Cost
  duration_s?: number | null
  share?: number | null
}

export type PlanUnit = {
  name: string
  kind?: string
  gated?: boolean
  executor?: string | null
  judge_executor?: string | null
  alias?: string | null
  edges?: { target: string; on: string }[]
  items?: number | null
}

export type Pause = {
  unit?: string
  kind?: string
  question?: string | null
  artifacts?: { key: string; path?: string | null }[]
  decisions?: string[]
  resume?: string[]
  waiting_since?: string | null
  waiting_s?: number | null
}

export type Touch = { ts?: string; unit?: string | null; class?: string | null; action?: string | null;
  caller_kind?: string | null; decider?: string | null; relay?: unknown; wait_s?: number | null }

export type Health = {
  alive?: boolean
  silent_s?: number | null
  suspect_stall?: boolean
  orphaned?: boolean
  waiting_for_person_s?: number | null
  burn_usd_per_h?: number | null
  cap_eta_min?: number | null
}

export type DetailDoc = {
  schema_version: number
  generated_at?: string
  run: StatusRow & { segment?: number | null; last_seq?: number | null; run_dir?: string; plan_digest?: string }
  plan: PlanUnit[]
  plan_stale?: boolean
  units: UnitDetail[]
  pause?: Pause | null
  budgets?: { counters?: Record<string, { used?: number | null; limit?: number | null }>;
    run_cost_cap?: { limit?: number | null; left?: number | null } }
  health?: Health
  supervision?: { touches?: Touch[]; level?: string | null; level_by?: string | null; designed_by?: string | null
    cost?: SupervisionCost | null }
  events_tail?: string[]
  truncated?: string[]
}

/** A document of a newer major schema is not drawn (MDS §2.2). */
export function isReadable(doc: { schema_version?: unknown } | null | undefined, kind: keyof typeof KNOWN_SCHEMA): boolean {
  const v = doc?.schema_version
  return typeof v === 'number' && v <= KNOWN_SCHEMA[kind]
}

/** SCO-B15's closed figures for a thread, as the detail document carries them (null until it closes). */
export type SupervisionFigure = { tokens?: Record<string, number>; estimated_usd?: number | null }
export type SupervisionCost = {
  marginal?: { by_category?: Record<string, SupervisionFigure>; total?: SupervisionFigure } | null
  turn?: { by_category?: Record<string, SupervisionFigure>; total?: SupervisionFigure } | null
  completeness?: string | null
  observations?: number | null
}
