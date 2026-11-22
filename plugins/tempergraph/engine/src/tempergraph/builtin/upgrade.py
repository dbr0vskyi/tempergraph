"""The built-in upgrade workflow (UWF): the assisted and owner items of a workflow upgrade, each as one gated
map item on the upgrade's branch. Started by `tempergraph upgrade` only; an ordinary run otherwise.

The verb writes what the run reads into `.tempergraph-upgrade/` at the root of the branch's worktree: the two
item lists and a context document with each item's entry, the package folder, the protected paths and the
baseline. That folder is never committed, and the scope check leaves it out.
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.api import CheckResult, Gate, Judge, Map, Routing, Script, Step, Value, Workflow
from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import CheckFinding, Criterion, WorkflowSpec

NAME = "upgrade"
FLAG = "upgrade"  # the value of `WorkflowSpec.builtin`
ITEMS_DIR = ".tempergraph-upgrade"
READ_ONLY_COMMANDS = ("tempergraph validate", "tempergraph upgrade --check", "tempergraph audit --layer definition")

OWNER_PROMPT = """You are helping the owner of a workflow package answer one question an engine release asks.

Item {item_id} ({item_index} of {item_count}):

{item}

Read the files the hits name. Draft the smallest change in the package that would answer the question, and
write it on this branch. Do not choose for the owner where the question offers choices: draft the most
conservative one and say what each other choice would change. Change nothing outside the package folder and
nothing the question does not concern.

End with one line: `ARTIFACT change_note: <what you changed and why, in one or two sentences>`"""

ADJUST_PROMPT = """You are bringing a workflow package up to a new engine release, one change at a time.

Item {item_id} ({item_index} of {item_count}):

{item}

Read the files the hits name and make the edit the instruction asks for at each hit. Make the smallest edit
that meets it. Do not reword, reformat or change anything the instruction does not concern, do not weaken a
criterion, a check or a judge, and do not edit a protected path or anything outside the package folder.

