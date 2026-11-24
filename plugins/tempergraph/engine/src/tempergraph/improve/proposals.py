"""Clusters and the ranked backlog, proposals, change classes and the proposer (PRP-B11, PRP-B14, PRP-B15, B1 to B4,
B8, B10; plan T12.5).

Records live under the state root: `improve/proposals/<proposal_id>.json` (metadata, the patch and the
classes). A proposal's patch only ever touches workflow package files; the engine classifies it from the
parsed workflow before and after, never from the diff text, and nothing here merges a pull request or pushes
a default branch (PRP-AC2): `open` pushes only the proposal's own `improve/<id>` branch and asks the code
host for a draft.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tempergraph.contracts import Criterion, TextRef, WorkflowSpec
from tempergraph.docs import read_json, write_json
from tempergraph.improve import lessons as lessonsmod
from tempergraph.improve import params
from tempergraph.store.layout import now_iso, run_dir

AUTONOMY = ("record", "file", "propose", "trial")
SIDE = {"prompt": "producer", "lessons": "producer", "limits": "producer", "model": "producer", "tools": "producer",
        "flow": "producer", "brief": "grader", "criterion": "grader", "check": "grader", "judge_model": "grader",
        "outcome": "grader", "weakening": "grader"}
STATES = ("drafted", "refused", "trialling", "shown_better", "not_shown", "regressed", "aborted", "opened",
          "merged", "closed")
LADDER = {"none": 0, None: 0, "person": 1, "judge": 2, "check": 3}  # OUT-B20, OUT-B21, upward only


class ProposalError(ValueError):
    pass


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _sha(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:16]


def _ts(text: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


# -- autonomy (PRP-B11) -------------------------------------------------------------------------------------

def autonomy(spec: WorkflowSpec, machine: str | None = None) -> str:
    """The declared level (`improvement.autonomy` in the package's `tempergraph.json`, default `file`),
    lowered, never raised, by the machine's `TEMPERGRAPH_AUTONOMY`."""
    declared = "file"
    if spec.package_root is not None:
        try:
            doc = json.loads((spec.package_root / "tempergraph.json").read_text(encoding="utf-8"))
            got = ((doc.get("improvement") or {}).get("autonomy")) if isinstance(doc, dict) else None
            if got in AUTONOMY:
                declared = str(got)
        except (OSError, ValueError):
            pass
    if machine in AUTONOMY and AUTONOMY.index(str(machine)) < AUTONOMY.index(declared):
        return str(machine)
    return declared


# -- clusters and backlog (PRP-B12) -------------------------------------------------------------------------

def _findings(root: Path, workflow: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base = root / "runs" / workflow
    if not base.is_dir():
        return out
    for p in sorted(base.glob("*/findings.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out += [f for f in doc.get("findings") or [] if isinstance(f, dict)]
    return out


def cluster_key(f: Mapping[str, Any]) -> str:
    cause = str(f.get("cause") or "")
    if cause.startswith("judge_blocked:"):  # judge-sent-back retries cluster by unit and criterion
        return _sha("criterion", f.get("unit"), cause.split(":", 1)[1])
    return _sha(f.get("side"), f.get("workflow"), f.get("unit"), cause)


def saturation(root: Path, workflow: str, finding: Mapping[str, Any], version: str | None) -> int:
    """SRV-B5, PRP-B12: the corroborated observations the cluster of `finding` holds on one workflow version, the
    sum of the `review_weight` of its member findings recorded on it."""
    key = cluster_key(finding)
    return sum(int(f.get("review_weight") or 0) for f in _findings(root, workflow)
               if f.get("class") == "fault" and f.get("workflow_version") == version and cluster_key(f) == key)


def _session_cost(r: Mapping[str, Any]) -> float:
    u = r.get("usage") or {}
    for k in ("reported_cost_usd", "estimated_cost_usd"):
        if isinstance(u.get(k), int | float):
            return float(u[k])
    return 0.0


def _repeat_cost(root: Path, workflow: str, thread: str, unit: str) -> float:
    """Sessions of `unit` after its first attempt: the repeats whose cost the cluster's cause explains."""
    task = thread.partition("/")[2]
    total = 0.0
    for r in _jsonl(run_dir(root, workflow, task) / "run.jsonl"):
        if r.get("kind") == "agent_run" and r.get("unit") == unit and int(r.get("attempt") or 1) > 1:
            total += _session_cost(r)
    return total


def _issues(root: Path, workflow: str, threads: Iterable[str], fps: set[str]) -> list[str]:
    urls: list[str] = []
    for t in sorted(set(threads)):
        for r in _jsonl(run_dir(root, workflow, t.partition("/")[2]) / "loop.jsonl"):
            if r.get("kind") in ("issue_filed", "issue_commented") and r.get("fingerprint") in fps and r.get("url"):
                url = str(r["url"]).split("#", 1)[0]
                if url not in urls:
                    urls.append(url)
    return urls


def clusters(root: Path, workflow: str, now: datetime | None = None) -> list[dict[str, Any]]:
    """Fault findings grouped and ranked by `repeat_cost_usd + label_value × label_weight`, twins folded
    under the side attributed first (PRP-B12). From the local ledger; the shared store is release 2."""
    from tempergraph.improve.reliability import read_labels

    now = now or datetime.now(UTC)
    since = now - timedelta(days=int(params.value("cost.window_days")))
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in _findings(root, workflow):
        if f.get("class") != "fault":
            continue
        groups.setdefault(cluster_key(f), []).append(f)
    labels = [lab for lab in read_labels(root, workflow) if lab.get("source") == "person"
              and lab.get("value") == "disagree"]
    out = []
    for cid, members in groups.items():
        first = min(members, key=lambda f: str(f.get("at") or ""))
        unit = str(first.get("unit") or "")
        threads = {str(f.get("thread")) for f in members}
        recent = {str(f.get("thread")) for f in members if (_ts(f.get("at")) or now) >= since}
        cost = round(sum(_repeat_cost(root, workflow, t, unit) for t in recent), 6) if unit else 0.0
        weight = sum(1 for lab in labels if lab.get("unit") == unit)
        fps = {str(f.get("fingerprint")) for f in members}
        out.append({"cluster_id": cid, "workflow": workflow, "side": first.get("side"), "unit": unit or None,
                    "cause": first.get("cause"), "first_at": first.get("at"),
                    "findings": sorted(fps), "threads": sorted(threads), "issues": _issues(root, workflow, threads, fps),
                    "runs": len(threads), "distinct_requests": len({f.get("request_digest") for f in members
                                                                     if f.get("request_digest")}),
                    "machines": len({f.get("machine") for f in members if f.get("machine")}),
                    "repeat_cost_usd": cost, "label_weight": weight,
                    "review_weight": sum(int(f.get("review_weight") or 0) for f in members),  # SRV-B27
                    "score": round(cost + params.value("proposals.label_value") * weight, 6), "twin_of": None})
    by_twin: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for c in out:
        if c["side"] in ("engine", "workflow"):
            by_twin.setdefault((c["unit"], c["cause"]), []).append(c)
    hidden: set[str] = set()
    for pair in by_twin.values():
        if len(pair) == 2:
            first, second = sorted(pair, key=lambda c: str(c.get("first_at") or ""))
            first["twin_of"], second["twin_of"] = second["cluster_id"], first["cluster_id"]
            hidden.add(second["cluster_id"])
    shown = [c for c in out if c["cluster_id"] not in hidden]
    return sorted(shown, key=lambda c: (-c["score"], -c["runs"], c["cluster_id"]))


def cluster(root: Path, workflow: str, cluster_id: str) -> dict[str, Any]:
    for c in clusters(root, workflow):
        if c["cluster_id"] == cluster_id or c.get("twin_of") == cluster_id:
            return c if c["cluster_id"] == cluster_id else {**c, "cluster_id": cluster_id}
    raise ProposalError(f"no cluster {cluster_id!r} for {workflow}; `improve backlog {workflow}` lists them")


# -- change classes (PRP-B14, PRP-B15) -------------------------------------------------------------------------------

def _text(spec: WorkflowSpec, src: Any) -> str:
    from tempergraph.model.text import load_text

    if src in (None, "default"):
        return str(src)
    try:
        return load_text(spec, src)
    except Exception:  # noqa: BLE001 - an unreadable text is a change the validation reports
        return f"<unreadable {src}>"


def _judge_text(spec: WorkflowSpec, j: Any) -> str:
    from tempergraph.model.text import split_judge_file

    if j is None:
        return ""
    if j.file:
        return "\n".join(split_judge_file(_text(spec, TextRef(path=j.file))))
    return f"{j.stance}\n{j.brief}"


def _crit(c: Criterion) -> tuple[Any, ...]:
    return (c.text, c.check_method, c.severity, c.verified_by, json.dumps(c.verifier, sort_keys=True, default=str))


def _criteria(spec: WorkflowSpec) -> dict[tuple[str, str], Criterion]:
    out = {}
    for name, u in spec.units.items():
        for c in u.gate.criteria:
            out[(name, str(c.id or c.text))] = c
    if spec.outcome is not None:
        for c in spec.outcome.final:
            out[("outcome", str(c.id or c.text))] = c
        for name, io in spec.outcome.intermediate.items():
            for c in io.criteria:
                out[(name, str(c.id or c.text))] = c
    return out


def _source_digest(spec: WorkflowSpec, ref: Any) -> str | None:
    """A check's code, by the source of the module its reference names."""
    if ref is None:
        return None
    root = spec.package_root
    text = str(getattr(ref, "ref", ref))
    if root is not None and (root / "workflow").is_dir():
        h = hashlib.sha256(text.encode())
        for p in sorted((root / "workflow").rglob("*.py")):
            h.update(p.read_bytes())
        return h.hexdigest()[:16]
    return text


@dataclass(kw_only=True)
class Classified:
    classes: list[str]
    sides: list[str]
    details: list[dict[str, Any]] = field(default_factory=list)
    lessons_refusal: str | None = None
    added_text: list[str] = field(default_factory=list)


def classify(before: WorkflowSpec, after: WorkflowSpec) -> Classified:
    """PRP-B14, PRP-B15 from the two parsed workflows (PRP-AC1): a reformatted or reordered file changes nothing."""
    classes: set[str] = set()
    details: list[dict[str, Any]] = []
    added: list[str] = []

    def add(klass: str, where: str, what: str) -> None:
        classes.add(klass)
        details.append({"class": klass, "where": where, "what": what})

    if tuple(before.order) != tuple(after.order) or set(before.units) != set(after.units) \
            or dict(before.flow) != dict(after.flow):
        add("flow", "workflow", "order, units or flow changed")
    for name in sorted(set(before.units) & set(after.units)):
        b, a = before.units[name], after.units[name]
        if (b.route, b.route_targets, b.switch, b.kind) != (a.route, a.route_targets, a.switch, a.kind):
            add("flow", name, "route arm changed")
        bs, as_ = b.step, a.step
        if bs is not None and as_ is not None:
            tb, ta = _text(before, bs.prompt), _text(after, as_.prompt)
            if tb != ta:
                add("prompt", name, "template text")
                added += [ln for ln in ta.splitlines() if ln.strip() and ln not in tb.splitlines()]
            if (bs.timeout_s, bs.idle_s) != (as_.timeout_s, as_.idle_s):
                add("limits", name, "timeout or idle limit")
            if (bs.model, bs.executor) != (as_.model, as_.executor):
                add("model", name, "alias or executor")
            if (tuple(bs.tools), tuple(bs.commands)) != (tuple(as_.tools), tuple(as_.commands)):
                add("tools", name, "declared tools or command prefixes")
        bg, ag = b.gate, a.gate
        if (bg.retry_budget, bg.loop_budget) != (ag.retry_budget, ag.loop_budget):
            add("limits", name, "retry or loop budget")
            if ag.retry_budget > 2 * max(1, bg.retry_budget) or ag.loop_budget > 2 * max(1, bg.loop_budget):
                add("weakening", name, "a budget raised above 2x")
        if bs is not None and as_ is not None and (as_.timeout_s or 0) > 2 * (bs.timeout_s or 10 ** 9):
            add("weakening", name, "a timeout raised above 2x")
        jb, ja = bg.judge, ag.judge
        if _judge_text(before, jb) != _judge_text(after, ja):
            add("brief", name, "judge brief or stance")
        if (jb and (jb.model, jb.executor)) != (ja and (ja.model, ja.executor)):
            add("judge_model", name, "judge alias or executor")
        if jb is not None and ja is not None:
            tb_, ta_ = jb.tools, ja.tools
            if (tb_ is not None and (ta_ is None or not set(ta_) <= set(tb_))) or \
                    tuple(a.extra.get("views_add") or ()) != tuple(b.extra.get("views_add") or ()):
                add("weakening", name, "judge view set widened")
        if (_source_digest(before, bg.check), str(getattr(bg.check, "ref", bg.check))) != (
                _source_digest(after, ag.check), str(getattr(ag.check, "ref", ag.check))):
            add("check", name, "deterministic check code or reference")
    cb, ca = _criteria(before), _criteria(after)
    for key in sorted(set(cb) | set(ca)):
        unit, cid = key
        if key not in ca:
            add("weakening", unit, f"criterion {cid} removed")
            continue
        if key not in cb:
            add("outcome" if unit == "outcome" or after.outcome else "criterion", unit, f"criterion {cid} added")
            continue
        b_, a_ = cb[key], ca[key]
        if _crit(b_) == _crit(a_):
            continue
        add("outcome" if after.outcome is not None else "criterion", unit, f"criterion {cid} changed")
        if b_.severity == "blocker" and a_.severity != "blocker":
            add("weakening", unit, f"criterion {cid}: blocker made {a_.severity}")
        if LADDER.get(a_.verified_by, 0) < LADDER.get(b_.verified_by, 0):
            add("weakening", unit, f"criterion {cid}: verifier moved down {b_.verified_by} to {a_.verified_by}")
    if (before.outcome and before.outcome.statement) != (after.outcome and after.outcome.statement):
        add("outcome", "outcome", "statement")
    refusal = None
    for name in sorted(set(before.units) & set(after.units)):
        old = [dataclasses.asdict(x) for x in lessonsmod.load(before, name)]
        new = [dataclasses.asdict(x) for x in lessonsmod.load(after, name)]
        if old != new:
            add("lessons", name, "lessons entries")
            crit_texts = [c.text for c in after.units[name].gate.criteria]
            refusal = refusal or lessonsmod.classify_change(old, new, crit_texts)
            added += [str(e["text"]) for e in new if e not in old]
    found = sorted(classes)
    return Classified(classes=found, sides=sorted({SIDE[c] for c in found}), details=details,
                      lessons_refusal=refusal, added_text=added)


def _request_shingles(root: Path, workflow: str, threads: Iterable[str]) -> set[str]:
    """Four-word spans of the member runs' requests, from their local evidence (the proposer's reading set,
    PRP-B23), so a patch that copies a run's words is refused `literal`."""
    from tempergraph.improve.record import read_evidence

    out: set[str] = set()
    for t in threads:
        ev = read_evidence(root, workflow, t.partition("/")[2])
        req = " ".join(str(v) for v in dict(ev.get("request") or {}).values())
        words = re.findall(r"[a-z0-9]+", req.lower())
        out |= {" ".join(words[i:i + 4]) for i in range(max(0, len(words) - 3))}
    return out


def literal_hits(added: Sequence[str], shingles: set[str]) -> list[str]:
    hits = []
    for text in added:
        hits += lessonsmod.literals(text)
        words = re.findall(r"[a-z0-9]+", text.lower())
        if any(" ".join(words[i:i + 4]) in shingles for i in range(max(0, len(words) - 3))):
            hits.append("request_words")
    return sorted(set(hits))


# -- patches -------------------------------------------------------------------------------------------------

def patch_paths(patch: str) -> list[str]:
    paths = []
    for ln in patch.splitlines():
        if ln.startswith(("--- ", "+++ ")):
            p = ln[4:].split("\t", 1)[0].strip()
            if p == "/dev/null":
                continue
            paths.append(p[2:] if p.startswith(("a/", "b/")) else p)
    return paths


def _inside(paths: Iterable[str]) -> bool:
    return all(p and not p.startswith("/") and ".." not in Path(p).parts for p in paths)


def apply_patch(package: Path, patch: str, dest: Path) -> Path:
    """A copy of the package with the patch applied; the package itself is untouched."""
    from tempergraph.git import GitError, git

    if not _inside(patch_paths(patch)):
        raise ProposalError("outside_package")
    shutil.copytree(package, dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    try:
        git(["apply", "--whitespace=nowarn", "-"], dest, stdin=patch if patch.endswith("\n") else patch + "\n")
    except GitError as exc:
        raise ProposalError("stale_base") from exc
    return dest


def package_digest(package: Path) -> str:
    """The package files a proposal reads, minus `evals/` (case sets and calibration move on their own,
    outside the content digest as in PKG-AC7), caches and git metadata."""
    h = hashlib.sha256()
    for p in sorted(package.rglob("*")):
        rel = p.relative_to(package)
        if not p.is_file() or rel.parts[0] in ("evals", ".git") or "__pycache__" in rel.parts:
            continue
        h.update(str(rel).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:16]


# -- proposal records (PRP-B13) -----------------------------------------------------------------------------

def proposals_dir(root: Path) -> Path:
    return root / "improve" / "proposals"


def save(root: Path, rec: Mapping[str, Any]) -> None:
    write_json(proposals_dir(root) / f"{rec['proposal_id']}.json", dict(rec))


def load_proposal(root: Path, proposal_id: str) -> dict[str, Any]:
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", proposal_id):
        raise ProposalError(f"{proposal_id!r} is not a proposal id")
    path = proposals_dir(root) / f"{proposal_id}.json"
    if not path.is_file():
        raise ProposalError(f"no proposal {proposal_id}")
    return dict(read_json(path, "proposal"))


def record(root: Path, spec: WorkflowSpec, cl: Mapping[str, Any], patch: str, *, author: str, rule: str,
           proposal_id: str | None = None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Classifies a patch against the current package and records the proposal, `drafted` or `refused`."""
    from tempergraph.model.validate import validate
    from tempergraph.package.loader import PackageNotLoaded, load

    pkg = spec.package_root
    if pkg is None:
        raise ProposalError("the workflow has no package folder")
    pid = proposal_id or uuid.uuid4().hex[:12]
    rec: dict[str, Any] = {"schema_version": 1, "proposal_id": pid, "workflow": spec.name,
                           "base_version": spec.version, "base_digest": package_digest(pkg),
                           "cluster_id": cl.get("cluster_id"), "cluster": {k: cl.get(k) for k in (
                               "side", "unit", "cause", "runs", "findings", "issues", "threads")},
                           "author": author, "patch": patch, "classes": [], "side": None,
                           "rule": " ".join(rule.split())[:300], "state": "drafted", "refusal": None,
                           "at": now_iso(), **dict(extra or {})}

    def refuse(code: str, **why: Any) -> dict[str, Any]:
        rec.update(state="refused", refusal=code, **why)
        save(root, rec)
        return rec

    if str(cl.get("side") or "") == "engine" or str(cl.get("side") or "").startswith("executor:"):
        return refuse("engine_side")  # PRP-B10: the loop drafts no engine code
    if not patch.strip():
        return refuse("empty_patch")
    if not _inside(patch_paths(patch)):
        return refuse("outside_package")
    if lessonsmod.literals(rec["rule"]) or re.search(r"\b\w+-\d+\b|#\d+", rec["rule"]):
        return refuse("literal", literal=["rule"])
    with tempfile.TemporaryDirectory(prefix="tg-proposal-") as tmp:
        try:
            dest = apply_patch(pkg, patch, Path(tmp) / pkg.name)
        except ProposalError as exc:
            return refuse(str(exc))
        try:
            after = load(dest)
        except PackageNotLoaded as exc:
            return refuse("invalid", validation=[str(exc)])
        finally:
            load(pkg)  # the engine's import map points at the live package again
        from tempergraph.executors.capabilities import DECLARED

        errors = [f"{f.code}: {f.message}" for f in validate(after, DECLARED) if f.severity == "error"]
        if errors:
            return refuse("invalid", validation=errors[:20])
        c = classify(spec, after)
    rec.update(classes=c.classes, details=c.details,
               side=c.sides[0] if len(c.sides) == 1 else ("mixed" if c.sides else None))
    if not c.classes:
        return refuse("no_change")
    if len(c.sides) > 1:
        return refuse("mixed_sides")  # PRP-B1
    if "weakening" in c.classes and author != "person":
        return refuse("weakening")  # PRP-B2: weakening is a person's act
    if c.lessons_refusal:
        return refuse(c.lessons_refusal)
    hits = literal_hits(c.added_text, _request_shingles(root, spec.name, cl.get("threads") or ()))
    if hits:
        return refuse("literal", literal=hits)  # PRP-B3
    if "weakening" in c.classes:
        rec["labels"] = ["weakens-gate"]
    if "tools" in c.classes and author == "proposer":
        rec["review_only"] = True  # a widening tools patch is opened for review, never trialled alone (ADR-0080)
    save(root, rec)
    return rec


# -- the proposer (PRP-B4) -----------------------------------------------------------------------------------

PROPOSER_BRIEF = """You improve one workflow package of a self-improvement loop by one small change.

The problem below is a cluster of findings the engine recorded across runs: a cause code, the unit, how
often, and the engine's drafted remedy. Edit files of the workflow package in this folder only: a step's
template, its lessons file (`lessons/<unit>.json`), its limits, model or tools; or, for a grading problem,
the judge brief, a criterion or a check. Never change a step together with the gate that grades it. Never
remove a criterion, lower a severity or widen what a judge may read. State the general rule your change
encodes in one sentence, with no ticket id, URL, number or quotation from a run.

End with one line: RULE: <the sentence>."""

JUDGE_CRITERIA = (
    Criterion(id="addresses-cause", text="The change addresses the cluster's recorded cause at its unit",
              check_method="Compare the diff with the cause code and the drafted remedy"),
    Criterion(id="general-rule", text="The change states one general rule, not one run's specifics",
              check_method="Read the rule sentence and every added line"),
)


def _brief(cl: Mapping[str, Any]) -> str:
    return (f"## Cluster\n- cause: {cl.get('cause')}\n- side: {cl.get('side')}\n- unit: {cl.get('unit')}\n"
            f"- runs: {cl.get('runs')}, distinct requests: {cl.get('distinct_requests')}\n"
            f"- repeat cost (30 days): ${float(cl.get('repeat_cost_usd') or 0):.2f}\n")


def propose(root: Path, spec: WorkflowSpec, cl: Mapping[str, Any], executor: Any, *,
            judge_executor: Any | None = None, worktrees: Path | None = None,
            alias: str = "medium", effort: str = "max") -> dict[str, Any]:
    """`improve propose <cluster>` without `--patch`: the proposer's step in its own worktree on branch
    `improve/<id>`, the engine's check (apply, validate, class check), then an independent judge."""
    from tempergraph.contracts import EventSink, GateSpec, JudgeSpec, SessionOptions, SessionRequest
    from tempergraph.git import GitError, git, main_checkout
    from tempergraph.run.guard import view_set
    from tempergraph.run.judging import JudgeInputs, Unparsed, derive, parse_judgement, render_judge

    if str(cl.get("side") or "") == "engine" or str(cl.get("side") or "").startswith("executor:"):
        return record(root, spec, cl, "", author="proposer", rule="")
    pkg = spec.package_root
    repo = main_checkout(pkg) if pkg is not None else None
    if pkg is None or repo is None:
        raise ProposalError("the workflow package is not inside a git repository; the proposer needs a branch")
    pid = uuid.uuid4().hex[:12]
    branch = f"improve/{pid}"
    wt = (worktrees or repo.parent / f"{repo.name}.worktrees") / f"improve--{pid}"
    try:
        git(["worktree", "add", "-q", "-b", branch, str(wt), "HEAD"], repo)
    except GitError as exc:
        raise ProposalError(f"worktree: {exc}") from exc
    rel = pkg.resolve().relative_to(repo.resolve())
    work_pkg = wt / rel
    prompt = PROPOSER_BRIEF + "\n\n" + _brief(cl)
    req = SessionRequest(kind="step", prompt=prompt, workdir=work_pkg, alias=alias,
                         session_key=f"improve.{pid}.step", tools=("read", "search", "list", "edit", "write"),
                         timeout_s=1800, in_engine_worktree=True,
                         options=SessionOptions(effort=effort))  # type: ignore[arg-type]
    res = executor.run_step(req, EventSink())
    spend = {"sessions": 1, "reported": res.usage.reported_cost_usd}
    git(["add", "-A"], wt)  # everything the session touched, so a write outside the package is seen
    patch = git(["diff", "--cached", "--relative", "--", "."], work_pkg)
    changed = [ln for ln in git(["diff", "--cached", "--name-only"], wt).splitlines() if ln]
    outside = [p for p in changed if Path(p).parts[:len(rel.parts)] != rel.parts]
    m = re.search(r"^RULE:\s*(.+)$", res.text or "", re.M)
    rule = m.group(1).strip() if m else ""
    extra = {"branch": branch, "worktree": str(wt), "spend": spend}
    if outside:
        rec = record(root, spec, cl, "", author="proposer", rule=rule, proposal_id=pid, extra=extra)
        rec.update(state="refused", refusal="outside_package", outside=outside)
        save(root, rec)
        return rec
    rec = record(root, spec, cl, patch, author="proposer", rule=rule, proposal_id=pid, extra=extra)
    if rec["state"] != "drafted":
        return rec
    jex = judge_executor or executor
    gate = GateSpec(judge=JudgeSpec(stance="Verify the change, not the claim."), criteria=JUDGE_CRITERIA)
    jprompt = render_judge(JudgeInputs(gate=gate, stance="Verify the change, not the claim.",
                                       brief="Grade the diff against the cluster.", request=_brief(cl),
                                       references={"diff": patch[:20000], "rule": rule}))
    from tempergraph.contracts import StepSpec

    jres = jex.run_judge(SessionRequest(kind="judge", prompt=jprompt, workdir=work_pkg, alias=alias,
                                        session_key=f"improve.{pid}.judge", timeout_s=1800,
                                        options=SessionOptions(effort=effort)),  # type: ignore[arg-type]
                         view_set(StepSpec(), [], jex.capabilities()), EventSink())
    spend["sessions"] = 2
    try:
        verdict = str(derive(parse_judgement(jres.text, gate), gate, None).verdict)
    except Unparsed:
        verdict = "ESCALATE"
    rec["judge"] = {"verdict": verdict}
    if verdict != "PROCEED":
        rec.update(state="refused", refusal="judge_not_met")
    else:
        git(["-c", "user.name=tempergraph", "-c", "user.email=engine@localhost", "commit", "-q", "-m",
             f"improve({spec.name}): {rule[:60]}"], wt)
    save(root, rec)
    return rec


# -- opening (PRP-B8) ----------------------------------------------------------------------------------------

ISSUE_URL = re.compile(r"^https?://[^/\s]+/([A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100})/issues/([0-9]{1,9})$")


def issue_ref(url: Any) -> tuple[str, int] | None:
    """`(owner/name, number)` of an issue URL of the loop's own records, none for any other text (PRP-B24)."""
    m = ISSUE_URL.match(str(url))
    return (m.group(1), int(m.group(2))) if m else None


def report_body(rec: Mapping[str, Any], trial: Mapping[str, Any] | None, *, repo: str | None = None) -> str:
    """The pull request text: counts, metrics, spend, the noise floor, classes and the rule; no run text. A
    `Closes #<n>` line for each issue of the cluster that is in `repo` (PRP-B24)."""
    rows = ["Opened by the tempergraph self-improvement loop. A person decides; the loop never merges.", "",
            f"**Rule** {rec.get('rule')}", f"**Classes** {', '.join(rec.get('classes') or [])} "
            f"(side {rec.get('side')}); author {rec.get('author')}.",
            f"**Cluster** `{rec.get('cluster_id')}`: cause `{(rec.get('cluster') or {}).get('cause')}` at "
            f"`{(rec.get('cluster') or {}).get('unit')}`, {(rec.get('cluster') or {}).get('runs')} runs."]
    closes: list[int] = []
    for url in (rec.get("cluster") or {}).get("issues") or []:
        rows.append(f"Refs {url}")
        ref = issue_ref(url)
        if repo and ref and ref[0] == repo and ref[1] not in closes:
            closes.append(ref[1])
    rows += [f"Closes #{n}" for n in closes]
    if "weakening" in (rec.get("classes") or []):
        rows.append("**Weakens a gate**: " + "; ".join(d["what"] for d in rec.get("details") or []
                                                       if d.get("class") == "weakening"))
    if trial:
        c = trial.get("counts") or {}
        rows += ["", f"**Trial** `{trial.get('trial_id')}`: {trial.get('decision')}"
                 + (f" ({trial.get('reason')})" if trial.get("reason") else "")
                 + f" on `{trial.get('target_metric')}`.",
                 f"Pairs: {c.get('wins', 0)} wins, {c.get('losses', 0)} losses, {c.get('ties', 0)} ties "
                 f"out of sample; {c.get('in_sample', 0)} in-sample pairs reported apart.",
                 "Guards: " + ", ".join(f"{g.get('name')} {g.get('state')}" for g in trial.get("guards") or []) + ".",
                 f"Noise floor: {trial.get('noise_floor')}. Spend: A ${float((trial.get('spend') or {}).get('A', 0)):.2f},"
                 f" B ${float((trial.get('spend') or {}).get('B', 0)):.2f}."]
        rows += [f"Warning: {w}" for w in trial.get("warnings") or []]
    else:
        rows += ["", "Not trialled (autonomy `propose`, or a review-only change)."]
    return "\n".join(rows)


def open_pr(root: Path, spec: WorkflowSpec, proposal_id: str, host: Any, *, push: bool = True) -> dict[str, Any]:
    """`improve open`: pushes the proposal's own branch and opens a draft pull request; never a merge."""
    from tempergraph.git import GitError, git, main_checkout
    from tempergraph.improve.codehost import CodeHostError, _check_branch

    rec = load_proposal(root, proposal_id)
    trial = None
    if rec.get("trial_id"):
        from tempergraph.improve.trials import load_trial

        trial = load_trial(root, str(rec["trial_id"]))
    if rec.get("state") not in ("shown_better", "drafted"):
        raise ProposalError(f"proposal {proposal_id} is {rec.get('state')}; only shown_better (or an untrialled "
                            "drafted one) opens")
    repo = spec.issue_repository
    if not repo:
        raise ProposalError(f"{spec.name} names no repository (`issue_repository`)")
    branch = _check_branch(str(rec.get("branch") or f"improve/{proposal_id}"))
    if push:
        checkout = main_checkout(spec.package_root) if spec.package_root else None
        if checkout is None:
            raise ProposalError("the workflow package is not inside a git repository")
        try:
            git(["push", "-q", "origin", f"refs/heads/{branch}:refs/heads/{branch}"], checkout)
        except GitError as exc:
            return {**rec, "open_error": f"push failed: {exc}"}
    try:
        base = host.default_branch(repo)
        url = host.create_draft_pr(repo, branch, base, f"[loop] {spec.name}: {str(rec.get('rule'))[:80]}",
                                   report_body(rec, trial, repo=repo), list(rec.get("labels") or []) + ["tempergraph-loop"])
    except CodeHostError as exc:
        return {**rec, "open_error": str(exc)}  # PRP-B16, PRP-B17, PRP-B20, PRP-B7, PRP-B8: stays shown_better; `open` can be rerun
    rec.update(state="opened", pull_request=url, opened_at=now_iso())
    save(root, rec)
    return rec
