"""Authoring sessions (AUT §2.1, §2.6, §2.8): `author start|intake|check|show|list|drop|approve`.

A session is a folder `<state root>/authoring/<id>/` holding `authoring.json`, the draft `outcome.json` and
`blueprint.json`, and `sources/`. Every verb here is model-free and writes only inside that folder (AUT-AC-4).
A phase approval records the digest of the part of the drafts that phase owns; an approval whose part changed
since counts as cleared, with every later one (AUT §4), so a session resumes from `author show` alone (AUT-AC-5).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import secrets
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tempergraph.author.blueprint import digest
from tempergraph.author.criteria_lint import lint, sufficiency
from tempergraph.author.inventory import KINDS, files, inventory
from tempergraph.docs import write_json
from tempergraph.store.layout import now_iso

PATHS = ("solution", "sources", "chat")
PHASES = {1: "intake", 2: "final outcome", 3: "work backwards", 4: "verifications", 5: "steps' work",
          6: "start and routing", 7: "approval", 8: "scaffold", 9: "verify, register, stamp"}
APPROVABLE = range(1, 8)
VERIFIER_KEYS = ("verified_by", "verifier", "source")
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


class AuthorRefused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(kw_only=True)
class Session:
    folder: Path
    record: dict[str, Any]
    outcome: dict[str, Any]
    blueprint: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.record.get("id"))

    def save(self) -> None:
        write_json(self.folder / "authoring.json", self.record, mode=0o644)


def sessions_root(state_root: Path) -> Path:
    return state_root / "authoring"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def open_session(state_root: Path, sid: str) -> Session:
    folder = sessions_root(state_root) / sid
    if not re.match(r"^[a-z0-9-]+$", sid) or not (folder / "authoring.json").is_file():
        raise AuthorRefused("no-session", f"no authoring session {sid!r} on this state root")
    try:
        return Session(folder=folder, record=_json(folder / "authoring.json"), outcome=_json(folder / "outcome.json"),
                       blueprint=_json(folder / "blueprint.json"))
    except (OSError, ValueError) as exc:
        raise AuthorRefused("session-unreadable", f"{folder}: {type(exc).__name__}") from exc


def _finished(rec: Mapping[str, Any]) -> bool:
    return bool(rec.get("scaffolded") or rec.get("finished_at"))


def all_sessions(state_root: Path) -> list[Session]:
    root = sessions_root(state_root)
    out = []
    for p in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            out.append(open_session(state_root, p.name))
        except AuthorRefused:
            continue
    return out


def _blank_outcome() -> dict[str, Any]:
    return {"schema_version": 1, "revision": 1, "statement": "", "deliverables": [], "final": [],
            "intermediate": {}, "assumptions": [], "revisions": []}


def start(state_root: Path, name: str, path: str | list[str], *, mode: str = "new",
          today: dt.date | None = None) -> Session:
    """AUT §2.1 `author start`; one open session per name (AUT §4)."""
    if not SLUG.match(name):
        raise AuthorRefused("name-invalid", f"{name!r} is not a workflow name (a lowercase slug)")
    paths = [path] if isinstance(path, str) else list(path)
    if mode == "new" and (not paths or any(p not in PATHS for p in paths)):
        raise AuthorRefused("path-invalid", f"--from takes {', '.join(PATHS)}")
    for s in all_sessions(state_root):
        if s.record.get("name") == name and not _finished(s.record):
            raise AuthorRefused("session-open", f"session {s.id} for {name!r} is open; finish or drop it first")
    day = (today or dt.date.today()).strftime("%Y%m%d")
    sid = f"{name}-{day}-{secrets.token_hex(2)}"
    folder = sessions_root(state_root) / sid
    (folder / "sources").mkdir(parents=True)
    record = {"schema_version": 1, "id": sid, "name": name, "path": paths[0] if len(paths) == 1 else paths,
              "mode": mode, "started_at": now_iso(), "sources": [], "candidates": [], "phases": [],
              "decisions": [], "blueprint_digest": None, "outcome_revision": None}
    s = Session(folder=folder, record=record, outcome=_blank_outcome(),
                blueprint={"schema_version": 1, "name": name, "units": []})
    write_json(folder / "outcome.json", s.outcome, mode=0o644)
    write_json(folder / "blueprint.json", s.blueprint, mode=0o644)
    s.save()
    return s


def revise(state_root: Path, package: Path) -> Session:
    """AUT §2.8 revise: a `mode: revise` session holding copies of the package's drafts and record."""
    try:
        name = _json(package / "tempergraph.json")["name"]
        outcome, bp = _json(package / "outcome.json"), _json(package / "blueprint.json")
        prior = _json(package / "authoring.json") if (package / "authoring.json").is_file() else {}
    except (OSError, ValueError, KeyError) as exc:
        raise AuthorRefused("package-unreadable", f"{package}: {type(exc).__name__}") from exc
    s = start(state_root, str(name), "revise", mode="revise")
    s.outcome, s.blueprint = outcome, bp
    keep = {k: prior[k] for k in ("sources", "candidates", "decisions", "issue_repository", "routing", "author",
                                  "phases", "blueprint_digest", "outcome_revision") if k in prior}
    # the package's approvals come along: an unchanged part stays approved, the first changed one and every
    # later one are cleared, so revise asks again only from where the drafts moved (AUT §2.7 step 3)
    s.record.update(keep, package=str(package.resolve()), base_revision=outcome.get("revision"))
    write_json(s.folder / "outcome.json", outcome, mode=0o644)
    write_json(s.folder / "blueprint.json", bp, mode=0o644)
    s.save()
    return s


