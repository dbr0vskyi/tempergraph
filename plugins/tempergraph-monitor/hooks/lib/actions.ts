// What a person can do from the monitor (MAC §2.1), as pure functions: each returns the text the prompt is filled
// with, built only from values the engine printed and the mod's constants (contract M2, MAC-B4). Nothing here
// runs a command; the person sends what was filled.

import type { DetailDoc, Pause, Session, StatusRow } from './engine'

/** A token the engine printed that may go into a command: no space, quote or shell character. */
const SAFE = /^-{0,2}[A-Za-z0-9_][A-Za-z0-9_.:/@+-]*$/
const DECISION = /^[a-z_]+(?::[A-Za-z0-9_-]+)?$/
const PLACEHOLDER = /<[a-z_:|A-Za-z0-9-]+>/

function safe(token: string): string {
  if (!SAFE.test(token)) throw new Error(`not an engine value: ${token}`)
  return token
}

export type Fill = { label: string; text: string; hotkey?: string }

/**
 * One resume fill per decision word of the pause (MAC-B1), from the resume line the engine printed
 * (`tempergraph resume <workflow> <task> --decision <a|b|c>`): the placeholder is replaced by the word.
 */
export function resumeFills(pause: Pause | null | undefined): Fill[] {
  if (!pause?.resume?.length || !pause.decisions?.length) return []
  const line = pause.resume[0]!
  const tokens = line.split(/\s+/).filter(Boolean)
  if (tokens[0] !== 'tempergraph' || tokens[1] !== 'resume') return []
  const at = tokens.findIndex(t => PLACEHOLDER.test(t))
  const head = (at >= 0 ? tokens.slice(0, at) : tokens).map(safe)
  if (at < 0 && head[head.length - 1] !== '--decision') head.push('--decision')
  return pause.decisions.filter(d => DECISION.test(d)).map((word, i) => ({
    label: `resume: ${word}`,
    text: `!${[...head, word].join(' ')}`,
    hotkey: i < 9 ? String(i + 1) : undefined,
  }))
}

/** Stop fills for a run (MAC §2.1): drain first, `--now` as the second choice. */
export function stopFills(row: Pick<StatusRow, 'thread_id'>): Fill[] {
  const tid = safe(row.thread_id)
  return [
    { label: 'stop (drain)', text: `!tempergraph stop ${tid}`, hotkey: 'x' },
    { label: 'stop now', text: `!tempergraph stop ${tid} --now` },
  ]
}

/** Hands the pause to the run driver skill with its resume context (MAC §2.1, SHL). */
export function driverFill(d: DetailDoc): Fill | null {
  if (!d.pause) return null
  const tid = safe(d.run.thread_id)
  const unit = d.pause.unit ? safe(d.pause.unit) : 'the gate'
  return { label: 'ask the run driver', text: `/tempergraph:run ${tid} is paused at ${unit}; walk me through the decision.` }
}

/** "Ask Claude about a session": names the session's engine transcript and the attempt's gate (MAC §2.1). */
export function askFill(s: Session, unit: string, attempt: number | null, verdict: string | null | undefined): Fill | null {
  const path = s.transcript?.engine
  if (!path) return null
  const kind = s.kind === 'judge' ? 'the judge' : 'the step'
  const why = verdict ? ` returned ${safe(verdict)}` : ' did what it did'
  return { label: 'ask Claude about this session',
    text: `Read ${path} and explain why ${kind} of ${safe(unit)} attempt ${attempt ?? 1}${why}.` }
}
