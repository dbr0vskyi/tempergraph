"""The C4 rules of the tool surface audit (TSA-B1 to TSA-B13; TSA-AC1, TSA-AC2, TSA-AC5, TSA-AC6): each raised by a
fixture and quiet on a clean one, with the catalog's severity, confidence and cause, the history ones skipped below
their minimum sample, and every widening remedy marked."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tempergraph.audit import audit
from tempergraph.audit import catalog as cat
from tempergraph.audit.report import AuditReport
from tempergraph.executors.capabilities import DECLARED

from .fixtures.packages import write
from .test_audit import clean_step, ctx, wf
from .test_audit_history import audit_history, many, read
from .test_audit_history_rules import each

Case = tuple[Callable[[Path], AuditReport], Callable[[Path], AuditReport]]
HistCase = tuple[Callable[[Path, int], AuditReport], Callable[[Path, int], AuditReport]]


def tspec(**step_kw: Any) -> Any:
    return wf({"draft": clean_step(**step_kw)}, allow_commands=["pytest"])


def defs(spec: Any, tmp: Path, layers: tuple[str, ...] = ("definition",), **kw: Any) -> AuditReport:
    stamp = kw.pop("stamp", None)
    kw.setdefault("caps", DECLARED)
    return audit(spec, set(layers), ctx(tmp, **kw), stamp=stamp)  # type: ignore[arg-type]


def D(layers: tuple[str, ...] = ("definition",), ctx_kw: dict[str, Any] | None = None, **step_kw: Any
      ) -> Callable[[Path], AuditReport]:
    return lambda tmp: defs(tspec(**step_kw), tmp, layers, **(ctx_kw or {}))


def hits(rep: AuditReport, rule: str) -> list[Any]:
    return [f for f in rep.findings if f.rule == rule]


SHELL = {"tools": ["read", "shell"], "commands": ["pytest"]}
ISSUE = {"produces": {"issue": "tracker_issue"}, "prompt": "Write the issue for {request} into issue."}

# -- definition and host rules: rule id -> (raising fixture, clean fixture) ---------------------------------------------

CASES: dict[str, Case] = {
    "mcp-tool-not-in-catalog": (D(tools=["read", "mcp:notes/append_note"]), D(tools=["read"])),  # no catalog entry
    "artifact-needs-write": (D(tools=["read", "edit"], **ISSUE), D(tools=["read", "mcp:tracker/create_issue"], **ISSUE)),
    "shell-without-commands": (D(tools=["read", "shell"]), D(**SHELL)),
    "dir-change-in-commands": (
        D(**SHELL, prompt="First run `cd src && pytest`, then write the notes into notes."),
        D(**SHELL, prompt="Run `git -C src status`, then write the notes into notes.")),
    "shell-for-read-likely": (
        D(tools=["read", "search", "shell"], commands=["pytest"],
          prompt="Use grep to find the code and cat the file, then write the notes into notes."),
        D(tools=["read", "search", "shell"], commands=["pytest"],
          prompt="Search with the search tool, then write the notes into notes.")),
    "path-outside-workspace": (D(prompt="Read /etc/hosts and write the notes into notes."),
                               D(prompt="Read hosts.txt and write the notes into notes.")),
    "granted-not-needed": (D(tools=["write", "web_fetch"]), D(tools=["read", "write"])),
    "not-enforced": (D(executor="antigravity"), D()),
    "judge-ambient-tool": (
        D(("host",), {"ambient_tools": lambda ex: ["mcp__monitor__status"]}),
        D(("host",), {"ambient_tools": lambda ex: []})),
    "mcp-server-not-configured": (
        D(("host",), {"mcp_servers": lambda: {"other"}}, tools=["read", "mcp:tracker/create_issue"]),
        D(("host",), {"mcp_servers": lambda: {"tracker"}}, tools=["read", "mcp:tracker/create_issue"])),
}


def _clash(tmp: Path, plugins: tuple[str, ...]) -> AuditReport:
    cache = tmp / "cache"
    for plugin in plugins:
        write(cache, f"market/{plugin}/1.0.0/skills/plan-review/SKILL.md", "---\nname: plan-review\n---\n")
    spec = tspec(prompt="Write the notes, then run skill `plan-review` on them.")
    return defs(spec, tmp, ("host",), plugin_cache=cache)


CASES["skill-name-clash"] = (lambda tmp: _clash(tmp, ("reviewers", "planning")), lambda tmp: _clash(tmp, ("planning",)))


def _stale(tmp: Path, monkeypatch: pytest.MonkeyPatch, renamed: dict[str, str]) -> AuditReport:
    monkeypatch.setattr("tempergraph.executor_compat.table", lambda: {"claude": {"renamed": renamed}})
    return defs(tspec(), tmp, ("host",))


def _drift(tmp: Path, drop: str | None) -> AuditReport:
    now = {n for names in DECLARED["claude"].tool_map.values() for n in names if "{" not in n}
    stamp = {"engine_version": "0.0.1", "tool_set": {"claude": sorted(now - {drop} if drop else now)}}
    return defs(tspec(), tmp, ("host",), stamp=stamp)


CASES["tool-set-drift"] = (lambda tmp: _drift(tmp, "Glob"), lambda tmp: _drift(tmp, None))


def _history_ctx(spec: Any, tmp: Path) -> AuditReport:
    return audit_history(spec, read(tmp), tmp)


def H(spec: Any, **run_kw: Any) -> Callable[[Path, int], AuditReport]:
    def build(tmp: Path, n: int) -> AuditReport:
        many(tmp, n, **run_kw)
        return _history_ctx(spec, tmp)

    return build


def JUDGE_SEES(tools: list[str]) -> dict[str, Any]:  # noqa: N802
    return {"attempts": [{"judge": {"tools_started": tools}}]}


READ_SEARCH = tspec(tools=["read", "search"])
READ_ONLY = tspec(tools=["read"])
SHELLY = tspec(tools=["read", "search", "shell"], commands=["pytest"])
GRANT = [{"kind": "grant", "unit": "draft", "capability": "shell", "prefix": "npm test", "action": "add"}]
SHELL_CALL = [{"name": "Bash", "capability": "shell"}]

HIST_CASES: dict[str, HistCase] = {
    "judge-exposed-tool": (H(READ_ONLY, **JUDGE_SEES(["Read", "mcp__monitor__status"])),
                           H(READ_ONLY, **JUDGE_SEES(["Read"]))),
    "granted-never-used": (H(READ_SEARCH, attempts=[{"calls": [{"name": "Read"}]}]),
                           H(READ_SEARCH, attempts=[{"calls": [{"name": "Read"}, {"name": "Grep"}]}])),
    "undeclared-calls": (H(READ_ONLY, attempts=[{"calls": [{"name": "Bash"}]}]),
                         H(READ_ONLY, attempts=[{"calls": [{"name": "Read"}]}])),
    "refusals-by-class": (H(SHELLY, attempts=[{"denied": [{"name": "Bash", "input_summary": "grep x ."}] * 2}]),
                          H(SHELLY, attempts=[{}])),
    "granted-at-run": (H(SHELLY, extra=GRANT, attempts=[{"calls": SHELL_CALL}]),
                       H(SHELLY, attempts=[{"calls": SHELL_CALL}])),
}


def test_every_c4_rule_has_a_fixture() -> None:
    """TSA-AC1: every C4 rule the audit computes has a raising and a clean fixture; the two owned ones are below."""
    owned = {"judge-view-missing", "needed-not-granted"}  # rendered from validation, tested below
    patched = {"declared-tool-stale"}  # needs the compatibility table patched: its own test below
    c4 = {r.id for r in cat.RULES if r.family == "C4"}
    assert c4 == set(CASES) | set(HIST_CASES) | owned | patched


def check_record(f: Any, rule_id: str) -> None:
    r = cat.BY_ID[rule_id]
    assert (f.layer, f.severity, f.confidence) == (r.layer, r.severity, r.confidence)
    assert f.widening is r.widening and f.rule == rule_id
    if rule_id != "refusals-by-class":
        assert f.cause == r.cause


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_fixture_raises_the_rule(tmp_path: Path, rule_id: str) -> None:
    """TSA-AC1 (TSA-B9, TSA-B10, TSA-B12): the raising fixture fires with the catalog's record."""
    rep = CASES[rule_id][0](tmp_path)
    got = hits(rep, rule_id)
    assert got, (rule_id, [(f.rule) for f in rep.findings if f.layer != "history"])
    check_record(got[0], rule_id)
    assert rule_id not in {s["rule"] for s in rep.rules_skipped}


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_clean_fixture_does_not_raise_the_rule(tmp_path: Path, rule_id: str) -> None:
    """TSA-AC1: the clean fixture is quiet and the rule ran."""
    rep = CASES[rule_id][1](tmp_path)
    assert hits(rep, rule_id) == []
    assert rule_id not in {s["rule"] for s in rep.rules_skipped}


