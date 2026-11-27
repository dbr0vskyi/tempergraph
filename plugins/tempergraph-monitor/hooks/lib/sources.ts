// What the monitor reads and how (MDS §2.1, §2.2), as pure functions the hooks module drives from timers.
// Contract M1: only read-only engine verbs are ever built here, from constants and values the engine printed.

import type { RunRecord } from './engine'
import { PS_ARGV } from './session'

export const ENGINE = 'tempergraph'

/** The program run for engine verbs: the first place of MAC-B5 that did not exit 127, else the first to try. */
let engine: string = ENGINE
/** The accepted `engine_path` setting (MAC-B7), or null. */
let setting: string | null = null
/** The shim of the engine home as the probe answered (MAC-B6), or null while the probe has not run. */
let home: string | null = null
/** Whether a program can be run from the probe's answer: an absolute path, not the label alone. */
let homeRuns = false

const ABSOLUTE = /^(\/|[A-Za-z]:[\\/])[^\0\n]*$/

/** The constant probe of the engine home (MAC-B6): prints `$TEMPERGRAPH_HOME`, else `$HOME/.tempergraph`; builds no engine verb. */
export const HOME_ARGV = ['sh', '-c', 'printf %s "${TEMPERGRAPH_HOME:-$HOME/.tempergraph}"'] as const

/** What the pane names when the probe gave no home folder. */
export const HOME_LABEL = `~/.tempergraph/bin/${ENGINE}`

/** Takes an absolute path to the shim, or empty for PATH; anything else is refused (MAC-B7). Starts a new lookup. */
export function useEngine(path: string | undefined): string {
  const p = (path ?? '').trim()
  setting = p && ABSOLUTE.test(p) && /(^|[\\/])tempergraph(\.exe|\.cmd)?$/.test(p) ? p : null
  home = null
  homeRuns = false
  engine = setting ?? ENGINE
  return engine
}

/** The shim of the engine home from the probe's answer: its folder, `/bin/tempergraph`; the label when it gave none. */
export function homeShimPath(answer: string | null | undefined): string {
  const folder = (answer ?? '').trim().replace(/[\\/]+$/, '')
  return folder ? `${folder}/bin/${ENGINE}` : HOME_LABEL
}

/** Keeps the probe's answer for the session (the probe is asked once). */
export function learnHome(answer: string | null | undefined): string {
  home = homeShimPath(answer)
  homeRuns = ABSOLUTE.test(home)
  return home
}

/** Whether the probe has been answered. */
export function homeKnown(): boolean {
  return home !== null
}

/** The places that can be run, in the order of MAC-B5: the setting, `tempergraph` on PATH, the shim of the engine home. */
export function enginePlaces(): string[] {
  const places = [...(setting ? [setting] : []), ENGINE, ...(home !== null && homeRuns ? [home] : [])]
  return places.filter((p, i) => places.indexOf(p) === i) // no program is a place twice
}

/** The places a failed lookup names to the person (MDS-B7). */
export function lookedAt(): string[] {
  return [...(setting ? [`engine_path setting: ${setting}`] : []), `PATH: ${ENGINE}`, `engine home: ${home ?? HOME_LABEL}`]
}

/** Makes one place the program of every verb built from here on; refuses a program that is not a place. */
export function useProgram(program: string): boolean {
  if (!enginePlaces().includes(program)) return false
  engine = program
  return true
}

/** Every verb the monitor may run. A verb that writes is never built (MDS-AC-2). */
export const READ_ONLY_VERBS = ['status', 'events', 'stats'] as const
export type ReadOnlyVerb = (typeof READ_ONLY_VERBS)[number]

export const WRITING_VERBS = ['run', 'resume', 'stop', 'batch', 'rerun', 'store', 'hooks', 'update', 'upgrade',
  'install', 'label', 'schedule', 'improve', 'scaffold', 'author', 'workflows', 'supervision'] as const

/** Engine thread ids and session keys are printed by the engine; anything else is refused. */
const THREAD = /^[A-Za-z0-9_][A-Za-z0-9_.-]*\/[A-Za-z0-9_][A-Za-z0-9_.:-]*$/
const UNIT = /^[A-Za-z_][A-Za-z0-9_-]*$/

/** `stats` writes only as `stats flush`, `stats sync` and `--sync` (engine CST-B14, CST-B15, CST-B16); the monitor never asks for those. */
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

/** A schedule id as the engine prints it: a slug and four hex digits (engine SCH). */
const SCHEDULE = /^[a-z0-9][a-z0-9-]{0,58}-[0-9a-f]{4}$/
const WORKFLOW = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/

/**
 * The read-only subcommands of verbs that also write (MDS-B8): each shape is the exact argv after the program, a
 * pattern standing for one value the engine printed. Every other subcommand of `schedule` and `evals` is refused.
 */
export const READ_ONLY_SHAPES: readonly (readonly (string | RegExp)[])[] = [
  ['schedule', 'list', '--json'],
  ['schedule', 'list', '--all', '--json'],
  ['schedule', 'show', SCHEDULE, '--json'],
  ['evals', 'bar', '--json'],
  ['evals', 'bar', WORKFLOW, '--json'],
]

function fits(rest: readonly string[], shape: readonly (string | RegExp)[]): boolean {
  return rest.length === shape.length && shape.every((s, i) => (typeof s === 'string' ? rest[i] === s : s.test(rest[i] ?? '')))
}

/** Every schedule on the machine, for the next slot, last fire and failures (engine SCH). */
export function scheduleListArgv(): readonly string[] {
  return [engine, 'schedule', 'list', '--all', '--json']
}

/** One schedule: its next ten slots and last 20 fires (engine SCH). */
export function scheduleShowArgv(id: string): readonly string[] {
  if (!SCHEDULE.test(id)) throw new Error(`not a schedule id: ${id}`)
  return [engine, 'schedule', 'show', id, '--json']
}

/** Each gate's calibration state (engine JCL-B18), for one workflow or all. */
export function evalsBarArgv(workflow?: string): readonly string[] {
  if (workflow !== undefined && !WORKFLOW.test(workflow)) throw new Error(`not a workflow name: ${workflow}`)
  return [engine, 'evals', 'bar', ...(workflow ? [workflow] : []), '--json']
}

/** An engine verb that only reads, or the constant `ps` listing or engine-home probe of MDS §2.1; nothing else is run. */
export function isReadOnly(argv: readonly string[]): boolean {
  if (argv.length === PS_ARGV.length && argv.every((a, i) => a === PS_ARGV[i])) return true
  if (argv.length === HOME_ARGV.length && argv.every((a, i) => a === HOME_ARGV[i])) return true
  if (argv[0] !== engine) return false
  if (READ_ONLY_SHAPES.some(shape => fits(argv.slice(1), shape))) return true
  if (!(READ_ONLY_VERBS as readonly string[]).includes(argv[1] ?? '')) return false
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

/** `rowDetail`: a live run's detail document is read again this often for its list row, log growth or not. */
export const RATES = { live: 5_000, idle: 30_000, change: 1_000, detail: 2_000, rowDetail: 10_000 } as const

/** How long to wait before the next `status` call. */
export function statusEvery(anyAlive: boolean, paneOpen: boolean): number {
  return anyAlive || paneOpen ? RATES.live : RATES.idle
}
