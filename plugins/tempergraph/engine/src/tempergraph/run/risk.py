"""Judge model by risk: the rule under its guard, the level of one attempt and stock rules (JRK §2.2, §2.3).

A risk rule only ever raises the judge. It reads model-free facts of the attempt and never the step's text,
artifacts or values; a fault takes the last, strongest level.
"""

from __future__ import annotations

import concurrent.futures
import fnmatch
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.contracts import EFFORTS, JudgeSpec, RiskContext, RiskLevel, RiskSpec
from tempergraph.run.ladder import TIER_RANK, tier

RULE_TIMEOUT_S = 1.0
CHOSEN_BY = ("rule", "fault", "floor", "shadow", "operator")
PIN_KEYS = ("model", "effort")
BASE_LEVEL = "base"  # the name of a judge's one level when it declares no `risk`


@dataclass(frozen=True, kw_only=True)
class RiskGit:
    """`GitFacts` of the attempt plus the size of its diff (JRK §2.2)."""

    branch: str = ""
    base: str = ""
    head: str = ""
    clean: bool = True
    pushed: bool = False
    changed_paths: tuple[str, ...] = ()
    commits_since_base: tuple[str, ...] = ()
    lines_added: int = 0
    lines_removed: int = 0

    def paths_by_glob(self, globs: Sequence[str]) -> int:
        """Changed paths that match any glob; `*` and `**` both cross directories (`src/**`, `**/migrations/*`)."""
        return sum(1 for p in self.changed_paths if any(fnmatch.fnmatchcase(p, g) for g in globs))


def line_counts(workdir: Path, base: str = "") -> tuple[int, int]:
    """Lines added and removed against the base (or `HEAD`), with the lines of untracked files as added."""
    added = removed = 0
    try:
        ref = base if base and gitmod.is_safe_ref(base) else "HEAD"
        for ln in gitmod.git(["diff", "--numstat", ref, "--"], workdir, check=False).splitlines():
            a, r, *_ = (ln.split("\t") + ["", ""])[:3]
            added += int(a) if a.isdigit() else 0
            removed += int(r) if r.isdigit() else 0
        status = gitmod.git(["status", "--porcelain=v1", "--untracked-files=all"], workdir, check=False)
    except gitmod.GitError:
        return added, removed
    for ln in status.splitlines():
        if ln.startswith("??") and not ln[3:].startswith(".tempergraph/"):
            try:
                with open(workdir / ln[3:], "rb") as fh:
                    added += fh.read(2_000_000).count(b"\n")
            except OSError:
                continue
    return added, removed


def git_of(facts: Any, workdir: Path) -> RiskGit:
    if facts is None:  # outside git a rule reads empty git facts; git-based stock rules are refused at start
        return RiskGit()
    added, removed = line_counts(workdir, getattr(facts, "base", "") or "")
    return RiskGit(branch=facts.branch, base=facts.base, head=facts.head, clean=facts.clean, pushed=facts.pushed,
                   changed_paths=tuple(facts.changed_paths), commits_since_base=tuple(facts.commits_since_base),
                   lines_added=added, lines_removed=removed)


def models(risk: RiskSpec, base_model: str | None) -> list[str | None]:
    """The alias of each level: level 0 is the gate's own judge; a level that states none keeps the one before."""
    out: list[str | None] = []
    for i, lv in enumerate(risk.levels):
        out.append(base_model if i == 0 else lv.model or out[-1])
    return out


def efforts(risk: RiskSpec, base_effort: str | None) -> list[str | None]:
    out: list[str | None] = []
    for i, lv in enumerate(risk.levels):
        out.append((lv.effort or base_effort) if i == 0 else lv.effort or out[-1])
    return out


def rank(alias: object) -> int | None:
    return TIER_RANK.get(tier(alias)) if alias else None


def top_rank(j: JudgeSpec | None) -> int:
    """The strongest tier a gate's judge can run on: its own, or its highest risk level's (LAD §2.4 E4)."""
    if j is None:
        return -1
    aliases = models(j.risk, j.model) if j.risk is not None else [j.model]
    ranks = [rank(a) for a in aliases]
    return max(-1 if r is None else r for r in ranks)


