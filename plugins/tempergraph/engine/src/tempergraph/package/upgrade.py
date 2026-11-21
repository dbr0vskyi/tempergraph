"""`tempergraph upgrade <workflow>` beyond `--check`: baseline, plan, transforms on a branch, verification and
the finish (WUP §2.2 to §2.7). Model-free; the assisted and owner items go to a caller-given assist step
(the built-in upgrade workflow, UWF), which is the only part that may start a session.

Nothing here touches the person's checkout: the changes are commits on `tempergraph/upgrade/<workflow>/<engine>`
in a worktree of its own, and the record is `upgrades/<upgrade_id>/` under the source repository's state root.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tempergraph import git as gitmod
from tempergraph.constants import ENGINE_VERSION
from tempergraph.contracts import Capabilities, WorkflowSpec
from tempergraph.docs import write_json
from tempergraph.model.diagram import diagram_model, to_mermaid
from tempergraph.model.validate import Finding, validate
from tempergraph.package import transforms
from tempergraph.package.changelog import detect, entries_between, semver
from tempergraph.package.inventory import canonical
from tempergraph.package.loader import LoadedPackage, PackageNotLoaded, load_package
from tempergraph.package.registry import plugin_cache
from tempergraph.package.stamp import STAMP, Verification, _audit_keys, read_stamp, tool_set
from tempergraph.store.layout import ensure_state_root, now_iso, state_root_path

BRANCH_PREFIX = "tempergraph/upgrade"
ASSIST_DIR = ".tempergraph-upgrade"  # the assist run's inputs at the worktree root; never committed
PROTECTED_DEFAULT = ("units.*.gate.criteria*", "units.*.gate.judge.stance*", "outcome.json", "workflow/*/checks*.py",
                     "judges/*")


def is_open(item: Any) -> bool:
    """Still owed: pending, or failed with no successor (a failed transform hands its hits to a `/rest` item)."""
    return item.state == "pending" or (item.state == "failed" and item.action != "transform")
COMMIT = ["-c", "user.name=tempergraph", "-c", "user.email=engine@localhost", "commit", "-q", "-m"]


class UpgradeRefused(Exception):
    """Exit 2: an unknown or installed workflow, a dirty source, a branch that is not this upgrade's."""


@dataclass(kw_only=True)
class Item:
    item_id: str
    entry: str
    action: str  # transform, assisted, owner, manual, none
    hits: list[dict[str, Any]] = field(default_factory=list)
    protected: bool = False
    state: str = "pending"  # pending, done, failed, skipped, answered
    by: str | None = None  # transform, model, person
    note: str = ""
    ask: str = ""  # the assisted instruction or the owner's question
    reason: str = ""


@dataclass(kw_only=True)
class Report:
    workflow: str
    upgrade_id: str = ""
    exit_code: int = 0
    refused: str = ""
    from_engine: str | None = None
    to_engine: str = ENGINE_VERSION
    from_version: str = ""
    proposed: dict[str, Any] = field(default_factory=dict)
    items: list[Item] = field(default_factory=list)
    not_touched: list[str] = field(default_factory=list)
    checks: list[Verification] = field(default_factory=list)
    baseline_errors: list[str] = field(default_factory=list)
    shares: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    shape_changed: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    branch: str = ""
    worktree: str = ""
    commits: list[dict[str, str]] = field(default_factory=list)
    assist: dict[str, Any] = field(default_factory=dict)
    stamp: dict[str, Any] | None = None
    pull_request: str | None = None

    def to_json(self) -> dict[str, Any]:
        doc = asdict(self)
        doc["schema_version"] = 1
        doc["verification"] = doc.pop("checks")
        return doc


@dataclass(kw_only=True)
class Assist:
    """What the assist step is given: the upgrade's record, the package on the branch and the open items."""

    upgrade_id: str
    record: Path
    worktree: Path
    package: Path
    items: list[Item]
    cap_usd: float
    executor: str | None
    entries: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    base: Mapping[str, Any] = field(default_factory=dict)
    protected: tuple[str, ...] = ()


AssistFn = Callable[[Assist], Mapping[str, Any]]


# -- where it works (WUP §2.2) ----------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Place:
    package: Path
    repo: Path
    rel: str  # the package folder inside the repository, posix; "" when it is the repository
    record: Path
    branch: str
    worktree: Path
    upgrade_id: str