def intake(s: Session, paths: list[Path], workspace: Path | None, *, kind: str | None = None,
           artifact: str | None = None, unit: str | None = None, outside: bool = False) -> list[dict[str, Any]]:
    """AUT §2.3 `author intake`: copy each file into `sources/` and record its inventory."""
    if kind is not None and kind not in KINDS:
        raise AuthorRefused("kind-invalid", f"--kind takes {', '.join(KINDS)}")
    default = "solution" if s.record.get("path") == "solution" else "reference"
    saved_dir = (s.folder / "sources").resolve()
    plan: list[tuple[Path, str, bool]] = []
    for given in paths:
        p = given.resolve()
        if not p.exists():
            raise AuthorRefused("source-missing", f"{given} does not exist")
        saved = p.is_relative_to(saved_dir)
        inside = workspace is not None and p.is_relative_to(workspace.resolve())
        if not (saved or inside or outside):
            raise AuthorRefused("path-outside-workspace", f"{given} is outside the workspace; pass --outside only "
                                "for a path the person named")
        base = saved_dir if saved else workspace.resolve() if inside and workspace is not None else None
        for f in files(p):
            plan.append((f, f.relative_to(base).as_posix() if base is not None else str(f), saved))
    added = []
    n_src = len(s.record["sources"])
    n_cand = len(s.record["candidates"])
    for f, rel, saved in plan:
        n_src += 1
        sid = f"s{n_src}"
        src = inventory(f, rel, sid, kind=kind or default, saved=saved, first_candidate=n_cand + 1,
                        artifact=artifact, unit=unit)
        n_cand += len(src.candidates)
        doc = src.to_json()
        if saved:
            doc["file"] = rel
        else:
            copy = f"{sid}-{f.name}"
            shutil.copyfile(f, s.folder / "sources" / copy)
            doc["file"] = copy
        s.record["sources"].append(doc)
        s.record["candidates"] += [c.to_json() for c in src.candidates]
        added.append(doc)
    s.save()
    return added


# -- phases --------------------------------------------------------------------------------------------------


def _strip(c: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in c.items() if k not in VERIFIER_KEYS}


