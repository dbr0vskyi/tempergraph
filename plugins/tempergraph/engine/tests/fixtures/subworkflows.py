"""Fixture parents and children for the sub-workflow unit (SWF-B1 to SWF-B8, SWF-B10, SWF-B12): engine fixtures, none a shipped workflow.

`register_workflow` writes a workflow package to disk and enters it in the registry of the test home, so the one
reader of a child (`tempergraph.model.subworkflow`) finds it as it finds a real one (PKG-B15). A child written here
can also be run: its `work` unit can write the files it produces or none, can wait for an approval, can carry a
finalizer, and its outcome gate is a judge, so a test scripts every session with a stand-in executor.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from tempergraph.api import Subworkflow
from tempergraph.contracts import WorkflowSpec
from tempergraph.package import registry

from .packages import package_parts, write
from .workflows import named, two_step

FINALIZER_MARK = "child-finalizer-ran.txt"  # the file a child's fixture finalizer writes in the workspace when it runs


def home_dir() -> Path:
    """The home folder `conftest.py` gives each test (`TEMPERGRAPH_HOME`)."""
    return Path(os.environ["TEMPERGRAPH_HOME"])


def _declaration(inputs: tuple[str, ...], produces: tuple[str, ...], children: Mapping[str, Mapping[str, Any]],
                 needs_git: bool, broken: bool, *, finalizer: bool, approval: bool, workspace: str | None,
                 defaults: bool, person: str | None = None, issue_repository: str = "acme/fixture",
                 judge_alias: str | None = None, ladder: bool = False) -> str:
    names = inputs or ("request",)
    prompt = "Work on " + " and ".join("{" + n + "}" for n in names)
    risk = (', risk=Risk(levels=[Level("base"), Level("high", model="large")], when=[When("high", paths=["src/**"])])'
            if needs_git else "")
    params = f"input=Input(parameters=[{', '.join(f'Param(name={n!r})' for n in inputs)}]), " if inputs else ""
    extra = ""
    if finalizer:
        extra += "finalizer=finish, finalizer_outcomes=['done'], "
    if workspace:
        extra += f"workspace={workspace!r}, "
    if defaults:
        extra += "settings={'depth': SettingDecl(kind='int', default=2, min=1, max=9)}, "
    gate_args = "approval=True, " if approval else ""
    judge_args = f"model={judge_alias!r}, " if judge_alias else ""
    step_args = "model='medium', effort_ladder=('medium', 'high', 'xhigh'), " if ladder else ""
    first = {"ask": ("details", "    units['details'] = Ask(questions=[Question('ticket', 'Which ticket?')])"),
             "wait": ("signoff", "    units['signoff'] = Wait(event='approved', check=signed)")}.get(person or "")
    lines = [
        "from tempergraph.api import Ask, Criterion, FinalizerResult, Gate, Input, Judge, Level, Param, Question, Risk, Routing, SettingDecl, Step, Subworkflow, Wait, When, Workflow",
        *(["raise RuntimeError('a package that does not import')"] if broken else []),
        "",
        "",
        "def finish(ctx):",
        f"    (ctx.workdir / {FINALIZER_MARK!r}).write_text('ran')",
        "    return FinalizerResult(outcome='done')",
        "",
        "",
        "def signed(value):",
        "    return value in ('yes', 'no')",
        "",
        "",
        "def workflow():",
        "    units = {}",
        *([first[1]] if first else []),
        f"    units['work'] = Step(prompt={prompt!r}, tools=['read', 'write'], produces={dict.fromkeys(produces, 'file')!r}, {step_args}",
        f"                         gate=Gate({gate_args}judge=Judge({judge_args}stance='Verify.'{risk}),",
        "                                   criteria=[Criterion(id='c-work', text='The work is done', check_method='Read the result')]))",
        *(f"    units[{n!r}] = Subworkflow(**{dict(kw)!r})" for n, kw in children.items()),
        f"    return Workflow(order={[*([first[0]] if first else []), 'work', *children]!r}, units=units, routing=Routing(description='A fixture workflow'),",
        f"                    {params}{extra}issue_repository={issue_repository!r})",
        "",
    ]
    return "\n".join(lines)


def _outcome(produces: tuple[str, ...]) -> dict[str, Any]:
    return {"schema_version": 1, "revision": 1, "statement": "Done well.",
            "deliverables": [{"key": k, "kind": "file", "where": "the workspace"} for k in produces],
            "intermediate": {"work": {"statement": "work done", "criteria": []}},
            "final": [{"id": "done", "text": "The work is done", "verified_by": "judge",
                       "check_method": "Read the result"}]}


# SWF-AC1: this helper builds the parents and children the tests of SWF-AC1 run on (test_subworkflow_validate.py,
# test_subworkflow_inputs.py, test_outside_git.py, test_subworkflow_run.py, test_subworkflow_gate.py): each refusal of
# SWF-B6 and each behaviour of SWF-B1 to SWF-B5 is proved against a package it writes.
def register_workflow(home: Path, parent: Path, name: str, *, version: str = "0.3.1", inputs: Iterable[str] = (),
                      produces: Iterable[str] = (), children: Mapping[str, Mapping[str, Any]] | None = None,
                      needs_git: bool = False, broken: bool = False, finalizer: bool = False, approval: bool = False,
                      workspace: str | None = None, defaults: bool = False, deliverables: bool = True,
                      person: str | None = None, issue_repository: str = "acme/fixture",
                      judge_alias: str | None = None, cases: Iterable[tuple[str, bool]] = (),
                      ladder: bool = False) -> Path:
    """Write the fixture package `name` under `parent` and enter it in the registry of `home`; return its root.

    One step unit `work` produces the keys in `produces` (the outcome lists them as deliverables unless
    `deliverables` is off, which lets a child end well without making a key it declares), then one
    `Subworkflow(**kwargs)` unit per item of `children`. `inputs` are the declared inputs (none: the one input
    `request`). `needs_git` adds a stock risk rule on changed paths. `broken` makes the package fail to import.
    `finalizer` gives the workflow a finalizer that writes `FINALIZER_MARK` in the workspace. `approval` makes the
    `work` gate pause for a person. `workspace` is the workflow's own `run.workspace` default. `defaults` declares the
    setting `depth` (default 2). `person` puts a unit before `work` that waits for a person: `ask` is an `Ask` unit
    `details` with the question `ticket`, `wait` a `Wait` unit `signoff` for the event `approved` (`yes` or `no`). A test scripts the sessions: the `work` step ends with `ARTIFACT <key>: <file>` lines
    for the keys it makes, and a judge answers with a verdict block.

    `issue_repository` is the workflow's `issue_repository`. `judge_alias` is the alias of the `work` gate's judge
    (none: the judge's own default). `cases` writes one reviewed calibration case per `(case_id, bad)` under the
    package's `evals/` for the `work` gate, labelled UNMET when `bad` and MET otherwise. `ladder` gives the `work`
    step an effort ladder, so its judgement carries `judge_state`."""
    kids = dict(children or {})
    root = parent / name
    mod = name.replace("-", "_")
    keys, ins = tuple(produces), tuple(inputs)
    write(root, ".claude-plugin/plugin.json", {"name": f"{name}-tgraph", "version": version,
                                               "description": "A fixture workflow", "author": {"name": "Example Owner"},
                                               "license": "MIT", "dependencies": ["tempergraph"]})
    write(root, "tempergraph.json", {"schema_version": 1, "name": name, "entry": f"{mod}:workflow",
                                     "workflow_api": 1, "docs": "provisional"})
    write(root, f"workflow/{mod}/__init__.py", _declaration(ins, keys, kids, needs_git, broken, finalizer=finalizer,
                                                           approval=approval, workspace=workspace, defaults=defaults,
                                                           person=person, issue_repository=issue_repository,
                                                           judge_alias=judge_alias, ladder=ladder))
    package_parts(root, name, outcome=_outcome(keys if deliverables else ()))
    for case_id, bad in cases:
        _case(root, case_id, bad)
    entries = [e for e in registry.read_entries(home) if e["name"] != name]
    registry.write_entries([*entries, {"name": name, "kind": "local", "path": str(root), "version": version}], home)
    return root


def _case(root: Path, case_id: str, bad: bool) -> None:
    """One reviewed gold case of the `work` gate: `request.md` says BAD or GOOD, so a stand-in judge can grade it."""
    folder = root / "evals" / "calibration" / "work" / case_id
    fx = folder / "fixture"
    write(fx, "workspace/notes.md", "# Notes\n- point one\n")
    write(fx, "request.md", "BAD" if bad else "GOOD")
    write(fx, "account.md", "I wrote the notes.")
    write(fx, "references.json", {"notes": "notes.md", "spec": "the point"})
    write(fx, "subject.json", {"notes": "notes.md"})
    write(folder, "case.json", {
        "schema_version": 1, "case_id": case_id, "gate": "work", "provenance": "expert", "state": "reviewed",
        "split": "holdout", "reach": {"c-work": "spec"},
        "labels": [{"criterion_id": "c-work", "expected": "UNMET" if bad else "MET", "reason": "Planted.",
                    "reviewer": "dana", "by_person": True}]})


def remove_registry(home: Path) -> None:
    (home / "registry.json").unlink(missing_ok=True)


def parent_spec(name: str = "deliver", **unit: Any) -> WorkflowSpec:
    """`two_step()` named `name`, plus the sub-workflow unit `setup` built from `unit` as `Subworkflow(**unit)`, last in order."""
    base = two_step()
    units = {**base.units, "setup": Subworkflow(**unit)}
    return named(dataclasses.replace(base, units=units, order=(*base.order, "setup")), name)


def registry_names(home: Path) -> list[str]:
    return [str(e["name"]) for e in json.loads((home / "registry.json").read_text(encoding="utf-8"))["workflows"]]