def locate(path: Path, workflow: str, engine: str = ENGINE_VERSION) -> Place:
    root = path.resolve()
    if root.is_relative_to(plugin_cache().resolve()):
        raise UpgradeRefused(f"upgrade the workflow's source; this is an installed copy ({root}). Clone the "
                             "plugin's repository and register that folder")
    repo = gitmod.toplevel(root)
    if repo is None:
        raise UpgradeRefused(f"upgrade the workflow's source; {root} is not inside a git repository")
    repo = repo.resolve()
    rel = root.relative_to(repo).as_posix()
    upgrade_id = f"{workflow}-{engine}"
    from tempergraph.workspace import sibling_root

    return Place(package=root, repo=repo, rel="" if rel == "." else rel,
                 record=state_root_path(repo) / "upgrades" / upgrade_id, branch=f"{BRANCH_PREFIX}/{workflow}/{engine}",
                 worktree=sibling_root(repo) / f"upgrade--{workflow}--{engine}", upgrade_id=upgrade_id)


def _branch_exists(repo: Path, branch: str) -> bool:
    return bool(gitmod.git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], repo, check=False).strip())


def _dirty(place: Place) -> list[str]:
    out = gitmod.git(["status", "--porcelain=v1", "--untracked-files=all", "--", place.rel or "."], place.repo)
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


# -- baseline and plan (WUP §2.3) -------------------------------------------------------------------------------


def _finding_key(f: Finding) -> str:
    return f"{f.severity}|{f.code}|{f.unit or ''}"


def _suites(spec: WorkflowSpec) -> list[str]:
    from tempergraph.improve.suites import green_model_free

    return green_model_free(spec)


def baseline(lp: LoadedPackage, caps: Mapping[str, Capabilities]) -> dict[str, Any]:
    found = validate(lp.spec, caps)
    model = diagram_model(lp.spec)
    return {"schema_version": 1, "taken_at": now_iso(), "engine_version": ENGINE_VERSION,
            "workflow_version": lp.workflow_version, "version": lp.manifests.version,
            "validation": [{"severity": f.severity, "code": f.code, "unit": f.unit, "message": f.message}
                           for f in found],
            "validation_keys": sorted({_finding_key(f) for f in found}),
            "audit": _audit_keys(lp, caps), "suites_failing": _suites(lp.spec),
            "shape_digest": model["digest"], "units": sorted(lp.spec.units), "parse": canonical(lp.spec)}


def _protected(spec: WorkflowSpec, hits: Sequence[Mapping[str, Any]]) -> bool:
    policy = dict(spec.upgrade or {})
    globs = tuple(policy.get("protected") or PROTECTED_DEFAULT)
    return any(fnmatch.fnmatchcase(str(h.get("where") or "").rsplit(":", 1)[0], g)
               or fnmatch.fnmatchcase(str(h.get("where") or ""), g) for h in hits for g in globs)


def plan(lp: LoadedPackage, entries: Sequence[Mapping[str, Any]], codes: set[str], *, no_assist: bool = False
         ) -> tuple[list[Item], list[str], dict[str, str]]:
    items: list[Item] = []
    untouched: list[str] = []
    notes: dict[str, str] = {}
    assist_off = no_assist or (lp.spec.upgrade or {}).get("assist") == "off"
    for e in entries:
        eid = str(e["id"])
        hits = [h.__dict__ for h in detect(e, lp.spec, lp.root, codes)]
        if not hits:
            untouched.append(eid)
            continue
        mig = dict(e.get("migrate") or {})
        action = str(mig.get("action") or "none")
        protected = _protected(lp.spec, hits)
        if action == "assisted" and protected:
            action = "owner"
        if action == "assisted" and assist_off:
            action = "manual"
        notes[eid] = str(e.get("note") or "")
        items.append(Item(item_id=eid, entry=eid, action=action, hits=hits, protected=protected,
                          note=str(e.get("note") or ""), state="done" if action == "none" else "pending",
                          ask=str(mig.get("instruction") or mig.get("question") or mig.get("reason") or "")))
    return items, untouched, notes


# -- transforms (WUP §2.4) --------------------------------------------------------------------------------------


