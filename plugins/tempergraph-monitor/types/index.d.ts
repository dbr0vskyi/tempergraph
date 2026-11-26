// The monitor's own session state: what its drawings read (MOV §2.1 "Model" layer).
// Engine documents are typed in hooks/lib/engine.ts; nothing here is an engine type.

export type MonitorRun = {
  threadId: string
  workflow: string
  label: string
  mark: '▶' | '⏸' | '✗' | '✓' | '⚠' | '·'
  state: string
  alive: boolean
  unit: string | null
  node: 'S' | 'C' | 'J' | 'G' | null
  attempt: number | null
  passed: number
  planned: number
  elapsed: number | null
  waiting: number | null
  cost: string
  question: string | null
  resume: string | null
  asks: string | null
  life: string | null
}

/** Where the pane is: the run list, a run, a unit, an attempt, or a session (MRV §2.1, MDD §2). */
export type MonitorView = {
  level: 'runs' | 'run' | 'unit' | 'attempt' | 'session' | 'pause' | 'cost' | 'fleet' | 'card'
  /** The attempt view's tab (step, check, judge, gate) or the session view's (now, calls, processes, log, info). */
  tab?: string
  thread?: string
  unit?: string
  visit?: number
  attempt?: number | null
  session?: string
  /** The fleet or other-repository row a card shows. */
  card?: string
}

/** The run list's filter and pins (MRV §2.2 `f`, `p`); pins are also kept in `$.store` across sessions. */
export type MonitorPrefs = { filter: 'all' | 'live' | 'waiting' | 'failed' | 'finished today'; pinned: string[] }

/** What a session tab read from files or `ps` (MDD §2.4): its session key, tab, lines and a note. */
export type MonitorExtra = { key: string; tab: string; lines: string[]; note: string | null }

/** Rows of other repositories on this machine (`scope = machine`, MRV §2.3): a read-only card each, no drill-down;
 * ended ones (`live` false) fold under one line. */
export type MonitorOther = { key: string; repo: string; text: string; card: string[]; live: boolean }

/** The fleet tab's documents (MCF §2.2) and the projection rows of the cost tab (MCF §2.1), as last read. */
export type MonitorFleet = { live: unknown; month: unknown; byWorkflow: unknown; projection: unknown;
  missing: string[]; others: MonitorOther[]; othersOpen?: boolean; readAt: number | null; error: string | null }

/** `looked` is what a failed lookup tried, in order (MDS-B7): the setting, PATH, the shim of the engine home. */
export type MonitorEngine = { installed: boolean; staleSince: number | null; error: string | null; looked: string[] }

declare module 'claude-code' {
  interface PluginState {
    'tempergraph-monitor': {
      runs: Shaped<MonitorRun[]>
      view: Shaped<MonitorView>
      detail: Shaped<unknown>
      engine: Shaped<MonitorEngine>
      endedAgo: Shaped<Record<string, number>>
      prefs: Shaped<MonitorPrefs>
      extra: Shaped<MonitorExtra>
      fleet: Shaped<MonitorFleet>
    }
  }
}