def part(s: Session, phase: int) -> str:
    """The digest of what `phase` owns (AUT §2.8)."""
    o, bp = s.outcome, s.blueprint
    if phase == 1:
        doc: Any = [[x.get("id"), x.get("digest"), x.get("kind")] for x in s.record.get("sources") or []]
    elif phase == 2:
        doc = {"statement": o.get("statement"), "deliverables": o.get("deliverables"),
               "final": [_strip(c) for c in o.get("final") or []]}
    elif phase == 3:
        doc = {u: {**{k: v for k, v in (io or {}).items() if k != "criteria"},
                   "criteria": [_strip(c) for c in (io or {}).get("criteria") or []]}
               for u, io in (o.get("intermediate") or {}).items()}
    elif phase == 4:
        crits = list(o.get("final") or []) + [c for io in (o.get("intermediate") or {}).values()
                                              for c in (io or {}).get("criteria") or []]
        doc = [[c.get("id"), *[c.get(k) for k in VERIFIER_KEYS]] for c in crits]
    elif phase == 5:
        doc = {k: v for k, v in bp.items() if k != "input"}
    elif phase == 6:
        doc = {"input": bp.get("input"), "routing": s.record.get("routing")}
    else:
        doc = [digest(bp), digest(o)]
    return digest(doc)


def approvals(s: Session) -> tuple[list[dict[str, Any]], list[int]]:
    """(effective approvals in phase order, phases cleared): the walk stops at the first missing or stale one."""
    by_phase = {int(p["phase"]): p for p in s.record.get("phases") or [] if isinstance(p, dict) and "phase" in p}
    good, cleared = [], []
    stale = False
    for ph in APPROVABLE:
        p = by_phase.get(ph)
        if p is None:
            stale = True
            continue
        if stale or p.get("digest") != part(s, ph):
            stale = True
            cleared.append(ph)
            continue
        good.append(p)
    return good, cleared


def next_phase(s: Session) -> int:
    good = {int(p["phase"]) for p in approvals(s)[0]}
    for ph in APPROVABLE:
        if ph not in good:
            return ph
    return 9 if s.record.get("scaffolded") else 8


def _criteria(o: Mapping[str, Any]) -> list[tuple[str | None, Mapping[str, Any]]]:
    out: list[tuple[str | None, Mapping[str, Any]]] = [(None, c) for c in o.get("final") or []]
    out += [(u, c) for u, io in (o.get("intermediate") or {}).items() for c in (io or {}).get("criteria") or []]
    return out


def check(s: Session, caps: Mapping[str, Any]) -> dict[str, Any]:
    """AUT §2.1 `author check`: OUT §4 on the outcome, SCF §2.1 on the blueprint, the criteria lint and the
    sufficiency check, coverage and trust. Read-only."""
    from tempergraph.author import blueprint as bpm
    from tempergraph.run.outcome import parse_outcome

    findings: list[dict[str, Any]] = []
    parsed = parse_outcome(s.outcome) if s.outcome.get("final") else None
    if isinstance(parsed, list):
        findings += [{"code": f.code, "unit": f.unit, "message": f.message, "severity": f.severity,
                      "where": "outcome"} for f in parsed]
        parsed = None
    linted = lint(s.outcome)
    findings += [{**f.to_json("check"), "where": "criteria"} for f in linted]
    enough = sufficiency(s.outcome, linted)
    bp = None
    if s.blueprint.get("units"):
        got = bpm.parse(s.blueprint)
        if isinstance(got, list):
            findings += [{"code": f.code, "unit": f.unit, "message": f.message, "severity": f.severity,
                          "where": "blueprint"} for f in got]
        else:
            bp = got
            findings += [{"code": f.code, "unit": f.unit, "message": f.message, "severity": f.severity,
                          "where": "blueprint"} for f in bpm.check(got, caps, parsed, s.outcome)]
    unclassified = [str(c.get("id")) for _, c in _criteria(s.outcome) if not c.get("verified_by")]
    report: dict[str, Any] = {
        "schema_version": 1, "id": s.id, "findings": findings,
        "sufficiency": [f.message for f in enough], "unclassified": unclassified,
        "verification": verification(s, parsed, bp),
        "ok": not any(f.get("severity") == "error" for f in findings) and not enough and not unclassified}
    if s.record.get("mode") == "revise":
        report["changes"] = changes(s)
        base = s.record.get("base_revision")
        if report["changes"] and isinstance(base, int) and int(s.outcome.get("revision") or 0) <= base:
            report["findings"].append({"code": "revision-not-bumped", "unit": None, "severity": "error",
                                       "where": "outcome", "message": f"the outcome changed; its revision must "
                                       f"be above {base}"})
            report["ok"] = False
    return report