def _outside(place: Place) -> list[str]:
    """Changed paths of the worktree that lie outside the package folder (WUP §2.2 scope)."""
    out = gitmod.git(["status", "--porcelain=v1", "--untracked-files=all"], place.worktree)
    paths = [ln[3:].split(" -> ")[-1].strip('"') for ln in out.splitlines() if ln.strip()]
    prefix = place.rel + "/" if place.rel else ""
    return [p for p in paths if prefix and not p.startswith((prefix, ASSIST_DIR + "/"))]


def _discard(place: Place) -> None:
    gitmod.git(["checkout", "-q", "--", "."], place.worktree, check=False)
    gitmod.git(["clean", "-fdq"], place.worktree, check=False)


def _commit(place: Place, message: str) -> str | None:
    gitmod.git(["add", "-A", "--", place.rel or "."], place.worktree)
    if not gitmod.git(["diff", "--cached", "--name-only"], place.worktree).strip():
        return None
    gitmod.git([*COMMIT, message], place.worktree)
    return gitmod.git(["rev-parse", "HEAD"], place.worktree).strip()


def _pkg(place: Place) -> Path:
    return place.worktree / place.rel if place.rel else place.worktree


def _still_hit(entry: Mapping[str, Any], pkg: Path, caps: Mapping[str, Capabilities]) -> list[dict[str, Any]] | None:
    """The entry's hits in the package as it now is; None when it no longer loads."""
    try:
        lp = load_package(pkg)
    except PackageNotLoaded:
        return None
    codes = {f.code for f in validate(lp.spec, caps)}
    hits = [h.__dict__ for h in detect(entry, lp.spec, lp.root, codes)]
    raised = sorted(codes & {str(c) for c in entry.get("proof") or []})
    return hits + [{"entry": str(entry.get("id")), "rule": c, "where": f"finding:{c}", "confidence": "high"}
                   for c in raised if not any(h["where"] == f"finding:{c}" for h in hits)]


def apply_transforms(place: Place, rep: Report, entries: Mapping[str, Mapping[str, Any]],
                     caps: Mapping[str, Capabilities], workflow: str) -> None:
    """One commit per changelog entry, oldest release first; each entry's rules run again afterwards."""
    pkg = _pkg(place)
    for it in [i for i in rep.items if i.action == "transform" and i.state == "pending"]:
        entry = entries[it.entry]
        owner: list[dict[str, Any]] = []
        try:
            res = transforms.apply(pkg, dict(entry.get("migrate") or {}))
            owner = res.owner
            if _outside(place):
                raise transforms.TransformError("the transform changed a path outside the package")
        except (transforms.TransformError, SyntaxError, OSError) as exc:
            _discard(place)
            it.state, it.reason = "failed", f"{type(exc).__name__}: {exc}"
            rest: list[dict[str, Any]] | None = it.hits
        else:
            sha = _commit(place, f"upgrade({workflow}): {it.entry} {entry.get('subject') or ''}".strip())
            if sha:
                rep.commits.append({"entry": it.entry, "commit": sha})
            rest = _still_hit(entry, pkg, caps)
            if rest:
                it.state, it.reason = "failed", "the entry's detect rules still hit after the transform"
            elif rest is None:
                it.state, it.reason = "failed", "the package no longer loads after the transform"
            else:
                it.state, it.by = "done", "transform"
        if it.state == "failed":
            rep.items.append(Item(item_id=f"{it.entry}/rest", entry=it.entry, action="assisted", hits=rest or it.hits,
                                  protected=it.protected, note=it.note,
                                  ask=f"The transform could not finish this change ({it.reason}). "
                                      + str(entry.get("note") or "")))
        for n, o in enumerate(owner, 1):
            rep.items.append(Item(item_id=f"{it.entry}/owner-{n}", entry=it.entry, action="owner", note=it.note,
                                  hits=[{"entry": it.entry, "rule": "transform", "where": str(o.get("where")),
                                         "confidence": "high"}],
                                  ask=f"{o.get('question')} (it was {o.get('was')})"))


# -- verification (WUP §2.6) ------------------------------------------------------------------------------------


def _reconcile(rep: Report, entries: Mapping[str, Mapping[str, Any]], pkg: Path,
               caps: Mapping[str, Capabilities], continuing: bool) -> None:
    """Before verifying: an open item whose entry no longer hits was fixed by hand. An owner item left without
    an assist step is answered by the person who continues the upgrade (`--continue`), never by a first run."""
    for it in rep.items:
        if not is_open(it) or it.entry not in entries or it.action not in ("assisted", "manual", "owner"):
            continue
        if it.action == "owner" and not continuing:
            continue
        if _still_hit(entries[it.entry], pkg, caps) == []:
            it.state, it.by = ("answered" if it.action == "owner" else "done"), "person"


