"""Authoring sessions (AUT-B11, AUT-B12, AUT-B23, AUT-B15, AUT-B19, AUT-B24, AUT-B25, AUT-B17; AUT-AC4, AUT-AC5, AUT-AC7 second half, AUT-B7, AUT-B9)."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from typing import Any

from tempergraph.cli.main import main
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin

from .conftest import hash_tree
from .fixtures.packages import OUTCOME, blueprint

SIGNALS = ({}, True)  # a person at a terminal (PRV-B13)


def cli(repo: Path, *argv: str) -> tuple[int, Any, str]:
    reg = Registry()
    reg.register(standin("claude"))
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), registry=reg, cwd=repo, out=out, err=err, signals=SIGNALS)
    text = out.getvalue()
    try:
        doc = json.loads(text) if text.strip() else None
    except ValueError:
        doc = text
    return code, doc, err.getvalue()


def session_files(repo: Path, sid: str) -> Path:
    return repo / ".tempergraph" / "authoring" / sid


def started(repo: Path, *extra: str) -> str:
    code, doc, err = cli(repo, "author", "start", "release-notes", "--from", "sources", *extra)
    assert code == 0, err
    return str(doc["id"])


def write_drafts(repo: Path, sid: str, outcome: dict[str, Any] | None = None,
                 bp: dict[str, Any] | None = None) -> None:
    folder = session_files(repo, sid)
    if outcome is not None:
        (folder / "outcome.json").write_text(json.dumps(outcome))
    if bp is not None:
        (folder / "blueprint.json").write_text(json.dumps(bp))


def test_start_intake_show_and_nothing_outside_the_session(repo: Path) -> None:
    """AUT-AC4: the session verbs write only their session folder, never a package folder."""
    (repo / "templates").mkdir()
    (repo / "templates" / "release-notes-template.md").write_text("# Added\n\n# Changed\n\n# Fixed\n")
    (repo / "good.md").write_text("# Added\n\n- a change\n\n# Changed\n\n# Fixed\n")
    before = hash_tree(repo)
    sid = started(repo, "templates")
    code, doc, err = cli(repo, "author", "intake", sid, "good.md", "--kind", "example_good", "--artifact", "notes")
    assert code == 0, err
    assert doc["added"][0]["kind"] == "example_good"
    code, doc, _ = cli(repo, "author", "show", sid)
    assert doc["next_phase"] == 1 and len(doc["sources"]) == 2
    assert any(c["kind"] == "existing:template" for c in doc["candidates"])
    after = hash_tree(repo)
    changed = {k for k in set(before) ^ set(after) | {k for k in before if before.get(k) != after.get(k)}}
    assert changed and all(k.startswith(".tempergraph") for k in changed), changed
    code, doc, _ = cli(repo, "author", "list")
    assert [s["id"] for s in doc["sessions"]] == [sid]


def test_one_open_session_per_name_and_paths(repo: Path, tmp_path: Path) -> None:
    sid = started(repo)
    code, doc, _ = cli(repo, "author", "start", "release-notes", "--from", "chat")
    assert code == 2 and doc["refused"] == "session-open"
    outside = tmp_path / "elsewhere.md"
    outside.write_text("# x\n")
    code, doc, _ = cli(repo, "author", "intake", sid, str(outside))
    assert code == 2 and doc["refused"] == "path-outside-workspace"
    code, doc, _ = cli(repo, "author", "intake", sid, str(outside), "--outside")
    assert code == 0
    code, doc, _ = cli(repo, "author", "drop", sid)
    assert code == 0 and not session_files(repo, sid).exists()
    assert started(repo) != sid


def test_phase_two_needs_the_sufficiency_check(repo: Path) -> None:
    """AUT-AC7 second half, AUT-B9: a vague statement keeps phase 2 open."""
    sid = started(repo)
    (repo / "t.md").write_text("# Added\n")
    assert cli(repo, "author", "intake", sid, "t.md")[0] == 0
    assert cli(repo, "author", "approve", sid, "1")[0] == 0
    o = copy.deepcopy(OUTCOME)
    o["statement"] = "good, complete release notes"
    write_drafts(repo, sid, o)
    code, doc, _ = cli(repo, "author", "approve", sid, "2")
    assert code == 2 and doc["refused"] == "phase-not-ready" and "not observable" in doc["message"]
    code, rep, _ = cli(repo, "author", "check", sid)
    assert code == 2 and [f for f in rep["findings"] if f["code"] == "criterion-vague"]
    write_drafts(repo, sid, copy.deepcopy(OUTCOME))
    code, doc, err = cli(repo, "author", "approve", sid, "2")
    assert code == 0, err
    assert doc["approved"]["by"]["host"] and doc["next_phase"] == 3


def _authored(repo: Path, tmp_path: Path) -> tuple[str, Path, dict[str, Any]]:
    """A session taken through phases 1 to 7 and scaffolded into `tmp_path/pkg`."""
    sid = started(repo)
    (repo / "notes.md").write_text("# Added\n\n- a change\n\n# Changed\n\n# Fixed\n\n# Removed\n")
    assert cli(repo, "author", "intake", sid, "notes.md", "--kind", "example_good", "--artifact", "notes")[0] == 0
    o = copy.deepcopy(OUTCOME)
    o["intermediate"]["draft"]["criteria"][0]["verifier"] = {
        "primitive": "headings_in_order", "artifact": "notes", "headings": ["Added", "Changed", "Fixed", "Removed"]}
    write_drafts(repo, sid, o, blueprint(outcome=o))
    folder = session_files(repo, sid)
    rec = json.loads((folder / "authoring.json").read_text())
    rec["issue_repository"] = "acme/release-notes"
    (folder / "authoring.json").write_text(json.dumps(rec))
    for ph in range(1, 8):
        code, doc, err = cli(repo, "author", "approve", sid, str(ph))
        assert code == 0, (ph, err, doc)
    out = tmp_path / "pkg"
    code, _, err = cli(repo, "scaffold", sid, "--out", str(out))
    assert code == 0, err
    return sid, out, o


def test_revise_marks_a_weakening_and_writes_the_revision(repo: Path, tmp_path: Path) -> None:
    """AUT-AC6 / AUT-B25: a blocker made a warning is a weakening; nothing is written before the phase 7 yes;
    `scaffold --update-docs` writes revision 2 with origin revise_session, and `author verify` passes."""
    from tempergraph.author.blueprint import outcome_digest

    _, pkg, _ = _authored(repo, tmp_path)
    code, doc, err = cli(repo, "author", "start", str(pkg), "--revise")
    assert code == 0, err
    rid = doc["id"]
    assert doc["mode"] == "revise" and doc["next_phase"] == 7  # only the stamp-time revisions entry moved
    folder = session_files(repo, rid)
    o = json.loads((folder / "outcome.json").read_text())
    o["intermediate"]["draft"]["criteria"][1]["severity"] = "warning"
    write_drafts(repo, rid, o)
    code, rep, _ = cli(repo, "author", "check", rid)
    assert {"criterion": "rn-faithful", "class": "weakening", "why": "a blocker made a warning"} in rep["changes"]
    assert "revision-not-bumped" in {f["code"] for f in rep["findings"]}
    o["revision"] = 2
    bp = json.loads((folder / "blueprint.json").read_text())
    bp["outcome_ref"] = {"revision": 2, "digest": outcome_digest(o)}
    write_drafts(repo, rid, o, bp)
    before = (pkg / "outcome.json").read_bytes()
    code, doc, _ = cli(repo, "scaffold", rid, "--out", str(pkg), "--update-docs")
    assert code == 2 and doc["refused"] == "blueprint_not_approved"
    assert (pkg / "outcome.json").read_bytes() == before
    code, doc, _ = cli(repo, "author", "show", rid)
    for ph in doc["cleared"] or [7]:
        code, d, err = cli(repo, "author", "approve", rid, str(ph))
        assert code == 0, (ph, err, d)
    code, doc, err = cli(repo, "scaffold", rid, "--out", str(pkg), "--update-docs")
    assert code == 0, err
    got = json.loads((pkg / "outcome.json").read_text())
    assert got["revision"] == 2 and got["revisions"][-1]["origin"] == "revise_session"
    code, doc, err = cli(repo, "author", "verify", str(pkg), "--json")
    assert code == 0, json.dumps([r for r in doc["rungs"] if r["state"] != "passed"])[:1500]


def test_full_path_to_scaffold_and_resume(repo: Path, tmp_path: Path) -> None:
    """AUT-AC5 / AUT-B7: after phase 4, `author show` alone says where to go on; an edit clears approvals;
    phase 7 then lets scaffold run, and the session counts as finished."""
    sid = started(repo)
    (repo / "notes.md").write_text("# Added\n\n- a change\n\n# Changed\n\n# Fixed\n\n# Removed\n")
    assert cli(repo, "author", "intake", sid, "notes.md", "--kind", "example_good", "--artifact", "notes")[0] == 0
    o = copy.deepcopy(OUTCOME)
    o["intermediate"]["draft"]["criteria"][0]["verifier"] = {
        "primitive": "headings_in_order", "artifact": "notes", "headings": ["Added", "Changed", "Fixed", "Removed"]}
    write_drafts(repo, sid, o)
    for ph in (1, 2, 3, 4):
        code, doc, err = cli(repo, "author", "approve", sid, str(ph))
        assert code == 0, (ph, err)
    code, doc, _ = cli(repo, "author", "show", sid)
    assert doc["next_phase"] == 5 and doc["approved"] == [1, 2, 3, 4] and doc["next"] == "steps' work"
    rows = {r["id"]: r["trust"] for r in doc["verification"]["rows"]}
    assert rows["rn-sections"] == "deterministic" and rows["rn-faithful"] == "uncalibrated"
    o2 = copy.deepcopy(o)
    o2["intermediate"]["draft"]["statement"] = "A draft with the four headings"
    write_drafts(repo, sid, o2)
    code, doc, _ = cli(repo, "author", "show", sid)
    assert doc["next_phase"] == 3 and doc["cleared"] == [3, 4]
    write_drafts(repo, sid, o)
    folder = session_files(repo, sid)
    rec = json.loads((folder / "authoring.json").read_text())
    rec["issue_repository"] = "acme/release-notes"
    (folder / "authoring.json").write_text(json.dumps(rec))
    write_drafts(repo, sid, bp=blueprint(outcome=o))
    for ph in (5, 6, 7):
        code, doc, err = cli(repo, "author", "approve", sid, str(ph))
        assert code == 0, (ph, err, doc)
    out = tmp_path / "pkg"
    code, doc, err = cli(repo, "scaffold", sid, "--out", str(out))
    assert code == 0, err
    assert (out / "evals/checks/draft/must-pass/notes.md").is_file()
    code, doc, _ = cli(repo, "author", "list")
    assert doc["sessions"][0]["finished"] is True
    assert started(repo)  # the name is free again