def verification(s: Session, parsed: Any, bp: Any) -> dict[str, Any]:
    """The verification table with each criterion's trust as it will be once scaffolded (OUT §2.3): a check is
    `deterministic` when the session holds a good example for its unit or artifact, since scaffold writes the
    must-pass and must-fail fixtures from it (SCF §2.7)."""
    from tempergraph.run.outcome_trust import TRUSTED

    goods = [x for x in s.record.get("sources") or [] if x.get("kind") == "example_good"]
    producer = {}
    if bp is not None:
        producer = {k: u.name for u in bp.units for k in u.produces}

    def trust(c: Mapping[str, Any], unit: str | None) -> str:
        by = c.get("verified_by")
        if by == "person":
            return "human"
        if by in (None, "none"):
            return "unverified"
        if by == "check":
            fixtures = any((x.get("unit") or producer.get(str(x.get("artifact")))) in (unit, None) for x in goods)
            return "deterministic" if fixtures else "uncalibrated"
        return "uncalibrated"

    rows = [{"unit": u or "outcome", "id": c.get("id"), "severity": c.get("severity", "blocker"),
             "verified_by": c.get("verified_by") or None, "source": c.get("source"), "trust": trust(c, u),
             "serves": list(c.get("serves") or [])} for u, c in _criteria(s.outcome)]
    profile: dict[str, int] = {}
    for r in rows:
        profile[r["trust"]] = profile.get(r["trust"], 0) + 1
    units = sorted({r["unit"] for r in rows if r["unit"] != "outcome"})
    coverage = []
    for r in rows:
        if r["unit"] != "outcome":
            continue
        serving = {x["unit"] for x in rows if r["id"] in x["serves"] and x["trust"] in TRUSTED}
        missing = [u for u in units if u not in serving]
        coverage.append({"criterion": r["id"], "trust": r["trust"],
                         "covered": r["trust"] in TRUSTED or (bool(units) and not missing), "missing_units": missing})
    return {"rows": rows, "profile": profile, "coverage": coverage}


RANK = {"unverified": 0, "uncalibrated": 1, "deterministic": 2, "calibrated": 2, "human": 2}


def changes(s: Session) -> list[dict[str, Any]]:
    """AUT §2.8 revise: each criterion's change class against the package's outcome."""
    pkg = Path(str(s.record.get("package") or ""))
    try:
        base = _json(pkg / "outcome.json")
    except (OSError, ValueError):
        return []
    was = {str(c.get("id")): (u, c) for u, c in _criteria(base)}
    now = {str(c.get("id")): (u, c) for u, c in _criteria(s.outcome)}
    tmp = dataclasses.replace(s, outcome=base)
    t_was = {str(r["id"]): r["trust"] for r in verification(tmp, None, None)["rows"]}
    t_now = {str(r["id"]): r["trust"] for r in verification(s, None, None)["rows"]}
    out = []
    for cid in sorted(set(was) | set(now)):
        if cid not in now:
            out.append({"criterion": cid, "class": "weakening", "why": "removed"})
            continue
        if cid not in was:
            out.append({"criterion": cid, "class": "strengthening", "why": "added"})
            continue
        a, b = was[cid][1], now[cid][1]
        sev_a, sev_b = a.get("severity", "blocker"), b.get("severity", "blocker")
        if sev_a == "blocker" and sev_b != "blocker":
            out.append({"criterion": cid, "class": "weakening", "why": "a blocker made a warning"})
        elif RANK[t_now[cid]] < RANK[t_was[cid]]:
            out.append({"criterion": cid, "class": "weakening", "why": f"trust {t_was[cid]} to {t_now[cid]}"})
        elif sev_a != "blocker" and sev_b == "blocker":
            out.append({"criterion": cid, "class": "strengthening", "why": "a warning made a blocker"})
        elif RANK[t_now[cid]] > RANK[t_was[cid]]:
            out.append({"criterion": cid, "class": "strengthening", "why": f"trust {t_was[cid]} to {t_now[cid]}"})
        elif _strip(a) != _strip(b) or a.get("verifier") != b.get("verifier"):
            out.append({"criterion": cid, "class": "neutral", "why": "text, scale or verifier changed"})
    return out


