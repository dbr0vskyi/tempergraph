"""The `host` layer (AUD): this machine and the target repository (ARC-B10, PRA-B7 to PRA-B10).

Read-only. The only child processes are the executor probes of `executors --probe` and the host-speed
probe, under a total budget of 30 s (AUD-B11, AUD-B6, AUD-B9); both are injectable so tests start none.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import executor_compat
from tempergraph.audit.catalog import PARAMS, rule
from tempergraph.audit.report import AuditFinding
from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.launcher import ShellTiming, shell_timing
from tempergraph.model.prompt_lint import TICKED, names
from tempergraph.model.text import TextUnreadable, load_text, split_judge_file
from tempergraph.run.commands import REPO_FILE, REPOSITORY, repository_commands

P = {k: v.default for k, v in PARAMS.items()}

# Documented command sources of a repository and the programs that cover each (ARC toolchain-not-covered).
TOOLCHAINS: dict[str, frozenset[str]] = {
    "package.json": frozenset({"npm", "npx", "yarn", "pnpm", "node", "bun"}),
    "Makefile": frozenset({"make"}),
    "pyproject.toml": frozenset({"python", "python3", "pytest", "uv", "ruff", "mypy", "hatch", "tox", "nox",
                                 "poetry", "pip"}),
    "go.mod": frozenset({"go"}),
    "Cargo.toml": frozenset({"cargo"}),
}


@dataclass(kw_only=True)
class HostInputs:
    target: Path
    probe: Callable[[str], str | None]  # executor -> probed version, None when the probe failed
    timing: Callable[[float], ShellTiming | None] = shell_timing
    which: Callable[[str], str | None] = shutil.which
    plugin_cache: Path | None = None
    stamp: dict[str, Any] | None = None  # the package's last `stamp.json`
    skipped: list[dict[str, Any]] = field(default_factory=list)


class Host:
    def __init__(self, spec: WorkflowSpec, decl_file: str, inputs: HostInputs) -> None:
        self.spec, self.decl, self.i = spec, decl_file, inputs
        self.found: list[AuditFinding] = []
        self.deadline = time.monotonic() + P["probe_budget_s"]

    def add(self, rule_id: str, unit: str | None, statement: str, *, item: str | None = None,
            evidence: dict[str, Any] | None = None, file: str | None = None, session: str | None = None) -> None:
        r = rule(rule_id)
        self.found.append(AuditFinding(rule=r.id, layer="host", severity=r.severity, confidence=r.confidence,
                                       cause=r.cause, unit=unit, item=item, session=session, statement=statement,
                                       evidence=evidence or {}, remedy=r.remedy,
                                       location={"file": file or self.decl}))

    def skip(self, rule_id: str, reason: str) -> None:
        self.i.skipped.append({"rule": rule_id, "reason": reason})

    def left(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    # -- programs and toolchains (C2) ---------------------------------------------------------------
    def prefixes(self) -> list[tuple[str | None, str]]:
        out: list[tuple[str | None, str]] = [(None, c) for c in self.spec.allow_commands]
        for name in self.spec.order:
            u = self.spec.units.get(name)
            if u is not None and u.step is not None:
                out += [(name, c) for c in u.step.commands]
        return out

    def commands(self) -> None:
        if self.spec.command_resolver is not None:
            reason = "command_resolver output is not read in release 1"
            self.skip("check-program-missing", reason)
            self.skip("toolchain-not-covered", reason)
            return
        programs: dict[str, str | None] = {}
        declared: set[str] = set()  # programs that only the target's commands file names (AUD-B18)
        entries = self.prefixes()
        for unit, prefix in entries:
            prog = prefix.split()[0] if prefix.split() else ""
            if prefix == REPOSITORY or not prog:  # the entry is the target's commands, not a program (AUD-B17)
                continue
            if prog not in programs:
                programs[prog] = unit
        if any(prefix == REPOSITORY for _, prefix in entries):
            for prefix in repository_commands(self.i.target):
                prog = prefix.split()[0]
                if prog not in programs:
                    programs[prog] = None
                    declared.add(prog)
        for prog, unit in programs.items():
            if self.i.which(prog) is None:
                self.add("check-program-missing", unit, f"{prog!r} is not on PATH, so commands with that prefix run "
                         "nothing", item=prog, evidence={"program": prog},
                         file=REPO_FILE if prog in declared else None)
        if not self.i.target.is_dir():
            self.skip("toolchain-not-covered", "no target directory")
            return
        documented = documented_commands(self.i.target)
        uses_commands = bool(programs) or any(u.gate.check is not None for u in self.spec.units.values())
        if documented and uses_commands:
            covering = frozenset().union(*(TOOLCHAINS[src] for src in documented))
            if not covering & set(programs):
                cmds = [c for cs in documented.values() for c in cs]
                self.add("toolchain-not-covered", None, "the target documents commands no declared prefix covers: "
                         + ", ".join(cmds[:6]), evidence={"documented": cmds, "declared": sorted(programs)})

    # -- slow host (C2) -----------------------------------------------------------------------------------
    def speed(self) -> None:
        got = self.i.timing(min(self.left(), P["slow_login_shell_s"] + 5))
        if got is None:
            self.skip("slow-host", "probe failed")
            return
        slow = got.login_s > P["slow_login_shell_s"] or (
            got.login_s > P["slow_login_shell_floor_s"] and got.login_s > P["slow_login_shell_ratio"] * got.plain_s)
        if slow:
            self.add("slow-host", None, f"a login shell takes {got.login_s:.1f} s against {got.plain_s:.2f} s for a "
                     "plain one", evidence={"login_s": round(got.login_s, 2), "plain_s": round(got.plain_s, 3)})

    # -- executor versions (owned: LIF executor compatibility) ---------------------------------------------
    def executors(self) -> None:
        used = []
        for name in self.spec.order:
            u = self.spec.units.get(name)
            if u is not None and u.step is not None:
                used.append(u.step.executor or self.spec.default_executor)
            if u is not None and u.gate.judge is not None and u.gate.judge.executor:
                used.append(u.gate.judge.executor)
        for ex in dict.fromkeys(used):
            if self.left() <= 0:
                self.skip("executor-outside-tested-range", "probe failed: the 30 s budget is spent")
                return
            version = self.i.probe(ex)
            if version is None:
                self.skip("executor-outside-tested-range", f"probe failed: {ex}")
                continue
            f = executor_compat.finding(ex, version)
            if f is not None:
                self.found.append(AuditFinding(
                    rule=f"executor-compat:{f.code}", layer="host", severity="warning", confidence="high",
                    owner="executor-compat", item=ex, statement=f.message, evidence={"executor": ex,
                                                                                    "version": version},
                    remedy="Run the executor's contract probes for this version, or pin a tested version (LIF)",
                    location={"file": "tempergraph.json"}))

    # -- names against the host (PRA) -----------------------------------------------------------------------
    def texts(self) -> Iterator[tuple[str, str, str, str]]:
        """(unit, executor, file, text) for each step template and judge text."""
        for name in self.spec.order:
            u = self.spec.units.get(name)
            if u is None:
                continue
            ex = (u.step.executor if u.step else None) or self.spec.default_executor
            st = u.step
            if st is not None and st.prompt != "default":
                text = None
                with contextlib.suppress(TextUnreadable):
                    text = load_text(self.spec, st.prompt)
                if text is not None:
                    yield name, ex, (st.prompt.path if isinstance(st.prompt, TextRef) else self.decl), text
            j = u.gate.judge
            if j is not None:
                text = f"{j.stance}\n{j.brief}"
                if j.file and self.spec.package_root is not None:
                    try:
                        text = "\n".join(split_judge_file(load_text(self.spec, TextRef(path=j.file))))
                    except TextUnreadable:
                        continue
                yield name, j.executor or ex, j.file or self.decl, text

    def references(self) -> None:
        root = self.spec.package_root
        installed = installed_skills(self.i.plugin_cache)
        own = {p.parent.name for p in (root / "skills").glob("*/SKILL.md")} if root else set()
        seen: set[str] = set()
        for unit, _ex, file, text in self.texts():
            for skill in names(text).skills:
                plugin, _, bare = skill.rpartition(":")
                if skill in seen or (plugin and plugin in installed.get(bare, ())):
                    continue
                seen.add(skill)
                others = sorted(installed.get(bare, ()))
                if (bare not in own and others) or len(others) > 1:
                    self.add("ref-resolves-elsewhere", unit, f"skill {bare!r} is "
                             + ("not shipped with the workflow and is found in " if bare not in own
                                else "also found in ") + ", ".join(others), item=bare, file=file,
                             evidence={"plugins": others})

    def stale_tools(self) -> None:
        stamped = (self.i.stamp or {}).get("tool_set")
        renamed = {ex: dict((executor_compat.table().get(ex) or {}).get("renamed") or {}) for ex in DECLARED}
        if not isinstance(stamped, dict) and not any(renamed.values()):
            self.skip("tool-name-stale", "no stamp and no renamed tools in the compatibility table")
            return
        for unit, ex, file, text in self.texts():
            current = {t for ts in DECLARED.get(ex, DECLARED["claude"]).tool_map.values() for t in ts}
            before = set((stamped or {}).get(ex) or ()) if isinstance(stamped, dict) else set()
            for tok in dict.fromkeys(TICKED.findall(text)):
                new = renamed.get(ex, {}).get(tok)
                if new or (tok in before and tok not in current):
                    self.add("tool-name-stale", unit, f"`{tok}` is no longer a {ex} tool name"
                             + (f"; it is now `{new}`" if new else " (it was at the last stamp)"),
                             item=tok, file=file, evidence={"executor": ex, "name": tok, **({"now": new} if new else {})})

    def run(self) -> list[AuditFinding]:
        for rid in ("interpreter-cannot-import", "worktree-env-outside-worktree"):
            self.skip(rid, "no declared interpreter in release 1 (WFM declares none)")
        self.skip("tool-name-unknown", "owned by prompt lint `lint-tool-name-foreign`; MCP names need the view "
                  "catalog of TSA (release 2)")
        for part in (self.commands, self.executors, self.speed, self.references, self.stale_tools):
            part()
        return self.found


def documented_commands(target: Path) -> dict[str, list[str]]:
    """Source file -> the commands it documents (package.json scripts, Makefile targets, and the presence of
    pyproject.toml, go.mod and Cargo.toml)."""
    out: dict[str, list[str]] = {}
    pkg = target / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except (OSError, ValueError, AttributeError):
            scripts = {}
        if isinstance(scripts, dict) and scripts:
            out["package.json"] = [f"package.json scripts.{k}" for k in sorted(scripts)]
    mk = target / "Makefile"
    if mk.is_file():
        try:
            targets = [line.split(":")[0] for line in mk.read_text(encoding="utf-8", errors="replace").splitlines()
                       if line and not line[0].isspace() and ":" in line and not line.startswith(("#", "."))
                       and "=" not in line.split(":")[0]]
        except OSError:
            targets = []
        if targets:
            out["Makefile"] = [f"make {t.strip()}" for t in targets[:10]]
    for name in ("pyproject.toml", "go.mod", "Cargo.toml"):
        if (target / name).is_file():
            out[name] = [name]
    return out


def installed_skills(cache: Path | None) -> dict[str, set[str]]:
    """Skill name -> installed plugins that ship it (newest non-orphaned version of each plugin)."""
    from tempergraph.package.registry import _version_key, plugin_cache

    root = cache or plugin_cache()
    out: dict[str, set[str]] = {}
    if not root.is_dir():
        return out
    for market in sorted(p for p in root.iterdir() if p.is_dir()):
        for plugin in sorted(p for p in market.iterdir() if p.is_dir()):
            versions = [v for v in plugin.iterdir() if v.is_dir() and not (v / ".orphaned_at").exists()]
            if not versions:
                continue
            newest = max(versions, key=lambda v: _version_key(v.name))
            for s in newest.glob("skills/*/SKILL.md"):
                out.setdefault(s.parent.name, set()).add(plugin.name)
    return out