def verify(place: Place, rep: Report, base: Mapping[str, Any], entries: Mapping[str, Mapping[str, Any]],
           caps: Mapping[str, Capabilities], before: WorkflowSpec | None) -> LoadedPackage | None:
    """V1 to V7 in order; the first failure stops the list. Returns the loaded package when all passed."""
    pkg = _pkg(place)
    rep.checks = []

    def add(check: str, ok: bool, evidence: str) -> bool:
        rep.checks.append(Verification(check=check, state="passed" if ok else "failed", evidence=evidence[:600]))
        return ok

    try:
        lp = load_package(pkg)
    except PackageNotLoaded as exc:
        add("V1 load", False, str(exc))
        return None
    add("V1 load", True, lp.workflow_version)
    found = validate(lp.spec, caps)
    known = set(base.get("validation_keys") or [])
    new = sorted({_finding_key(f) for f in found if f.severity in ("error", "warning")} - known)
    if not add("V2 validation", not new, f"new findings: {', '.join(new)}" if new else
               f"no error or warning the baseline lacks ({len(found)} findings)"):
        return None
    codes = {f.code for f in found}
    open_items = [i.item_id for i in rep.items if i.action != "none" and is_open(i)]
    unproven = []
    for it in rep.items:
        if it.state == "done" and it.entry in entries and it.action != "none":
            e = entries[it.entry]
            left = detect(e, lp.spec, lp.root, codes)
            raised = sorted(codes & {str(c) for c in e.get("proof") or []})
            if left or raised:
                unproven.append(f"{it.item_id}: {', '.join(raised) or str(len(left)) + ' hits'}")
    if not add("V3 proof", not open_items and not unproven,
               "; ".join(([f"items not done: {', '.join(open_items)}"] if open_items else []) + unproven)
               or "every done item's rules and proof codes are clear"):
        return None
    audit_now = _audit_keys(lp, caps)
    added = sorted(set(audit_now) - set(base.get("audit") or []))
    if not add("V4 audit", not added, f"new findings: {', '.join(added)}" if added else
               f"no finding at warning or above that the baseline lacks ({len(audit_now)} known)"):
        return None
    classes: list[str] = []
    details: list[str] = []
    if before is not None:
        from tempergraph.improve.proposals import classify

        got = classify(before, lp.spec)
        classes = list(got.classes)
        rep.classes = classes
        details = [f"{d.get('class')}: {d.get('where')} {d.get('what')}" for d in got.details]
    answered = [i for i in rep.items if i.action == "owner" and i.state == "answered"]
    by_model_protected = [i.item_id for i in rep.items if i.by == "model" and i.protected]
    weak_ok = "weakening" not in classes or bool(answered)
    if not add("V5 change classes", weak_ok and not by_model_protected,
               ("a weakening no owner item answered: " + "; ".join(d for d in details if d.startswith("weakening")))
               if not weak_ok else ("a protected path changed by the model: " + ", ".join(by_model_protected))
               if by_model_protected else (", ".join(classes) or "no change of a class")
               + ("; weakening approved by the owner" if "weakening" in classes else "")):
        return None
    was_red = set(base.get("suites_failing") or [])
    red = _suites(lp.spec)
    worse = sorted(set(red) - was_red)
    if not add("V6 suites", not worse, "; ".join(worse) if worse else
               (f"pre-existing failures: {len(was_red)}" if was_red else "model-free suites pass")):
        return None
    model = diagram_model(lp.spec)
    write_json(pkg / "diagram" / "model.json", model, mode=0o644)
    (pkg / "diagram" / "workflow.md").write_text("```mermaid\n" + to_mermaid(model) + "\n```\n", encoding="utf-8")
    sha = _commit(place, f"upgrade({lp.spec.name}): regenerate the diagram")
    if sha:
        rep.commits.append({"entry": "diagram", "commit": sha})
    if model["digest"] != base.get("shape_digest"):
        was, now = set(base.get("units") or []), set(lp.spec.units)
        rep.shape_changed = [f"+{u}" for u in sorted(now - was)] + [f"-{u}" for u in sorted(was - now)] or ["edges"]
    add("V7 diagram", True, "shape changed: " + ", ".join(rep.shape_changed) if rep.shape_changed else "shape unchanged")
    if lp.workflow_version != base.get("workflow_version"):
        rep.stale = ["rubric scores and judge acceptance recorded for the earlier content are stale"]
    return load_package(pkg)