End with one line: `ARTIFACT change_note: <what you changed and why, in one or two sentences>`"""

STANCE = ("You verify one edit made to a workflow package for an engine upgrade. You did not make the edit. "
          "Judge only what the diff and the files show.")
BRIEF = ("Run `git diff` in the workspace to read the edit, and read the files it touches. The item's note and "
         "its instruction or question are in the step's request above. Grade each criterion on the diff alone.")


def _crit(cid: str, text: str, *, severity: str = "blocker", by: str = "judge") -> Criterion:
    how = "The gate's check decides this from the workspace" if by == "check" else \
        "Read the diff and the files it touches against the item's note and instruction"
    return Criterion(id=cid, text=text, severity=severity, verified_by=by, check_method=how)  # type: ignore[arg-type]


CHECKED = [
    _crit("uwf-scope", "The attempt changes no file outside the package and, in `adjust`, no protected path", by="check"),
    _crit("uwf-loads", "The package loads and validation has no error the baseline lacks", by="check"),
    _crit("uwf-proof", "The item's detect rules find nothing and its proof codes are not raised", by="check"),
    _crit("uwf-fixtures", "Every check fixture that passed before the upgrade still passes", by="check"),
]
JUDGED = [
    _crit("uwf-instruction", "The edit does what the entry's instruction asks at every hit, and nothing that only "
                             "the owner should decide"),
    _crit("uwf-unchanged", "Behaviour the entry does not concern is unchanged: no rewording, reformatting or extra "
                           "edits outside what the hits need"),
    _crit("uwf-no-weakening", "No criterion, check or judge view is weakened, and no rubric or bar is invented"),
    _crit("uwf-smallest", "The diff is the smallest that meets the instruction", severity="warning"),
]


def slug(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", item_id)[:40]


def _doc(workdir: Path, name: str) -> Any:
    return json.loads((workdir / ITEMS_DIR / name).read_text(encoding="utf-8"))


def resolve_items(ctx: Any) -> dict[str, str]:
    """The model-free input step: the two lists the verb wrote must be there and of this engine."""
    context = _doc(ctx.workdir, "context.json")
    if context.get("engine_version") != ENGINE_VERSION:
        raise ValueError("the upgrade plan is of another engine version")
    for name in ("owner_items.json", "assisted_items.json"):
        if not isinstance(_doc(ctx.workdir, name), list):
            raise ValueError(f"{name} is not a list")
    return {"owner_items": f"{ITEMS_DIR}/owner_items.json", "assisted_items": f"{ITEMS_DIR}/assisted_items.json"}


def _changed(workdir: Path) -> list[str]:
    out = gitmod.git(["status", "--porcelain=v1", "--untracked-files=all"], workdir, check=False)
    paths = [ln[3:].split(" -> ")[-1].strip('"') for ln in out.splitlines() if ln.strip()]
    return [p for p in paths if not p.startswith(ITEMS_DIR + "/")]


def item_check(ctx: Any) -> CheckResult:
    """UWF-B12, UWF-B13: scope, load and validate, proof, fixtures. The first that fails is reported alone, because
    each later one needs the earlier to hold."""
    from tempergraph.executors.capabilities import DECLARED
    from tempergraph.model.validate import validate
    from tempergraph.package.changelog import detect
    from tempergraph.package.loader import PackageNotLoaded, load_package

    workdir = Path(ctx.workdir)
    context = _doc(workdir, "context.json")
    rel = str(context.get("package") or "")
    prefix = rel + "/" if rel else ""
    item = dict((context.get("items") or {}).get(str(ctx.item)) or {})

    def fail(criterion: str, message: str) -> CheckResult:
        return CheckResult(result="FAIL", evidence=message[:300], findings=[
            CheckFinding(status="fail", criterion=criterion, message=message[:300], kind="substance")])

    changed = _changed(workdir)
    outside = [p for p in changed if prefix and not p.startswith(prefix)]
    if outside:
        return fail("uwf-scope", f"changed outside the package: {', '.join(outside[:5])}")
    owner_file = workdir / ITEMS_DIR / "owner_changed.json"
    try:
        by_owner = set(json.loads(owner_file.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        by_owner = set()
    inside = [p[len(prefix):] for p in changed]
    if ctx.unit == "adjust":
        globs = [str(g) for g in context.get("protected") or []]
        hit = [p for p in inside if p not in by_owner and any(fnmatch.fnmatchcase(p, g) for g in globs)]
        if hit:
            return fail("uwf-scope", f"a protected path was edited: {', '.join(hit[:5])}; only its owner changes it")
    pkg = workdir / rel if rel else workdir
    try:
        lp = load_package(pkg)
    except PackageNotLoaded as exc:
        return fail("uwf-loads", f"the package does not load: {exc}")
    found = validate(lp.spec, dict(DECLARED))
    known = set(context.get("validation_keys") or [])
    new = sorted({f"{f.severity}|{f.code}|{f.unit or ''}" for f in found if f.severity == "error"} - known)
    if new:
        return fail("uwf-loads", f"validation errors the baseline lacks: {', '.join(new[:5])}")
    entry = item.get("entry_doc")
    if isinstance(entry, Mapping):
        codes = {f.code for f in found}
        left = detect(entry, lp.spec, lp.root, codes)
        raised = sorted(codes & {str(c) for c in entry.get("proof") or []})
        if left or raised:
            where = ", ".join([h.where for h in left][:5] + raised)
            return fail("uwf-proof", f"the entry still applies at: {where}")
    from tempergraph.improve.suites import green_model_free

    worse = sorted(set(green_model_free(lp.spec)) - set(context.get("suites_failing") or []))
    if worse:
        return fail("uwf-fixtures", "; ".join(worse)[:300])
    if ctx.unit == "draft_answer":  # what an owner item changed is the owner's to approve, not a later item's fault
        (workdir / ITEMS_DIR).mkdir(exist_ok=True)
        owner_file.write_text(json.dumps(sorted(by_owner | set(inside))), encoding="utf-8")
    return CheckResult(result="PASS", evidence=f"{len(changed)} files changed inside the package", findings=[
        CheckFinding(status="pass", criterion=c.id, message="") for c in CHECKED])


def workflow(executor: str | None = None) -> WorkflowSpec:
    """The spec, the same for every upgrade; `executor` is `UpgradePolicy.executor` or the verb's `--executor`."""
    def item(prompt: str, *, approval: bool) -> Any:
        return Step(prompt=prompt, tools=["read", "search", "list", "edit", "write", "shell"],
                    commands=list(READ_ONLY_COMMANDS), model="large", executor=executor,
                    produces={"change_note": Value(max_chars=600)},
                    gate=Gate(check=item_check, judge=Judge(stance=STANCE, brief=BRIEF, model="medium"),
                              criteria=[*CHECKED, *JUDGED], approval=approval, retry_budget=2,
                              on_budget_spent="ask"))

    spec = Workflow(
        order=["resolve", "draft_answer", "adjust"],
        routing=Routing(description="Apply the assisted and owner items of a workflow upgrade",
                        when_to_use="Started by `tempergraph upgrade <workflow>` only"),
        allow_commands=list(READ_ONLY_COMMANDS),
        units={
            "resolve": Script(call=resolve_items, produces={"owner_items": "file", "assisted_items": "file"},
                              side_effects="none", summary="Read the upgrade's plan", gate=Gate()),
            "draft_answer": Map(items_from=("resolve", "owner_items"), on_empty="skip", max_items=50,
                                step=item(OWNER_PROMPT, approval=True)),
            "adjust": Map(items_from=("resolve", "assisted_items"), on_empty="skip", max_items=50,
                          step=item(ADJUST_PROMPT, approval=False)),
        },
    )
    import dataclasses

    return dataclasses.replace(spec, name=NAME, version=ENGINE_VERSION, builtin=FLAG)


def is_upgrade(spec: WorkflowSpec) -> bool:
    return spec.builtin == FLAG


# -- the assist step of `tempergraph upgrade` (WUP-B18) --------------------------------------------------------