def test_declared_tool_stale_names_the_new_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TSA-B12: a mapped executor tool the compatibility table marks renamed is found, giving the new name."""
    got = hits(_stale(tmp_path, monkeypatch, {"Read": "ReadFile"}), "declared-tool-stale")
    assert got and got[0].evidence["now"] == "ReadFile" and got[0].item == "Read"
    check_record(got[0], "declared-tool-stale")
    assert hits(_stale(tmp_path, monkeypatch, {}), "declared-tool-stale") == []


@pytest.mark.parametrize("rule_id", sorted(HIST_CASES))
def test_a_history_fixture_raises_the_rule(tmp_path: Path, rule_id: str) -> None:
    """TSA-AC1 (TSA-B9, TSA-B11): the raising fixture of a history rule fires with the catalog's record."""
    n = cat.BY_ID[rule_id].min_n or 1
    got = hits(HIST_CASES[rule_id][0](tmp_path, n), rule_id)
    assert got, rule_id
    check_record(got[0], rule_id)
    assert got[0].evidence["n"] == n and got[0].unit == "draft"


@pytest.mark.parametrize("rule_id", sorted(HIST_CASES))
def test_a_history_clean_fixture_is_quiet(tmp_path: Path, rule_id: str) -> None:
    """TSA-AC1: the clean fixture is quiet and the rule ran."""
    rep = HIST_CASES[rule_id][1](tmp_path, max(cat.BY_ID[rule_id].min_n or 1, 10))
    assert hits(rep, rule_id) == [] and rule_id not in {s["rule"] for s in rep.rules_skipped}


