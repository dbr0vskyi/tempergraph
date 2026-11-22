"""The C4 rules of the tool surface audit (TSA-B1, TSA-B2, TSA-B4, TSA-B9 to TSA-B13) and the matrix of `audit tools`
(TSA-B3, TSA-B5, TSA-B8).

Every rule reads the session surface built once by `audit.surface` (the executors' tool maps, the manifest, and the
recorded use when there is history), the host facts the caller passes in (read-only) and `HistoryFacts`; nothing is
written and no model is asked. A remedy that adds a grant (a command or a tool) is marked widening: the finding
carries `widening` and its remedy starts with `Widens the grant:` (TSA-B13); a remedy that removes one is plain
advice. The matrix and the findings read one surface, so they cannot disagree.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tempergraph import executor_compat
from tempergraph.audit.catalog import PARAMS, rule
from tempergraph.audit.history import HistoryFacts
from tempergraph.audit.history_rules import RuleSkipped
from tempergraph.audit.host import installed_skills
from tempergraph.audit.report import AuditFinding
from tempergraph.audit.surface import (
    CLASSES,
    SessionSurface,
    Surface,
    caps_of,
    read_names,
    step_text,
)
from tempergraph.contracts import Capabilities, WorkflowSpec
from tempergraph.executors.capabilities import tool_names

P = {k: v.default for k, v in PARAMS.items()}
DIR_CHANGE_TEXT = re.compile(r"\bcd\s+\S+\s*(?:&&|;)")
SHELL_READ_TEXT = re.compile(r"\b(?:use|run|via|using|with)\s+`?(?:cat|head|tail|grep|rg|find|ls)\b", re.I)
OUTSIDE_TEXT = re.compile(r"(?<![\w./-])(?:/(?:etc|usr|var|home|root|tmp|opt|mnt|Users)\b[\w./-]*|\.\./[\w./-]*)")
# How an executor holds the grant it was given: only with a run flag, by construction, or by what a probe finds.
ENFORCEMENT = {"claude": "flag", "agent-sdk": "always", "messages-api": "construction", "antigravity": "probe"}
FIX = {
    "shell_for_read": "use the file tools to read and search",
    "dir_change_then_command": "name the directory to the command (`git -C <dir>`)",
    "outside_workspace": "use paths inside the workspace",
    "undeclared_tool": "declare the tool",
    "needed_command": "declare the command or add it to the resolver",
}
WIDENING_CLASSES = frozenset({"undeclared_tool", "needed_command"})
AmbientProbe = Callable[[str], list[str] | None]
ConfiguredServers = Callable[[], set[str] | None]


def enforcement(caps: Capabilities) -> str:
    """`always`, `construction`, `flag`, `probe` or `never`: when the executor holds a step's grant."""
    if not caps.enforces_step_tools:
        return "never"
    return ENFORCEMENT.get(caps.name, "always")


def current_names(caps: Capabilities) -> set[str]:
    return {n for names in caps.tool_map.values() for n in names if "{" not in n}


