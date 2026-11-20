// What the monitor reads and how (MDS §2.1, §2.2), as pure functions the hooks module drives from timers.
// Contract M1: only read-only engine verbs are ever built here, from constants and values the engine printed.

import type { RunRecord } from './engine'

export const ENGINE = 'tempergraph'

/** Every verb the monitor may run. A verb that writes is never built (MDS-AC-2). */
export const READ_ONLY_VERBS = ['status', 'events'] as const
export type ReadOnlyVerb = (typeof READ_ONLY_VERBS)[number]

export const WRITING_VERBS = ['run', 'resume', 'stop', 'batch', 'rerun', 'store', 'hooks', 'update', 'upgrade',
  'install', 'label', 'schedule', 'improve', 'scaffold', 'author', 'workflows', 'supervision'] as const

/** Engine thread ids and session keys are printed by the engine; anything else is refused. */
const THREAD = /^[A-Za-z0-9_][A-Za-z0-9_.-]*\/[A-Za-z0-9_][A-Za-z0-9_.:-]*$/
const UNIT = /^[A-Za-z_][A-Za-z0-9_-]*$/

export function statusArgv(): readonly string[] {
  return [ENGINE, 'status', '--json']
}

export function detailArgv(threadId: string, unit?: string): readonly string[] {
  if (!THREAD.test(threadId)) throw new Error(`not an engine thread id: ${threadId}`)
  if (unit !== undefined && !UNIT.test(unit)) throw new Error(`not a unit name: ${unit}`)
  return [ENGINE, 'status', threadId, '--detail', '--json', ...(unit ? ['--unit', unit] : [])]
}

export function isReadOnly(argv: readonly string[]): boolean {
  return argv[0] === ENGINE && (READ_ONLY_VERBS as readonly string[]).includes(argv[1] ?? '')
}

// -- run-log tail (MDS §2.2) -------------------------------------------------------------------------------

export type TailState = { offset: number; size: number }

export const TAIL_START: TailState = { offset: 0, size: 0 }

/** Where the next read starts: a file that shrank was replaced and is read again from 0. */
export function nextRead(state: TailState, size: number, max = 4 * 1024 * 1024): { offset: number; length: number } {
  const offset = size < state.size || size < state.offset ? 0 : state.offset
  return { offset, length: Math.min(max, Math.max(0, size - offset)) }
}

/**
 * Parses one read of a run log from `offset`. A last line without a newline is dropped and read again next
 * time, so a record written in two pieces is yielded once (MDS-AC-3). Unparsable lines and the schema
 * line are skipped. Offsets count UTF-8 bytes, as the file does.
 */
export function parseChunk(text: string, offset: number): { records: RunRecord[]; offset: number } {
  const end = text.lastIndexOf('\n')
  if (end < 0) return { records: [], offset }
  const whole = text.slice(0, end + 1)
  const records: RunRecord[] = []
  for (const line of whole.split('\n')) {
    if (!line.trim()) continue
    try {
      const rec = JSON.parse(line) as RunRecord
      if (rec && typeof rec === 'object' && typeof rec.seq === 'number') records.push(rec)
    } catch {
      // a line cut by a dead process; the engine ends it before its next record
    }
  }
  return { records, offset: offset + new TextEncoder().encode(whole).length }
}

/** Keeps the last `limit` records per thread in memory (MDS §2.2 bounds), each `seq` once. */
export function keepTail(held: readonly RunRecord[], added: readonly RunRecord[], limit = 500): RunRecord[] {
  const last = held.length ? held[held.length - 1]!.seq : -1
  return [...held, ...added.filter(r => r.seq > last)].slice(-limit)
}

// -- poll rates (MDS §2.1, MDS-B1) -------------------------------------------------------------------------------

export const RATES = { live: 5_000, idle: 30_000, change: 1_000, detail: 2_000 } as const

/** How long to wait before the next `status` call. */
export function statusEvery(anyAlive: boolean, paneOpen: boolean): number {
  return anyAlive || paneOpen ? RATES.live : RATES.idle
}
