// What the monitor reads and how (MDS §2.1, §2.2), as pure functions the hooks module drives from timers.
// Contract M1: only read-only engine verbs are ever built here, from constants and values the engine printed.

import type { RunRecord } from './engine'
import { PS_ARGV } from './session'

export const ENGINE = 'tempergraph'

/** The program run for engine verbs: `tempergraph` on PATH, or the `engine_path` setting (MAC §2.3). */
let engine: string = ENGINE

/** Takes an absolute path to the shim, or empty for PATH; anything else is refused and PATH is kept. */
export function useEngine(path: string | undefined): string {
  const p = (path ?? '').trim()
  engine = p && /^(\/|[A-Za-z]:[\\/])[^\0\n]*$/.test(p) && /(^|[\\/])tempergraph(\.exe|\.cmd)?$/.test(p) ? p : ENGINE
  return engine
}

/** Every verb the monitor may run. A verb that writes is never built (MDS-AC-2). */
export const READ_ONLY_VERBS = ['status', 'events', 'stats'] as const
export type ReadOnlyVerb = (typeof READ_ONLY_VERBS)[number]

export const WRITING_VERBS = ['run', 'resume', 'stop', 'batch', 'rerun', 'store', 'hooks', 'update', 'upgrade',
  'install', 'label', 'schedule', 'improve', 'scaffold', 'author', 'workflows', 'supervision'] as const

/** Engine thread ids and session keys are printed by the engine; anything else is refused. */
const THREAD = /^[A-Za-z0-9_][A-Za-z0-9_.-]*\/[A-Za-z0-9_][A-Za-z0-9_.:-]*$/
const UNIT = /^[A-Za-z_][A-Za-z0-9_-]*$/

/** `stats` writes only as `stats flush`, `stats sync` and `--sync` (engine CST §2.5); the monitor never asks for those. */
const STATS_WRITES = ['flush', 'sync', '--sync']
const SINK = /^[a-z0-9-]{1,40}$/

/** The run rows: this repository, or with `scope = machine` every root of the machine index (MDS §2.1). */
export function statusArgv(machine = false): readonly string[] {
  return machine ? [engine, 'status', '--all-roots', '--json'] : [engine, 'status', '--json']
}

/** `stats --projection` for the cost tab (MCF §2.1). */
export function projectionArgv(): readonly string[] {
  return [engine, 'stats', '--projection', '--by', 'workflow', '--json']
}

/** `stats --live` over the fleet copy, or this machine's month by `key` (MCF §2.2); `--local` without a sink (MCF-B5). */
export function fleetArgv(what: 'live' | 'machine' | 'workflow', sink: string): readonly string[] {
  if (sink && !SINK.test(sink)) throw new Error(`not a sink name: ${sink}`)
  if (what === 'live') return [engine, 'stats', '--live', '--json']
  return [engine, 'stats', ...(sink ? [] : ['--local']), '--month', monthOf(Date.now()), '--by', what, '--json']
}

export function monthOf(ms: number): string {
  return new Date(ms).toISOString().slice(0, 7)
}

export function detailArgv(threadId: string, unit?: string): readonly string[] {
  if (!THREAD.test(threadId)) throw new Error(`not an engine thread id: ${threadId}`)
  if (unit !== undefined && !UNIT.test(unit)) throw new Error(`not a unit name: ${unit}`)
  return [engine, 'status', threadId, '--detail', '--json', ...(unit ? ['--unit', unit] : [])]
}

/** An engine verb that only reads, or the constant `ps` listing of MDS §2.1; nothing else is run. */
export function isReadOnly(argv: readonly string[]): boolean {
  if (argv.length === PS_ARGV.length && argv.every((a, i) => a === PS_ARGV[i])) return true
  if (argv[0] !== engine || !(READ_ONLY_VERBS as readonly string[]).includes(argv[1] ?? '')) return false
  return argv[1] !== 'stats' || !argv.some(a => STATS_WRITES.includes(a))
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