@pytest.mark.parametrize("rule_id", sorted(r for r in HIST_CASES if (cat.BY_ID[r].min_n or 1) > 1))
def test_a_history_rule_below_min_n_is_skipped_with_its_n(tmp_path: Path, rule_id: str) -> None:
    """TSA-AC1, AUD-AC3: below its minimum sample the rule gives no finding and is skipped as `n=<runs> of <min>`."""
    need = cat.BY_ID[rule_id].min_n or 1
    rep = HIST_CASES[rule_id][0](tmp_path, need - 1)
    assert hits(rep, rule_id) == []
    assert next(s for s in rep.rules_skipped if s["rule"] == rule_id)["reason"] == f"n={need - 1} of {need}"


def test_the_ambient_probe_that_cannot_list_skips_the_host_rule_and_history_still_runs(tmp_path: Path) -> None:
    """TSA-B9: a probe that cannot list plugin tools: `judge-ambient-tool` is skipped with `probe cannot list`."""
    many(tmp_path, 1)
    rep = defs(tspec(), tmp_path, ("host", "history"), history=read(tmp_path))
    assert next(s for s in rep.rules_skipped if s["rule"] == "judge-ambient-tool")["reason"] == "probe cannot list"
    assert "history" in rep.layers_run


# -- the owned rules are rendered from validation ---------------------------------------------------------------------


