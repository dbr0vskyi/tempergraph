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
}

/** Where the pane is: the run list, a run, a unit, an attempt, or a session (MRV §2.1, MDD §2). */
export type MonitorView = {
  level: 'runs' | 'run' | 'unit' | 'attempt' | 'session'
  thread?: string
  unit?: string
  visit?: number
  attempt?: number | null
  session?: string
}

export type MonitorEngine = { installed: boolean; staleSince: number | null; error: string | null }

declare module 'claude-code' {
  interface PluginState {
    'tempergraph-monitor': {
      runs: Shaped<MonitorRun[]>
      view: Shaped<MonitorView>
      detail: Shaped<unknown>
      engine: Shaped<MonitorEngine>
      endedAgo: Shaped<Record<string, number>>
    }
  }
}