class ToolRules:
    def __init__(self, spec: WorkflowSpec, surface: Surface, caps: Mapping[str, Capabilities], decl: str, *,
                 stamp: dict[str, Any] | None = None, plugin_cache: Any = None,
                 mcp_servers: ConfiguredServers | None = None, ambient_tools: AmbientProbe | None = None) -> None:
        self.spec, self.surface, self.caps, self.decl = spec, surface, caps, decl
        self.stamp, self.plugin_cache = stamp, plugin_cache
        self.mcp_servers, self.ambient_tools = mcp_servers, ambient_tools
        self.found: list[AuditFinding] = []
        self.skipped: list[dict[str, Any]] = []
        self.facts: HistoryFacts | None = None

    # -- helpers -------------------------------------------------------------------------------------------------
    def add(self, rule_id: str, unit: str | None, statement: str, *, session: str | None = None,
            item: str | None = None, evidence: dict[str, Any] | None = None, field: str | None = None,
            remedy: str | None = None, widening: bool | None = None, cause: str | None = None) -> None:
        """One finding with the catalog's record; a widening remedy is marked and its text says so (TSA-B13)."""
        r = rule(rule_id)
        wide = r.widening if widening is None else widening
        ev = dict(evidence or {})
        if r.layer == "history" and self.facts is not None:
            ev.update(n=self.facts.runs, window_days=self.facts.window_days)
        loc: dict[str, Any] = {"file": self.decl}
        if field:
            loc["field"] = field
        text = remedy or r.remedy
        self.found.append(AuditFinding(
            rule=r.id, layer=r.layer, severity=r.severity, confidence=r.confidence,
            cause=cause or r.cause, unit=unit, item=item, session=session, statement=statement, evidence=ev,
            remedy=("Widens the grant: " + text) if wide else text, widening=wide,
            location=loc if r.layer != "history" else {}))

    def skip(self, rule_id: str, reason: str) -> None:
        self.skipped.append({"rule": rule_id, "reason": reason})

    def steps(self) -> list[SessionSurface]:
        return [s for s in self.surface.sessions if s.role == "step"]

    def judges(self) -> list[SessionSurface]:
        return [s for s in self.surface.sessions if s.role == "judge"]

    # -- definition: grant and need (TSA-B10) ----------------------------------------------------------------------
    def definition(self) -> list[AuditFinding]:
        start = len(self.found)
        for s in self.steps():
            u = self.spec.units[s.unit]
            st = u.step
            if st is None:
                continue
            text = step_text(self.spec, s.unit)
            field = f"units.{s.unit}.step.tools"
            for key in s.artifacts_unwritable:
                self.add("artifact-needs-write", s.unit, f"{s.unit} produces {key!r} ({s.produces[key]}) and declares "
                         "no tool that can write it", session="step", item=key, evidence={"artifact": key,
                                                                                         "kind": s.produces[key]},
                         field=f"units.{s.unit}.step.produces.{key}")
            if "shell" in st.tools and not st.commands:
                self.add("shell-without-commands", s.unit, f"{s.unit} declares `shell` with no command prefix",
                         session="step", field=f"units.{s.unit}.step.commands")
            offenders = [c for c in st.commands if re.search(r"\bcd\b", c)]
            if m := DIR_CHANGE_TEXT.search(text):
                offenders.append(m.group(0))
            for off in offenders:
                self.add("dir-change-in-commands", s.unit, f"{s.unit} changes directory before a command ({off!r})",
                         session="step", item=off, field=f"units.{s.unit}.step.commands")
            if "shell" in st.tools and {"read", "search"} & set(st.tools) and (m := SHELL_READ_TEXT.search(text)):
                self.add("shell-for-read-likely", s.unit, f"the text of {s.unit} tells the step to read or search "
                         f"through shell programs ({m.group(0)!r}) while file tools are granted", session="step",
                         evidence={"text": m.group(0)}, field=field)
            outside = OUTSIDE_TEXT.search(text) or next((m for c in st.commands if (m := OUTSIDE_TEXT.search(c))),
                                                        None)
            if outside:
                self.add("path-outside-workspace", s.unit, f"{s.unit} names the path {outside.group(0)!r}, outside "
                         "the workspace", session="step", item=outside.group(0))
            sc = caps_of(self.caps, s.executor)
            for cap in st.tools:
                names = tool_names(sc, cap) if sc else ()
                if names and not any(n in s.needed for n in names):
                    self.add("granted-not-needed", s.unit, f"{s.unit} grants {cap!r}, which its text and artifacts "
                             "never ask for", session="step", item=cap, field=field)
            if sc is not None and st.tools and enforcement(sc) == "never":
                self.add("not-enforced", s.unit, f"{s.executor} cannot hold {s.unit}'s grant; the step may call "
                         "any tool", session="step", item=s.executor,
                         evidence={"executor": s.executor, "enforcement": enforcement(sc)})
            self._catalog(s, st.tools)
        return self.found[start:]

    def _catalog(self, s: SessionSurface, tools: tuple[str, ...]) -> None:
        """TSA-B10: a declared MCP tool the view catalog does not classify, or whose judge's executor has no MCP
        view: either way its judge gets no view of it."""
        from tempergraph.executors.viewcatalog import read_views

        judge = self.surface.get(f"{s.unit}:judge")
        jc = caps_of(self.caps, judge.executor) if judge else None
        if jc is None:
            return
        for cap in tools:
            if cap.startswith("mcp:") and (not jc.judge_mcp or not read_views(cap)):
                self.add("mcp-tool-not-in-catalog", s.unit, f"{cap} is declared on {s.unit}, but its judge on "
                         f"{judge.executor if judge else '?'} gets no view of it", session="judge", item=cap,
                         field=f"units.{s.unit}.step.tools")

    # -- host (TSA-B9, TSA-B12) ----------------------------------------------------------------------------------
    def host(self) -> list[AuditFinding]:
        start = len(self.found)
        self._ambient()
        self._clash()
        self._servers()
        self._stale()
        self._drift()
        return self.found[start:]

    def _ambient(self) -> None:
        if self.ambient_tools is None:
            self.skip("judge-ambient-tool", "probe cannot list")
            return
        for s in self.judges():
            listed = self.ambient_tools(s.executor)
            if listed is None:
                self.skip("judge-ambient-tool", "probe cannot list")
                return
            for name in listed:
                if name not in s.granted:
                    self.add("judge-ambient-tool", s.unit, f"a judge on {s.executor} would hold {name!r}, outside its "
                             "view set", session="judge", item=name, evidence={"tool": name,
                                                                                  "executor": s.executor})

    def _clash(self) -> None:
        installed = installed_skills(self.plugin_cache)
        seen: set[str] = set()
        for s in self.steps():
            for skill in read_names(step_text(self.spec, s.unit)).skills:
                bare = skill.rpartition(":")[2]
                plugins = sorted(installed.get(bare, ()))
                if skill == bare and len(plugins) > 1 and bare not in seen:
                    seen.add(bare)
                    self.add("skill-name-clash", s.unit, f"skill {bare!r} is installed in {len(plugins)} plugins "
                             f"({', '.join(plugins)}); also found by `ref-resolves-elsewhere`", session="step",
                             item=bare, evidence={"plugins": plugins})

    def _servers(self) -> None:
        declared: dict[str, str] = {}
        for s in self.steps():
            for cap in s.capabilities:
                if cap.startswith("mcp:"):
                    declared.setdefault(cap[4:].partition("/")[0], s.unit)
        if not declared:
            return
        have = self.mcp_servers() if self.mcp_servers is not None else None
        if have is None:
            self.skip("mcp-server-not-configured", "probe cannot list")
            return
        for server, unit in declared.items():
            if server not in have:
                self.add("mcp-server-not-configured", unit, f"`mcp:{server}` is declared but your configuration has "
                         f"no server named {server!r}", session="step", item=server, evidence={"server": server})

    def _stale(self) -> None:
        table = executor_compat.table()
        for s in self.steps():
            renamed = dict((table.get(s.executor) or {}).get("renamed") or {})
            for name in s.granted:
                if name in renamed:
                    self.add("declared-tool-stale", s.unit, f"{name!r} is no longer a {s.executor} tool name; it is "
                             f"now {renamed[name]!r}", session="step", item=name,
                             evidence={"executor": s.executor, "now": renamed[name]})

    def _drift(self) -> None:
        stamped = (self.stamp or {}).get("tool_set")
        if not isinstance(stamped, dict):
            self.skip("tool-set-drift", "no stamp")
            return
        for ex in dict.fromkeys(s.executor for s in self.surface.sessions):
            caps, before = caps_of(self.caps, ex), stamped.get(ex)
            if caps is None or before is None:
                continue
            now = current_names(caps)
            if now != set(before):
                self.add("tool-set-drift", None, f"the tool names of {ex} differ from the last stamp", item=ex,
                         evidence={"executor": ex, "added": sorted(now - set(before)),
                                   "removed": sorted(set(before) - now)})

    # -- history (TSA-B1, TSA-B9, TSA-B11) ------------------------------------------------------------------------
    def with_history(self, facts: HistoryFacts) -> ToolRules:
        self.facts = facts
        return self

    def judge_exposed_tool(self) -> list[AuditFinding]:
        for s in self.judges():
            for name in sorted(s.ambient):
                runs = s.ambient_runs.get(name, [])
                called = (s.used or {}).get(name, {}).get("calls", 0)
                self.add("judge-exposed-tool", s.unit, f"the judge session of {s.unit} listed {name!r} at start, "
                         f"outside its view set, in {len(runs)} runs; "
                         + ("never called" if not called else f"called {called} times"), session="judge", item=name,
                         evidence={"tool": name, "runs": runs, "called": called})
        return self.found

    def granted_never_used(self) -> list[AuditFinding]:
        for s in self.steps():
            used = s.used or {}
            sc = caps_of(self.caps, s.executor)
            for cap in dict.fromkeys(s.capabilities):
                names = tool_names(sc, cap) if sc is not None else ()
                if names and not any(used.get(n, {}).get("calls", 0) for n in names):
                    self.add("granted-never-used", s.unit, f"{cap!r} is declared on {s.unit} and was never called",
                             session="step", item=cap, evidence={"capability": cap, "tools": list(names)})
        return self.found

    def undeclared_calls(self) -> list[AuditFinding]:
        runs = self.facts.runs if self.facts else 0
        for s in self.steps():
            outside = {n: row["calls"] for n, row in (s.used or {}).items() if n not in s.granted and row["calls"]}
            total = sum(outside.values())
            if runs and total / runs >= 0.25:
                self.add("undeclared-calls", s.unit, f"{s.unit} called {total} tools outside its grant over {runs} "
                         f"runs", session="step", evidence={"tools": outside, "per_run": round(total / runs, 2)})
        return self.found

    def refusals_by_class(self) -> list[AuditFinding]:
        facts = self.facts
        if facts is None or (facts.runs and facts.journal_runs == 0):
            raise RuleSkipped("unclassified: no run has an activity journal")
        for s in self.steps():
            if not isinstance(s.refusals, dict) or not s.refusals:
                continue
            total = sum(s.refusals.values())
            if total / max(facts.runs, 1) < 1:
                continue
            ranked = sorted(s.refusals.items(), key=lambda kv: (-kv[1], CLASSES.index(kv[0])
                                                              if kv[0] in CLASSES else 99))
            fixes = []
            for klass, _ in ranked:
                fix = FIX.get(klass, "read the refusal's input summary")
                if klass == "needed_command" and s.refusal_examples.get(klass):
                    fix = f"declare `{s.refusal_examples[klass]}` or add it to the resolver"
                fixes.append(fix)
            wide = any(k in WIDENING_CLASSES for k, _ in ranked)
            self.add("refusals-by-class", s.unit, f"{s.unit} was refused {total} calls over {facts.runs} runs, "
                     f"most often as {ranked[0][0]}", session="step", cause=ranked[0][0], widening=wide,
                     evidence={"classes": dict(ranked), "per_run": round(total / max(facts.runs, 1), 2)},
                     remedy="; then ".join(fixes))
        return self.found

    def granted_at_run(self) -> list[AuditFinding]:
        facts = self.facts
        if facts is None:
            return self.found
        runs: dict[tuple[str, str], set[str]] = {}
        for g in facts.grants:
            if not g.capability or g.action in ("remove", "revoke", "deny"):
                continue
            for r in facts.sessions:
                if r.run == g.run and r.unit == g.unit and not r.judge and any(
                        c.capability == g.capability for c in r.calls):
                    runs.setdefault((g.unit, str(g.capability)), set()).add(g.run)
        for (unit, cap), rs in sorted(runs.items()):
            if len(rs) >= 2:
                self.add("granted-at-run", unit, f"a grant of {cap!r} was given and used on {unit} in {len(rs)} runs",
                         session="step", item=cap, evidence={"capability": cap, "runs": sorted(rs)})
        return self.found