def test_judge_view_missing_is_validations_finding_once(tmp_path: Path) -> None:
    """TSA-B9, AUD-B8: a judge with no read view of an artifact kind is validation's finding, shown once."""
    no_mcp = {**DECLARED, "claude": replace(DECLARED["claude"], judge_mcp=False)}  # a judge without MCP views
    rep = defs(tspec(tools=["read", "shell"], commands=["pytest"], produces={"issue": "tracker_issue"},
                     prompt="Write the issue for {request} into issue."), tmp_path, caps=no_mcp)
    assert len(hits(rep, "validate:judge-view-unavailable")) == 1 and hits(rep, "judge-view-missing") == []
    assert hits(defs(tspec(), tmp_path, caps=no_mcp), "validate:judge-view-unavailable") == []


def test_needed_not_granted_is_validations_finding_once(tmp_path: Path) -> None:
    """TSA-B10, AUD-B8: a tool the unit needs that its executor maps nowhere is validation's finding, shown once."""
    rep = defs(tspec(executor="messages-api", tools=["subagent"]), tmp_path)
    assert len(hits(rep, "validate:tool-unmapped")) == 1 and hits(rep, "needed-not-granted") == []
    assert hits(defs(tspec(executor="messages-api", tools=["read"]), tmp_path), "validate:tool-unmapped") == []


# -- TSA-B1, TSA-AC2: a judge exposed before any call -----------------------------------------------------------------


def test_an_ambient_tool_never_called_is_reported_with_its_session_and_runs(tmp_path: Path) -> None:
    """TSA-AC2 (TSA-B1, TSA-B6): the judge's start tool list in two runs holds `mcp__monitor__status` outside its
    view set and it was never called: `judge-exposed-tool` at `error` names the tool, the session and both runs."""
    rep = H(READ_ONLY, **JUDGE_SEES(["Read", "mcp__monitor__status"]))(tmp_path, 2)
    (f,) = hits(rep, "judge-exposed-tool")
    assert (f.severity, f.session, f.item, f.unit) == ("error", "judge", "mcp__monitor__status", "draft")
    assert f.evidence["tool"] == "mcp__monitor__status" and f.evidence["runs"] == ["t000", "t001"]
    assert f.evidence["called"] == 0 and "never called" in f.statement


def test_an_exposed_tool_that_was_called_says_so(tmp_path: Path) -> None:
    """TSA-AC2 (TSA-B9): the same tool, called, is still exposed (called or not) and the evidence counts the calls."""
    judge = {"tools_started": ["Read", "mcp__monitor__status"], "calls": [{"name": "mcp__monitor__status"}]}
    rep = H(READ_ONLY, attempts=[{"judge": judge}])(tmp_path, 2)
    (f,) = hits(rep, "judge-exposed-tool")
    assert f.evidence["called"] == 2 and "never called" not in f.statement


# -- TSA-B4, TSA-AC6: need comes from text and artifacts -----------------------------------------------------------------


def test_a_tracker_issue_with_no_write_tool_is_found_and_one_with_a_tool_is_quiet(tmp_path: Path) -> None:
    """TSA-AC6 (TSA-B4): a step producing `tracker_issue` and declaring only `read` and `edit` is found, naming the
    key; a step that declares an MCP write tool is not."""
    from tempergraph.audit.surface import build_surface

    spec = tspec(tools=["read", "edit"], **ISSUE)
    (f,) = hits(defs(spec, tmp_path), "artifact-needs-write")
    assert f.item == "issue" and f.session == "step" and f.evidence["artifact"] == "issue"
    assert build_surface(spec, DECLARED, None, None).sessions[0].artifacts_unwritable == ["issue"]
    ok = tspec(tools=["read", "mcp:tracker/create_issue"], **ISSUE)
    assert hits(defs(ok, tmp_path), "artifact-needs-write") == []
    assert build_surface(ok, DECLARED, None, None).sessions[0].artifacts_unwritable == []


# -- TSA-B2: refusals sorted, not just counted ---------------------------------------------------------------------------


