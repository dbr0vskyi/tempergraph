// The cost tab of a run (MCF §2.1) from the detail document, under contract M4: every figure says `rep` or `est`,
// `≥` when a part is unmeasured, and reported and estimated money are never summed into one figure (MCF-B2).

import type { Attempt, DetailDoc, Session } from './engine'

export type Money = { rep: number; est: number; reported: number; estimated: number; unmeasured: number; sessions: number }

const ZERO: Money = { rep: 0, est: 0, reported: 0, estimated: 0, unmeasured: 0, sessions: 0 }

function add(a: Money, s: Session): Money {
  const u = s.usage ?? {}
  const rep = typeof u.reported_cost_usd === 'number' ? u.reported_cost_usd : null
  const est = typeof u.estimated_cost_usd === 'number' ? u.estimated_cost_usd : null
  return {
    rep: a.rep + (rep ?? 0),
    est: a.est + (rep === null ? (est ?? 0) : 0),
    reported: a.reported + (rep !== null ? 1 : 0),
    estimated: a.estimated + (rep === null && est !== null ? 1 : 0),
    unmeasured: a.unmeasured + (rep === null && est === null ? 1 : 0),
    sessions: a.sessions + 1,
  }
}

/** `$0.22 rep (1 of 3 sessions)` and `$0.95 est` apart; `≥` in front when a session is unmeasured; `—` for none. */
export function figure(m: Money): string {
  if (m.sessions === 0 || m.unmeasured === m.sessions) return '—'
  const floor = m.unmeasured ? '≥ ' : ''
  const parts: string[] = []
  if (m.reported) {
    const partial = m.reported < m.sessions ? ` (${m.reported} of ${m.sessions} sessions)` : ''
    parts.push(`${floor}$${m.rep.toFixed(2)} rep${partial}`)
  }
  if (m.estimated) parts.push(`${floor}$${m.est.toFixed(2)} est`)
  return parts.join(' · ')
}

export function sessionsOf(a: Attempt): Session[] {
  return [...(a.step?.sessions ?? []), ...(a.judge?.sessions ?? [])]
}

export type CostTab = {
  total: string
  completeness: string
  units: { name: string; first: string; repeats: { cause: string; cost: string }[]; share: number | null }[]
  kinds: { kind: string; cost: string }[]
  executors: { key: string; cost: string; tokens: string }[]
  budget: string
  supervision: string
  projection: string
}

const TOKENS = ['input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'thinking_tokens'] as const
const SHORT: Record<(typeof TOKENS)[number], string> = {
  input_tokens: 'in', output_tokens: 'out', cache_read_tokens: 'cache read', cache_write_tokens: 'cache write',
  thinking_tokens: 'thinking' }

export function costTab(d: DetailDoc): CostTab {
  let all = ZERO
  const kinds = new Map<string, Money>()
  const execs = new Map<string, { m: Money; tokens: Record<string, number | null> }>()
  const units = d.units.map(u => {
    let first = ZERO
    const repeats: { cause: string; cost: string }[] = []
    u.visits.forEach((v, vi) => v.attempts.forEach((a, ai) => {
      let here = ZERO
      for (const s of sessionsOf(a)) {
        here = add(here, s)
        all = add(all, s)
        const kind = s.kind === 'retry' ? 're-ask' : (s.kind ?? 'step')
        kinds.set(kind, add(kinds.get(kind) ?? ZERO, s))
        const key = `${s.executor ?? '?'} · ${s.model ?? s.alias ?? 'model not recorded'}`
        const e = execs.get(key) ?? { m: ZERO, tokens: {} }
        e.m = add(e.m, s)
        for (const t of TOKENS) {
          const n = s.usage?.[t]
          // a token count the executor did not give stays unrecorded, never 0 (contract M4)
          e.tokens[t] = typeof n === 'number' ? (e.tokens[t] ?? 0) + n : (e.tokens[t] ?? null)
        }
        execs.set(key, e)
      }
      if (vi === 0 && ai === 0) first = here
      else repeats.push({ cause: a.repeat_cause ?? (ai === 0 ? `visit ${v.visit} (${v.entered_from})` : 'retry'), cost: figure(here) })
    }))
    return { name: u.name, first: figure(first), repeats, share: u.share ?? null }
  })
  const cap = d.budgets?.run_cost_cap
  const burn = d.health?.burn_usd_per_h
  const eta = d.health?.cap_eta_min
  const budget = cap?.limit != null
    ? `$${(cap.left ?? 0).toFixed(2)} left of $${cap.limit.toFixed(2)}`
      + (burn != null && eta != null ? ` · ~${Math.round(eta)} min at $${burn.toFixed(0)}/h` : '')
    : `no run cost cap${burn != null && d.health?.alive ? ` · burn $${burn.toFixed(2)}/h` : ''}`
  const flag = d.run.cost?.completeness ?? (all.unmeasured ? 'incomplete' : all.estimated ? 'estimated' : 'complete')
  return {
    total: figure(all),
    completeness: flag,
    units,
    kinds: [...kinds].map(([kind, m]) => ({ kind, cost: figure(m) })),
    executors: [...execs].map(([key, e]) => ({ key, cost: figure(e.m),
      tokens: TOKENS.map(t => `${SHORT[t]} ${e.tokens[t] ?? '—'}`).join(' · ') })),
    budget,
    supervision: supervisionText(d),
    projection: 'unavailable',
  }
}

function usd(f: { estimated_usd?: number | null } | undefined): string {
  return typeof f?.estimated_usd === 'number' ? `$${f.estimated_usd.toFixed(2)} est` : 'unpriced'
}

/** The supervision line (MCF §2.1): marginal and turn apart, each category named, never `0` when unmeasured. */
export function supervisionText(d: DetailDoc): string {
  const s = d.supervision
  const level = s?.level ? `level ${s.level} · ` : ''
  const c = s?.cost
  if (!c || !c.completeness) return s?.level ? `${level}cost not recorded` : 'not recorded'
  if (!c.marginal || !c.turn) return `${level}cost not measured (${c.completeness})`
  const cats = Object.entries(c.marginal.by_category ?? {}).map(([k, f]) => `${k} ${usd(f)}`).join(', ')
  return `${level}marginal ${usd(c.marginal.total)} · turn ${usd(c.turn.total)} · ${c.completeness}` +
    (cats ? ` (${cats})` : '')
}