def problems(risk: RiskSpec, base_model: str | None, base_effort: str | None) -> list[str]:
    """Why a declaration cannot be used (JRK §2.1, §4)."""
    out: list[str] = []
    names = [lv.name for lv in risk.levels]
    if not 2 <= len(names) <= 3 or len(set(names)) != len(names) or not all(names):
        return ["`levels` takes 2 or 3 levels with distinct names"]
    if (risk.rule is None) == (not risk.when):
        out.append("give exactly one of `rule` and `when`")
    if risk.mode not in ("route", "shadow"):
        out.append(f"`mode` is `route` or `shadow`, not {risk.mode!r}")
    first = risk.levels[0]
    if first.model is not None and first.model != base_model:
        out.append(f"level {first.name!r} is the gate's own judge: it takes no model of its own")
    ms, es = models(risk, base_model), efforts(risk, base_effort)
    for i in range(1, len(names)):
        lv = risk.levels[i]
        if lv.effort is not None and lv.effort not in EFFORTS:
            out.append(f"level {lv.name!r}: {lv.effort!r} is not an effort")
            continue
        if ms[i] != ms[i - 1]:
            a, b = rank(ms[i - 1]), rank(ms[i])
            if a is None or b is None or b < a:
                out.append(f"level {lv.name!r} must be at a tier at or above {ms[i - 1]!r} "
                           "(tier aliases `small`, `medium`, `large`)")
        lower = es[i] is not None and es[i - 1] is not None and EFFORTS.index(es[i]) < EFFORTS.index(es[i - 1])
        if lower:
            out.append(f"level {lv.name!r} lowers the effort of the level before it")
        elif ms[i] == ms[i - 1] and es[i] == es[i - 1]:
            out.append(f"level {lv.name!r} equals the level before it in model and effort")
    for w in risk.when:
        if w.level not in names[1:]:
            out.append(f"`when` names level {w.level!r}, which is not a level above the first")
        if not w.paths and w.min_lines is None and w.fact is None:
            out.append(f"`when` for {w.level!r} needs `paths`, `min_lines` or `fact`")
        if (w.fact is None) != (w.min_fact is None):
            out.append(f"`when` for {w.level!r} takes `fact` and `min_fact` together")
    return out


def _number(v: Any) -> float | None:
    try:
        return None if isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def stock(risk: RiskSpec, ctx: RiskContext) -> tuple[str, dict[str, Any]]:
    """The stock rules: of the levels whose rule holds, the highest; else the first level."""
    names = [lv.name for lv in risk.levels]
    best, signals = 0, {}
    for w in risk.when:
        holds = False
        if w.paths:
            n = ctx.git.paths_by_glob(w.paths)
            signals[f"{w.level}_paths"] = n
            holds = holds or n >= w.min_paths
        if w.min_lines is not None:
            n = int(ctx.git.lines_added) + int(ctx.git.lines_removed)
            signals["lines_changed"] = n
            holds = holds or n >= w.min_lines
        if w.fact is not None and w.min_fact is not None:
            v = _number((ctx.facts.get(w.fact[0]) or {}).get(w.fact[1]))
            if v is None:
                raise LookupError(f"no numeric fact {w.fact[0]}.{w.fact[1]}")
            signals[f"{w.fact[0]}.{w.fact[1]}"] = int(v) if v.is_integer() else v
            holds = holds or v >= w.min_fact
        if holds:
            best = max(best, names.index(w.level))
    return names[best], signals


def run_rule(risk: RiskSpec, ctx: RiskContext) -> dict[str, Any]:
    """The rule's level and signals, or the fault that takes the last level (JRK-B2): a raise, an undeclared
    name, a value of another shape, or more than a second."""
    names = [lv.name for lv in risk.levels]

    def call() -> Any:
        if risk.rule is not None:
            return risk.rule.resolve()(ctx)
        return stock(risk, ctx)

    started = time.monotonic()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        got = pool.submit(call).result(timeout=RULE_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        return {"fault": "timeout", "seconds": round(time.monotonic() - started, 3)}
    except Exception as exc:  # noqa: BLE001 - any raise is a fault, and the run continues
        return {"fault": type(exc).__name__}
    finally:
        pool.shutdown(wait=False)
    name, signals = got if isinstance(got, tuple) and len(got) == 2 else (got, {})
    if not isinstance(name, str) or name not in names:
        return {"fault": "undeclared_level"}
    if not isinstance(signals, Mapping):
        return {"fault": "signals_invalid"}
    clean = {str(k): v for k, v in signals.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool)}
    return {"level": name, "signals": clean}


def resolve(risk: RiskSpec, ran: Mapping[str, Any], *, base_model: str | None, base_effort: str | None,
            pinned: bool = False, producer_rank: int | None = None) -> dict[str, Any]:
    """JRK §2.3: the level that grades one attempt. `ran` is `run_rule`'s result; `producer_rank` is the tier of
    an escalated producer, else None. Returns `{level, would_choose, signals, chosen_by, model, effort}`, with
    `fault` when the rule failed; under an operator pin `model` and `effort` are None (the pin's own)."""
    names = [lv.name for lv in risk.levels]
    ms, es = models(risk, base_model), efforts(risk, base_effort)
    fault = ran.get("fault")
    would = len(names) - 1 if fault else names.index(str(ran["level"]))
    out: dict[str, Any] = {"would_choose": names[would], "signals": dict(ran.get("signals") or {})}
    if fault:
        out["fault"] = fault
        if "seconds" in ran:
            out["seconds"] = ran["seconds"]
    if pinned:
        return {**out, "level": "operator", "chosen_by": "operator", "model": None, "effort": None}
    idx, by = would, "fault" if fault else "rule"
    if risk.mode == "shadow":
        idx, by = 0, "shadow"
    if producer_rank is not None and (rank(ms[idx]) if rank(ms[idx]) is not None else -1) < producer_rank:  # type: ignore[operator]
        idx = next((i for i in range(idx, len(names)) if (rank(ms[i]) or 0) >= producer_rank), len(names) - 1)
        by = "floor"
    return {**out, "level": names[idx], "chosen_by": by, "model": ms[idx], "effort": es[idx]}


def level_named(risk: RiskSpec, name: str) -> RiskLevel | None:
    return next((lv for lv in risk.levels if lv.name == name), None)