def test_refusals_are_sorted_by_class_and_the_remedy_lists_the_fixes_in_that_order(tmp_path: Path) -> None:
    """TSA-B2: 10 runs of `discovery`, 14 refusals: 7 `grep`, 4 `cd … && git`, 3 `npm run build`."""
    def make(i: int) -> dict[str, Any]:
        denied = []
        if i < 7:
            denied.append({"name": "Bash", "input_summary": "grep -rn x ."})
        if i < 4:
            denied.append({"name": "Bash", "input_summary": "cd /repo && git status"})
        if 4 <= i < 7:
            denied.append({"name": "Bash", "input_summary": "npm run build"})
        return {"unit": "discovery", "attempts": [{"denied": denied}]}

    each(tmp_path, 10, make)
    spec = wf({"discovery": clean_step(tools=["read", "search", "shell"], commands=["pytest"])}, allow_commands=["pytest"])
    rep = audit_history(spec, read(tmp_path), tmp_path)
    (f,) = hits(rep, "refusals-by-class")
    assert f.evidence["classes"] == {"shell_for_read": 7, "dir_change_then_command": 4, "needed_command": 3}
    assert f.cause == "shell_for_read" and f.session == "step" and f.unit == "discovery"
    order = [f.remedy.index(x) for x in ("file tools", "git -C <dir>", "npm run build")]
    assert order == sorted(order)


def test_refusals_without_a_journal_are_unclassified_never_zero(tmp_path: Path) -> None:
    """TSA-B7, AUD-B10: logs from an older engine have no journal: the rule is skipped as `unclassified`."""
    many(tmp_path, 5, journal=False)
    rep = audit_history(tspec(), read(tmp_path), tmp_path)
    assert next(s for s in rep.rules_skipped if s["rule"] == "refusals-by-class")["reason"].startswith("unclassified")


# -- TSA-B13, TSA-AC5: widening is marked -------------------------------------------------------------------------------


def test_a_remedy_that_adds_a_grant_is_marked_widening_and_one_that_removes_is_plain(tmp_path: Path) -> None:
    """TSA-AC5 (TSA-B13): `artifact-needs-write` adds a grant, `granted-not-needed` removes one."""
    rep = defs(tspec(tools=["read", "edit"], **ISSUE), tmp_path)
    (add,) = hits(rep, "artifact-needs-write")
    assert add.widening is True and add.remedy.startswith("Widens the grant: ")
    assert add.to_json()["widening"] is True
    rep2 = defs(tspec(tools=["write", "web_fetch"]), tmp_path)
    (rm,) = hits(rep2, "granted-not-needed")
    assert rm.widening is False and not rm.remedy.startswith("Widens") and rm.to_json()["widening"] is False
    rep.show_all = True
    assert "[widens]" in rep.to_text() and "remedy: Widens the grant:" in rep.to_text()
    sarif = rep.to_sarif()["runs"][0]["results"]
    assert any(r.get("properties") == {"widening": True} for r in sarif if r["ruleId"] == "artifact-needs-write")


def test_every_widening_rule_of_the_catalog_marks_its_findings(tmp_path: Path) -> None:
    """TSA-AC5: each catalog rule with a widening remedy yields a marked finding; no other does."""
    for rule_id in ("artifact-needs-write", "shell-without-commands"):
        got = hits(CASES[rule_id][0](tmp_path), rule_id)
        assert got and all(f.widening and f.remedy.startswith("Widens the grant: ") for f in got)
    for rule_id in ("undeclared-calls", "granted-at-run"):
        got = hits(HIST_CASES[rule_id][0](tmp_path / rule_id, cat.BY_ID[rule_id].min_n or 1), rule_id)
        assert got and all(f.widening and f.remedy.startswith("Widens the grant: ") for f in got)
    got = hits(CASES["dir-change-in-commands"][0](tmp_path), "dir-change-in-commands")
    assert got and not got[0].widening


def test_tool_rules_need_no_model_and_write_nothing(tmp_path: Path) -> None:
    """AUD-AC2: the C4 rules over a state root with runs leave it unchanged."""
    from .conftest import hash_tree

    state = tmp_path / "state"
    many(state, 3)
    before = hash_tree(state)
    audit_history(tspec(tools=["read", "shell"]), read(state), tmp_path)
    assert hash_tree(state) == before