TOOL_HISTORY: dict[str, Callable[[ToolRules], list[AuditFinding]]] = {
    "judge-exposed-tool": ToolRules.judge_exposed_tool, "granted-never-used": ToolRules.granted_never_used,
    "undeclared-calls": ToolRules.undeclared_calls, "refusals-by-class": ToolRules.refusals_by_class,
    "granted-at-run": ToolRules.granted_at_run,
}


COLUMNS = (("session", "Session"), ("tool", "Tool"), ("capability", "Capability"), ("granted", "Granted"),
           ("needed", "Needed"), ("used", "Used"), ("verdict", "Verdict"))


def _verdict(s: SessionSurface, name: str, stale: set[str | None]) -> str:
    """TSA-B8: `missing` (needed, not granted), `exposed` (ambient, or called without a grant), `refused`, `drift`
    (renamed or retired), `unused` (granted, never named and never called), else `ok`."""
    row = (s.used or {}).get(name, {})
    granted = name in s.granted
    if name in s.needed and not granted:
        return "missing"
    if name in s.ambient or (not granted and row.get("calls")):
        return "exposed"
    if row.get("refused"):
        return "refused"
    if name in stale:
        return "drift"
    if granted and name not in s.needed and not row.get("calls"):
        return "unused"
    return "ok"