# -- finish (WUP §2.7) ------------------------------------------------------------------------------------------


def propose(rep: Report, base: Mapping[str, Any], lp: LoadedPackage, classes: Sequence[str] = ()) -> dict[str, Any]:
    was = dict(base.get("parse") or {})
    now = canonical(lp.spec)
    gone_units = set(was.get("units") or {}) - set(now.get("units") or {})
    old_in = {p.get("name") for p in ((was.get("input") or {}).get("parameters") or [])}
    new_in = {p.get("name") for p in ((now.get("input") or {}).get("parameters") or [])}

    def keys(doc: Mapping[str, Any]) -> set[str]:
        return {f"{u}.{k}" for u, d in (doc.get("units") or {}).items()
                for k in (((d or {}).get("step") or {}).get("produces") or {})}

    if gone_units or (old_in - new_in) or (keys(was) - keys(now)):
        level = "major"
    elif any(i.by in ("model", "person") for i in rep.items) or (new_in - old_in) or classes:
        level = "minor"
    else:
        level = "patch"
    major, minor, patch = semver(str(base.get("version") or "0.0.0"))
    new = {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[level]
    emajor = semver(rep.to_engine)[0]
    return {"level": level, "version": new, "requires_engine": f">={rep.to_engine},<{emajor + 1}"}


def _bump(place: Place, rep: Report, lp: LoadedPackage) -> None:
    pkg = _pkg(place)
    manifest = pkg / ".claude-plugin" / "plugin.json"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["version"] = rep.proposed["version"]
    write_json(manifest, doc, mode=0o644)
    if rep.proposed["level"] in ("major", "minor"):
        done = [i for i in rep.items if i.state in ("done", "answered") and i.action != "none"]
        write_json(pkg / "changes" / f"{rep.proposed['version']}.json", {
            "schema_version": 1, "version": rep.proposed["version"], "draft": True,
            "entries": [{"entry": i.entry, "by": i.by, "note": i.note} for i in done]}, mode=0o644)
    sha = _commit(place, f"upgrade({lp.spec.name}): version {rep.proposed['version']}")
    if sha:
        rep.commits.append({"entry": "version", "commit": sha})


def _stamp(place: Place, rep: Report, lp: LoadedPackage, base: Mapping[str, Any], caps: Mapping[str, Capabilities],
           entry_ids: Sequence[str]) -> None:
    by = {i.entry: i.by or "none" for i in rep.items}
    model = diagram_model(lp.spec)
    found = validate(lp.spec, caps)
    outcome = getattr(lp.spec, "outcome", None)
    rep.stamp = {
        "schema_version": 1, "engine_version": rep.to_engine, "workflow_api": lp.manifests.engine.workflow_api,
        "workflow_version": lp.workflow_version, "docs_digest": lp.docs_digest, "shape_digest": model["digest"],
        "entries_applied": [{"id": e, "by": by.get(e, "none")} for e in entry_ids],
        "tool_set": tool_set(lp.spec), "audit": _audit_keys(lp, caps),
        "outcome_revision": int(getattr(outcome, "revision", 0) or 0),
        "baseline": {"error": sum(1 for f in found if f.severity == "error"),
                     "warning": sum(1 for f in found if f.severity == "warning")},
        "upgrade_id": rep.upgrade_id, "stamped_at": now_iso(),
    }
    write_json(_pkg(place) / STAMP, rep.stamp, mode=0o644)
    sha = _commit(place, f"upgrade({lp.spec.name}): stamp for engine {rep.to_engine}")
    if sha:
        rep.commits.append({"entry": "stamp", "commit": sha})


def shares(items: Sequence[Item]) -> dict[str, Any]:
    done = [i for i in items if i.action != "none" and i.state in ("done", "answered")]
    count = {k: sum(1 for i in done if i.by == k) for k in ("transform", "model", "person")}
    total = len(done)
    return {"done": total, **count,
            "share": {k: (round(v / total, 3) if total else 0.0) for k, v in count.items()},
            "open": sum(1 for i in items if is_open(i)), "skipped": sum(1 for i in items if i.state == "skipped")}


def body(rep: Report) -> str:
    """The report as the pull request's text: counts and the entries' own notes, no run text."""
    lines = [f"Upgrade of `{rep.workflow}` from engine {rep.from_engine or 'unstamped'} to {rep.to_engine}.",
             f"Version {rep.from_version} to {rep.proposed.get('version')} ({rep.proposed.get('level')}); "
             f"`requires_engine` {rep.proposed.get('requires_engine')}.", "",
             f"Items done: {rep.shares.get('done', 0)} (transform {rep.shares.get('transform', 0)}, model "
             f"{rep.shares.get('model', 0)}, person {rep.shares.get('person', 0)}).", ""]
    lines += [f"- {i.item_id}: {i.state}" + (f" by {i.by}" if i.by else "") + (f". {i.note}" if i.note else "")
              for i in rep.items]
    lines += ["", "Verification:"] + [f"- {v.check}: {v.state}. {v.evidence}" for v in rep.checks]
    if rep.not_touched:
        lines += ["", "Considered and not touched: " + ", ".join(rep.not_touched)]
    return "\n".join(lines) + "\n"


# -- the verb ---------------------------------------------------------------------------------------------------


def _save(place: Place, rep: Report, name: str = "report.json", doc: Mapping[str, Any] | None = None) -> None:
    write_json(place.record / name, dict(doc) if doc is not None else rep.to_json())


def _load_json(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def upgrade(path: Path, caps: Mapping[str, Capabilities], *, no_assist: bool = False, stamp: bool = False,
            bump: bool = False, open_pr: bool = False, continue_id: str | None = None, cap_usd: float = 10.0,
            executor: str | None = None, assist: AssistFn | None = None, host: Any = None,
            engine: str = ENGINE_VERSION, folder: Path | None = None) -> Report:
    """Phases 1 to 7. `assist` runs the assisted and owner items and returns `{exit_code, items: {id: {state,
    by, reason}}, cost_usd}`; without it, or with `no_assist`, those items stay for a person."""
    root = path.resolve()
    try:
        src = load_package(root)
    except PackageNotLoaded as exc:
        return Report(workflow=root.name, exit_code=2, refused=f"the package does not load: {exc}")
    name = src.spec.name
    rep = Report(workflow=name, to_engine=engine)
    try:
        place = locate(root, name, engine)
    except UpgradeRefused as exc:
        rep.refused, rep.exit_code = str(exc), 2
        return rep
    rep.upgrade_id, rep.branch, rep.worktree = place.upgrade_id, place.branch, str(place.worktree)
    all_entries = [e for e in entries_between(None, engine, folder) if e.get("audience") == "workflow"]
    by_id = {str(e["id"]): e for e in all_entries}
    if continue_id is not None:
        saved = _load_json(place.record / "report.json")
        if continue_id != place.upgrade_id or not saved or not place.worktree.is_dir():
            rep.refused, rep.exit_code = f"no upgrade {continue_id!r} of {name} is in progress here", 2
            return rep
        base = _load_json(place.record / "baseline.json")
        rep.items = [Item(**i) for i in saved.get("items") or []]
        for key in ("from_engine", "from_version", "not_touched", "notes", "commits", "baseline_errors", "assist"):
            setattr(rep, key, saved.get(key) or getattr(rep, key))
    else:
        if _branch_exists(place.repo, place.branch) or place.worktree.exists():
            rep.refused, rep.exit_code = (f"the branch {place.branch} already exists; `tempergraph upgrade {name} "
                                          f"--continue {place.upgrade_id}` goes on with it"), 2
            return rep
        dirty = _dirty(place)
        if dirty:
            rep.refused, rep.exit_code = (f"the source has uncommitted changes ({dirty[0]}); commit or stash them "
                                          "first"), 2
            return rep
        prior = read_stamp(root)
        rep.from_engine = str(prior["engine_version"]) if prior else None
        rep.from_version = src.manifests.version
        base = baseline(src, caps)  # phase 2, on the unchanged package
        rep.baseline_errors = [f"{f['code']} {f['unit'] or ''}: {f['message']}".strip() for f in base["validation"]
                               if f["severity"] == "error"]
        between = [e for e in entries_between(rep.from_engine, engine, folder) if e.get("audience") == "workflow"]
        codes = {str(f["code"]) for f in base["validation"]}
        rep.items, rep.not_touched, rep.notes = plan(src, between, codes, no_assist=no_assist)  # phase 3
        ensure_state_root(state_root_path(place.repo))
        place.record.mkdir(parents=True, exist_ok=True, mode=0o700)
        _save(place, rep, "baseline.json", base)
        _save(place, rep, "plan.json", {"schema_version": 1, "upgrade_id": place.upgrade_id, "engine_version": engine,
                                        "workflow": name, "items": [asdict(i) for i in rep.items],
                                        "not_touched": rep.not_touched})
        place.worktree.parent.mkdir(parents=True, exist_ok=True)
        gitmod.git(["worktree", "add", "-q", "-b", place.branch, str(place.worktree), "HEAD"], place.repo)
        apply_transforms(place, rep, by_id, caps, name)  # phase 4
    pkg = _pkg(place)
    todo = [i for i in rep.items if i.action in ("assisted", "owner") and is_open(i)]
    if todo and (no_assist or assist is None):
        for i in todo:
            if i.action == "assisted":
                i.action = "manual"
        if assist is None and not no_assist:
            rep.warnings.append("no assist step is available; the assisted and owner items stay for a person")
    elif todo and assist is not None:  # phase 5
        got = dict(assist(Assist(upgrade_id=place.upgrade_id, record=place.record, worktree=place.worktree, package=pkg,
                                 items=todo, cap_usd=cap_usd, entries=by_id, base=base,
                                 executor=executor or (src.spec.upgrade or {}).get("executor"),
                                 protected=tuple((src.spec.upgrade or {}).get("protected") or PROTECTED_DEFAULT))))
        if int(got.get("exit_code") or 0) == 0:  # the run ended: its edits become one commit, its inputs go
            shutil.rmtree(place.worktree / ASSIST_DIR, ignore_errors=True)
            sha = _commit(place, f"upgrade({name}): assisted and owner items")
            if sha:
                rep.commits.append({"entry": "assist", "commit": sha})
        for i in todo:
            new = dict((got.get("items") or {}).get(i.item_id) or {})
            i.state, i.by = str(new.get("state") or i.state), new.get("by") or i.by
            i.reason = str(new.get("reason") or i.reason)
        rep.assist = {k: got.get(k) for k in ("thread_id", "cost_usd", "exit_code", "message") if k in got}
        code = int(got.get("exit_code") or 0)
        if code in (3, 5) or (code and any(is_open(i) for i in todo)):
            rep.exit_code = code if code in (3, 5) else 4
            rep.shares = shares(rep.items)
            _save(place, rep)
            return rep
    _reconcile(rep, by_id, pkg, caps, continue_id is not None)
    try:
        before: WorkflowSpec | None = load_package(root).spec
    except PackageNotLoaded:
        before = None
    lp = verify(place, rep, base, by_id, caps, before)  # phase 6
    rep.shares = shares(rep.items)
    if lp is None:
        rep.exit_code = 4
        _save(place, rep)
        return rep
    rep.proposed = propose(rep, base, lp, rep.classes)  # phase 7
    if bump:
        _bump(place, rep, lp)
        lp = load_package(pkg)
    if stamp:
        _stamp(place, rep, lp, base, caps, [str(e["id"]) for e in all_entries
                                            if e["id"] in {i.entry for i in rep.items} | set(rep.not_touched)])
    if open_pr:
        rep.pull_request = _open_pr(place, rep, lp, host)
    _save(place, rep)
    return rep


def _open_pr(place: Place, rep: Report, lp: LoadedPackage, host: Any) -> str | None:
    from tempergraph.improve.codehost import CodeHostError

    repo = lp.spec.issue_repository
    if host is None or not repo:
        rep.warnings.append("no pull request was opened: " + ("no code host credentials" if host is None else
                                                               "the workflow names no `issue_repository`"))
        return None
    labels = ["engine-upgrade"] + (["weakens-gate"] if any(
        v.check.startswith("V5") and "weakening" in v.evidence for v in rep.checks) else [])
    try:
        gitmod.git(["push", "-q", "origin", f"refs/heads/{place.branch}:refs/heads/{place.branch}"], place.repo)
        return str(host.create_draft_pr(repo, place.branch, host.default_branch(repo),
                                        f"[upgrade] {rep.workflow}: engine {rep.to_engine}", body(rep), labels))
    except (CodeHostError, gitmod.GitError) as exc:
        rep.warnings.append(f"no pull request was opened: {exc}")
        return None