def _phase_problems(s: Session, phase: int, caps: Mapping[str, Any]) -> list[str]:
    rep = check(s, caps)
    errors = [f for f in rep["findings"] if f.get("severity") == "error"]
    if phase == 1:
        return [] if s.record.get("sources") or s.record.get("path") == "chat" else ["no source was taken in"]
    if phase == 2:
        mine = [f for f in errors if f.get("where") == "criteria" and f.get("unit") is None]
        return [f"{f['code']}: {f['message']}" for f in mine] + rep["sufficiency"]
    if phase == 3:
        mine = [f for f in errors if f.get("where") in ("criteria", "outcome") and f.get("unit") is not None]
        if not s.outcome.get("intermediate"):
            return ["no intermediate outcome yet"]
        return [f"{f['code']}: {f['message']}" for f in mine]
    if phase == 4:
        return [f"{c} has no verifier class" for c in rep["unclassified"]] + [
            f"{f['code']}: {f['message']}" for f in errors if f.get("where") == "outcome"]
    if phase in (5, 6):
        if not s.blueprint.get("units"):
            return ["the blueprint has no unit yet"]
        return [f"{f['code']}: {f['message']}" for f in errors if f.get("where") == "blueprint"]
    return [f"{f['code']}: {f['message']}" for f in errors] + rep["sufficiency"] + [
        f"{c} has no verifier class" for c in rep["unclassified"]]


def approve(s: Session, phase: int, caller: Mapping[str, Any], caps: Mapping[str, Any]) -> dict[str, Any]:
    """`author approve <id> <phase>`: the person's yes on a phase's drafts (AUT §2.8)."""
    if phase not in APPROVABLE:
        raise AuthorRefused("phase-invalid", "phases 1 to 7 are approved; 8 and 9 are `scaffold` and `author verify`")
    good = {int(p["phase"]) for p in approvals(s)[0]}
    missing = [p for p in range(1, phase) if p not in good]
    if missing:
        raise AuthorRefused("phase-order", f"phase {phase} needs phases {missing} approved first")
    problems = _phase_problems(s, phase, caps)
    if problems:
        raise AuthorRefused("phase-not-ready", "; ".join(problems))
    keep = [p for p in s.record.get("phases") or [] if int(p.get("phase", 0)) < phase]
    entry = {"phase": phase, "approved_at": now_iso(), "by": dict(caller), "digest": part(s, phase)}
    s.record["phases"] = keep + [entry]
    if phase == 7:
        s.record["blueprint_digest"] = digest(s.blueprint)
        s.record["outcome_revision"] = s.outcome.get("revision")
    s.save()
    return entry


def show(s: Session, caps: Mapping[str, Any]) -> dict[str, Any]:
    """AUT §2.1 `author show`: everything a new conversation needs to resume (AUT-AC-5)."""
    good, cleared = approvals(s)
    nxt = next_phase(s)
    rep = check(s, caps)
    return {"schema_version": 1, "id": s.id, "name": s.record.get("name"), "mode": s.record.get("mode"),
            "path": s.record.get("path"), "folder": str(s.folder), "next_phase": nxt, "next": PHASES[nxt],
            "approved": [p["phase"] for p in good], "cleared": cleared, "sources": s.record.get("sources"),
            "candidates": s.record.get("candidates"), "outcome": s.outcome, "blueprint": s.blueprint,
            "verification": rep["verification"], "findings": rep["findings"], "sufficiency": rep["sufficiency"],
            "decisions": s.record.get("decisions"), "assumptions": s.outcome.get("assumptions") or [],
            **({"changes": rep["changes"]} if "changes" in rep else {})}


def listing(state_root: Path) -> list[dict[str, Any]]:
    return [{"id": s.id, "name": s.record.get("name"), "mode": s.record.get("mode"), "next_phase": next_phase(s),
             "finished": _finished(s.record), "started_at": s.record.get("started_at")}
            for s in all_sessions(state_root)]


def drop(s: Session) -> None:
    root = s.folder.parent.resolve()
    if s.folder.resolve().parent != root or root.name != "authoring":
        raise AuthorRefused("drop-refused", f"{s.folder} is not a session folder")
    shutil.rmtree(s.folder)