def matrix(surface: Surface, findings: Sequence[AuditFinding] = ()) -> list[dict[str, Any]]:
    """TSA-B8, TSA-B5: one row per session and tool, from the surface alone; `Used` is `—` without history."""
    stale = {f.item for f in findings if f.rule in ("declared-tool-stale", "tool-set-drift")}
    rows: list[dict[str, Any]] = []
    for s in surface.sessions:
        names = dict.fromkeys([*s.granted, *s.needed, *sorted(s.ambient), *(s.used or {})])
        for name in names:
            used = "—" if s.used is None else "{calls} calls, {refused} refused".format(
                **{"calls": 0, "refused": 0, **s.used.get(name, {})})
            rows.append({"session": s.session, "unit": s.unit, "tool": name,
                         "capability": s.granted.get(name) or s.known.get(name),
                         "granted": "yes" if name in s.granted else "ambient" if name in s.ambient else "no",
                         "needed": f"yes ({s.needed[name]})" if name in s.needed else "no", "used": used,
                         "verdict": _verdict(s, name, stale)})
    return rows


def render_matrix(rows: Sequence[Mapping[str, Any]], fmt: str, *, extra: Mapping[str, Any] | None = None) -> str:
    """The matrix as an aligned text table or as JSON with `extra` keys (the workflow, the skipped history rules)."""
    if fmt == "json":
        return json.dumps({"schema_version": 1, **(extra or {}), "rows": list(rows)}, indent=2,
                          ensure_ascii=False) + "\n"
    cells = [[title for _, title in COLUMNS]] + [[str(r.get(key) or "-") for key, _ in COLUMNS] for r in rows]
    widths = [max(len(c[i]) for c in cells) for i in range(len(COLUMNS))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip() for row in cells]
    skipped = (extra or {}).get("rules_skipped") or []
    if skipped:
        lines += ["", "history rules skipped: " + ", ".join(f"{s['rule']} ({s['reason']})" for s in skipped)]
    return "\n".join(lines) + "\n"


def run_history(tr: ToolRules, rule_id: str, facts: HistoryFacts) -> list[AuditFinding]:
    """One history rule of C4 on the shared surface: only the findings that rule added (`RuleSkipped` passes up)."""
    tr.with_history(facts)
    start = len(tr.found)
    TOOL_HISTORY[rule_id](tr)
    return tr.found[start:]