def write_inputs(a: Any) -> None:
    entries, base, protected = a.entries, a.base, tuple(a.protected)
    folder = Path(a.worktree) / ITEMS_DIR
    folder.mkdir(exist_ok=True)
    rel = Path(a.package).relative_to(a.worktree).as_posix()
    items: dict[str, Any] = {}
    lists: dict[str, list[dict[str, str]]] = {"owner": [], "assisted": []}
    for it in a.items:
        hits = "\n".join(f"- {h.get('where')} (rule {h.get('rule')})" for h in it.hits) or "- (the whole package)"
        ask = "Question for the owner" if it.action == "owner" else "Instruction"
        text = (f"What changed in the engine: {it.note}\n\n{ask}: {it.ask}\n\nHits:\n{hits}\n\n"
                f"Package folder: {rel or '.'}\nProtected paths (the owner's): {', '.join(protected)}")
        items[slug(it.item_id)] = {"item_id": it.item_id, "action": it.action,
                                   "entry_doc": dict(entries.get(it.entry) or {}) or None}
        lists["owner" if it.action == "owner" else "assisted"].append({"id": slug(it.item_id), "text": text})
    (folder / "owner_items.json").write_text(json.dumps(lists["owner"], indent=1), encoding="utf-8")
    (folder / "assisted_items.json").write_text(json.dumps(lists["assisted"], indent=1), encoding="utf-8")
    (folder / "context.json").write_text(json.dumps({
        "schema_version": 1, "upgrade_id": a.upgrade_id, "engine_version": ENGINE_VERSION,
        "package": "" if rel == "." else rel, "protected": list(protected), "items": items,
        "validation_keys": list(base.get("validation_keys") or []),
        "suites_failing": list(base.get("suites_failing") or [])}, indent=1), encoding="utf-8")


def results(root: Path, a: Any, exit_code: int) -> dict[str, Any]:
    """Each item's state from the thread: a map item that passed its gate is done (`adjust`, by the model) or
    answered (`draft_answer`, by the person who approved it); the owner item a person stopped at is skipped."""
    from tempergraph.durability import engine_file
    from tempergraph.durability.checkpoint import thread_values
    from tempergraph.run.log import last_record
    from tempergraph.store.layout import run_dir

    spec = workflow()
    tid = f"{NAME}/{a.upgrade_id}"
    values = thread_values(engine_file.checkpoint_of(root, NAME, a.upgrade_id), spec, tid)
    maps = values.get("maps") or {}
    out: dict[str, Any] = {}
    log = run_dir(root, NAME, a.upgrade_id) / "run.jsonl"
    stopped = (last_record(log, "human") or {}).get("decision") == "stop"
    for it in a.items:
        unit = "draft_answer" if it.action == "owner" else "adjust"
        passed = set((maps.get(unit) or {}).get("passed") or [])
        if slug(it.item_id) in passed:
            out[it.item_id] = {"state": "answered", "by": "person"} if unit == "draft_answer" \
                else {"state": "done", "by": "model"}
        elif unit == "draft_answer" and stopped:  # the first owner item not passed is the one the person stopped at
            out[it.item_id] = {"state": "skipped", "by": "person", "reason": "stopped by the owner at its approval"}
            stopped = False
    end = last_record(log, "run_exit") or {}
    cost = (end.get("cost") or {}).get("reported")
    return {"exit_code": exit_code, "thread_id": tid, "cost_usd": cost, "items": out}


def assist(a: Any, registry: Any, *, caller: Mapping[str, Any], settings: Any = None) -> dict[str, Any]:
    """Run, or go on reading, the upgrade's own thread `upgrade/<upgrade_id>` on the branch's worktree."""
    import dataclasses

    from tempergraph.contracts import ThreadState
    from tempergraph.durability.status import classify
    from tempergraph.run.runner import RunSettings, start
    from tempergraph.store.layout import state_root_path

    root = state_root_path(Path(a.worktree))
    spec = workflow(a.executor)
    state = classify(root, spec, a.upgrade_id) if root.is_dir() else ThreadState.NONE
    if state is ThreadState.NONE:
        write_inputs(a)
        base_settings = settings or RunSettings()
        run_settings = dataclasses.replace(
            base_settings, workspace="in_place", origin="upgrade", caller=dict(caller),
            label=f"upgrade {a.upgrade_id}",
            flags={**dict(base_settings.flags), "run.run_cost_cap_usd": max(float(a.cap_usd), 0.0)})
        got = start(spec, a.upgrade_id, {"request": a.upgrade_id}, Path(a.worktree), registry, run_settings)
        code = int(got.exit_code)
        if code == 2:  # refused before anything ran: the reason is the run driver's own
            return {"exit_code": 2, "thread_id": f"{NAME}/{a.upgrade_id}", "items": {},
                    "message": got.message or got.reason}
    elif state is ThreadState.FINISHED:
        code = 0
    elif state is ThreadState.PAUSED:
        code = 3
    else:
        code = 5 if state is ThreadState.STOPPED else 4
    return results(root, a, code)
