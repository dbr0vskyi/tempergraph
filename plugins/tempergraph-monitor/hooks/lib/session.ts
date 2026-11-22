// The session view's Calls, Processes and Log tabs (MDD §2.4), as pure functions over what the mod read:
// the activity journal (engine EVT-B17, EVT-B18, EVT-B7, EVT-B19), a `ps` listing with constant argv, and the tails of local logs.

import { clip, duration } from './model'

export type CallRow = { time: string; name: string; summary: string | null; ok: boolean | null; took: string;
  sub: boolean; open: boolean }

/**
 * Tool calls from the activity journal, oldest first: each `tool_started` paired with its `tool_finished` by
 * `call_id`. A call with no finish yet is open. Lines that do not parse, and every other event, are skipped.
 */
export function callsFrom(journal: string, showInputs: boolean): CallRow[] {
  const rows: CallRow[] = []
  const open = new Map<string, CallRow>()
  for (const line of journal.split('\n')) {
    if (!line.trim()) continue
    let ev: Record<string, unknown>
    try {
      ev = JSON.parse(line) as Record<string, unknown>
    } catch {
      continue
    }
    if (ev.ev === 'tool_started') {
      const row: CallRow = {
        time: duration(typeof ev.t === 'number' ? ev.t : null),
        name: String(ev.name ?? '?'),
        summary: showInputs && typeof ev.input_summary === 'string' ? clip(ev.input_summary, 120) : null,
        ok: null, took: '', sub: ev.subagent === true, open: true,
      }
      rows.push(row)
      open.set(String(ev.call_id ?? rows.length), row)
    } else if (ev.ev === 'tool_finished') {
      const row = open.get(String(ev.call_id ?? ''))
      if (!row) continue
      row.ok = typeof ev.ok === 'boolean' ? ev.ok : null
      row.took = duration(typeof ev.duration_s === 'number' ? ev.duration_s : null)
      row.open = false
      open.delete(String(ev.call_id ?? ''))
    } else if (ev.ev === 'truncated') {
      rows.push({ time: '', name: 'journal cut at its cap; tool lines kept', summary: null, ok: null, took: '',
        sub: false, open: false })
    }
  }
  return rows
}

export function callText(r: CallRow): string {
  const mark = r.open ? '▶' : r.ok === false ? '✗' : r.ok ? '✓' : '·'
  return `${r.sub ? '  ' : ''}${mark} ${r.time.padStart(4)} ${r.name}${r.summary ? ` · ${r.summary}` : ''}${r.took ? `  ${r.took}` : ''}`
}

/** The constant argv of MDS §2.1: program names only, never arguments (MDD §5). */
export const PS_ARGV = ['ps', '-A', '-o', 'pid=,pgid=,ppid=,etime=,comm='] as const

export type ProcRow = { pid: number; ppid: number; elapsed: string; program: string; depth: number }

/** The session's process group as a tree, from `ps` output; nothing outside `pgid` is kept (MDD-AC-3). */
export function processTree(ps: string, pgid: number): ProcRow[] {
  const procs = ps.split('\n').map(l => l.trim().split(/\s+/)).filter(f => f.length >= 5)
    .map(([pid, group, ppid, etime, ...comm]) => ({ pid: Number(pid), pgid: Number(group), ppid: Number(ppid),
      elapsed: etime!, program: (comm.join(' ').split('/').pop() ?? '').slice(0, 40) }))
    .filter(p => p.pgid === pgid && Number.isFinite(p.pid))
  const ids = new Set(procs.map(p => p.pid))
  const out: ProcRow[] = []
  const walk = (parent: number | null, depth: number) => {
    for (const p of procs.filter(x => (parent === null ? !ids.has(x.ppid) : x.ppid === parent))) {
      out.push({ pid: p.pid, ppid: p.ppid, elapsed: p.elapsed, program: p.program, depth })
      if (depth < 12) walk(p.pid, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

export function procText(p: ProcRow): string {
  return `${'  '.repeat(p.depth)}${p.program} (${p.pid}) ${p.elapsed}`
}

/** The last lines of a log read from its end; a first line cut by the read is dropped. Text only (MDD §5). */
export function tailLines(text: string, cut: boolean, n = 40): string[] {
  const lines = text.split('\n')
  if (cut) lines.shift()
  return lines.filter(l => l.length).slice(-n).map(l => clip(l, 200))
}

export const LOG_TAIL_BYTES = 64 * 1024
