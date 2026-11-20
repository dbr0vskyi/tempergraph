"""Scaffold, `--update`, the check helpers and the generated tests (SCF §2.4; plan T8.6)."""

from __future__ import annotations

import copy
import io
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tempergraph.author.blueprint import digest, outcome_digest
from tempergraph.author.scaffold import ScaffoldRefused, read_session, scaffold
from tempergraph.cli.main import main
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin
from tempergraph.package import selftest
from tempergraph.package.loader import load_package

from .fixtures.packages import OUTCOME, blueprint, write

GOOD_NOTES = "# Added\n\n- a change\n\n# Changed\n\n# Fixed\n\n# Removed\n"


def outcome() -> dict[str, Any]:
    o = copy.deepcopy(OUTCOME)
    o["intermediate"]["draft"]["criteria"][0]["verifier"] = {
        "primitive": "headings_in_order", "artifact": "notes", "headings": ["Added", "Changed", "Fixed", "Removed"]}
    return o


def session(root: Path, *, approved: bool = True, o: dict[str, Any] | None = None,
            bp: dict[str, Any] | None = None) -> Path:
    o = o or outcome()
    bp = bp or blueprint(outcome=o)
    folder = root / "session"
    write(folder, "blueprint.json", bp)
    write(folder, "outcome.json", o)
    write(folder, "authoring.json", {
        "schema_version": 1, "id": "a1", "name": bp["name"], "path": "sources", "mode": "new",
        "phases": [{"phase": 7, "approved_at": "2026-11-20T10:00:00Z"}] if approved else [],
        "blueprint_digest": digest(bp), "outcome_revision": o["revision"], "issue_repository": "acme/release-notes",
        "author": "Example Owner",
        "sources": [{"id": "s1", "kind": "example_good", "locator": "saved:notes.md", "artifact": "notes",
                     "digest": "0" * 64}],
        "decisions": [{"id": "d1", "phase": 4, "subject": "One judge", "choice": "One judge reads the notes",
                       "alternatives": ["two judges"], "consequence": "cheaper"}]})
    write(folder, "sources/notes.md", GOOD_NOTES)
    write(folder, "cases.json", {"schema_version": 1, "cases": [{"id": "case-1", "request": "v1.2"}]})
    return folder


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    scaffold(read_session(session(tmp_path)), tmp_path / "out" / "release-notes")
    return tmp_path / "out" / "release-notes"


def test_minimal_workflow_scaffolds_and_its_generated_tests_pass(pkg: Path, tmp_path: Path) -> None:
    """SCF-B3 / SCF-AC-2: the package of PKG §2.7 is written and its own generated tests pass."""
    for rel in (".claude-plugin/plugin.json", "tempergraph.json", "outcome.json", "blueprint.json", "authoring.json",
                "workflow/pyproject.toml", "workflow/release_notes/__init__.py", "workflow/release_notes/checks.py",
                "prompts/draft.md", "judges/draft.md", "evals/cases.json", "evals/checks/draft/must-pass/notes.md",
                "evals/checks/draft/must-fail/notes.md", "docs/specs/00-overview.spec.md",
                "docs/specs/01-draft.spec.md", "docs/adr/0001-one-judge.adr.md", "diagram/model.json",
                "tests/test_release_notes_generated.py"):
        assert (pkg / rel).is_file(), rel
    assert json.loads((pkg / "outcome.json").read_text())["revisions"][0]["origin"] == "authored"
    lp = load_package(pkg)
    assert lp.spec.units["draft"].gate.check is not None
    for name in selftest.NAMES:
        work = tmp_path / f"t-{name}"
        work.mkdir()
        assert selftest.run(name, pkg, work) == [], name


def test_generated_test_file_runs_under_pytest(pkg: Path) -> None:
    got = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(pkg / "tests")],
                         capture_output=True, text=True, cwd=pkg, timeout=300, check=False)
    assert got.returncode == 0, got.stdout[-2000:] + got.stderr[-2000:]
    assert "7 passed" in got.stdout


def test_check_helpers_name_their_criterion(pkg: Path, tmp_path: Path) -> None:
    from tempergraph.api import checks
    from tempergraph.run.checks import CheckContext

    (tmp_path / "notes.md").write_text("# Added\n# Fixed\n")
    ctx = CheckContext(unit="draft", workdir=tmp_path, request={}, artifacts={"draft": {"notes": "notes.md"}},
                       values={"review": {"verdict": "ok"}})
    f = checks.headings_in_order(ctx, "notes", ["Added", "Changed"], "c1")
    assert f.status == "fail" and f.criterion == "c1" and "changed" in f.message
    assert checks.file_present(ctx, "notes", "c2").status == "pass"
    assert checks.pattern_absent(ctx, "notes", r"TODO", "c3").status == "pass"
    assert checks.pattern_present(ctx, "notes", r"^# Fixed", "c4").status == "pass"
    assert checks.value_in_choices(ctx, "verdict", ["ok", "redo"], "c5").status == "pass"
    assert checks.result([f]).result == "FAIL"


def test_refusals(tmp_path: Path, pkg: Path) -> None:
    with pytest.raises(ScaffoldRefused) as info:
        read_session(session(tmp_path / "x", approved=False))
    assert info.value.code == "blueprint_not_approved"
    s = session(tmp_path / "y")
    o = json.loads((s / "outcome.json").read_text())
    o["statement"] = "Changed after approval."
    write(s, "outcome.json", {**o, "revision": 2})
    with pytest.raises(ScaffoldRefused) as info:
        read_session(s)
    assert info.value.code == "blueprint_not_approved"
    with pytest.raises(ScaffoldRefused) as info:
        scaffold(read_session(session(tmp_path / "z")), pkg)
    assert info.value.code == "out-not-empty"
    reg = Registry()
    reg.register(standin("claude"))
    err = io.StringIO()
    code = main(["scaffold", str(tmp_path / "z" / "session"), "--out", str(pkg)], registry=reg, cwd=tmp_path,
                out=io.StringIO(), err=err)
    assert code == 2 and "out-not-empty" in err.getvalue()


def test_update_keeps_person_edits(pkg: Path, tmp_path: Path) -> None:
    """SCF-B7: a rewritten prompt is not touched and is listed; data-generated docs sections and the
    diagram are regenerated."""
    (pkg / "prompts" / "draft.md").write_text("My own prompt for {request}; write notes.\n")
    spec_file = pkg / "docs" / "specs" / "01-draft.spec.md"
    spec_file.write_text(spec_file.read_text().replace("Part of the", "My prose.\n\nPart of the"))
    s = session(tmp_path / "again")
    o = json.loads((s / "outcome.json").read_text())
    o["intermediate"]["draft"]["criteria"][1]["text"] = "Every entry matches its merged change exactly"
    o["revision"] = 2
    write(s, "outcome.json", o)
    rec = json.loads((s / "authoring.json").read_text())
    rec["outcome_revision"] = 2
    bp = json.loads((s / "blueprint.json").read_text())
    bp["outcome_ref"] = {"revision": 2, "digest": outcome_digest(o)}
    write(s, "blueprint.json", bp)
    rec["blueprint_digest"] = digest(bp)
    write(s, "authoring.json", rec)
    rep = scaffold(read_session(s), pkg, update=True)
    assert "prompts/draft.md" in rep.person_edited
    assert (pkg / "prompts" / "draft.md").read_text().startswith("My own prompt")
    text = spec_file.read_text()
    assert "My prose." in text and "rn-faithful Every entry matches its merged change exactly" in text
    assert "outcome.json" in rep.written and "diagram/model.json" in rep.written


def test_update_never_changes_an_edited_file(pkg: Path, tmp_path: Path) -> None:
    """SCF-AC-4 as a property test over random edits (docs specs keep their prose; only their acceptance
    section is data)."""
    rng = random.Random(20261120)
    candidates = sorted(p.relative_to(pkg).as_posix() for p in pkg.rglob("*") if p.is_file()
                        and not p.relative_to(pkg).as_posix().startswith(("docs/specs/", "diagram/", "outcome.json",
                                                                          "authoring.json", "blueprint.json")))
    for round_ in range(5):
        edited = rng.sample(candidates, 3)
        before = {}
        for rel in edited:
            p = pkg / rel
            p.write_bytes(p.read_bytes() + f"\n# edit {round_}\n".encode())
            before[rel] = p.read_bytes()
        rep = scaffold(read_session(session(tmp_path / f"s{round_}")), pkg, update=True)
        for rel in edited:
            assert (pkg / rel).read_bytes() == before[rel], rel
            assert rel in rep.person_edited, rel


def test_update_docs_only(pkg: Path, tmp_path: Path) -> None:
    (pkg / "evals" / "cases.json").unlink()
    rep = scaffold(read_session(session(tmp_path / "d")), pkg, update=True, docs_only=True)
    assert not (pkg / "evals" / "cases.json").exists()
    assert all(r.startswith("docs/") or r == "outcome.json" for r in rep.written)


def test_custom_check_is_left_to_write(tmp_path: Path) -> None:
    o = outcome()
    o["intermediate"]["draft"]["criteria"][0]["verifier"] = {"check": "draft_check"}
    out = tmp_path / "out"
    rep = scaffold(read_session(session(tmp_path, o=o, bp=blueprint(outcome=o))), out)
    assert rep.to_write == ["rn-sections"]
    work = tmp_path / "w"
    work.mkdir()
    problems = selftest.run("check_fixtures", out, work)
    assert problems and "expected PASS, got MAYBE" in problems[0]


def test_selftest_reports_drift(pkg: Path, tmp_path: Path) -> None:
    decl = pkg / "workflow/release_notes/__init__.py"
    decl.write_text(decl.read_text().replace("summary='Write the release notes'", "summary=''"))
    assert selftest.run("summaries", pkg, tmp_path)
    (pkg / "diagram" / "model.json").write_text(json.dumps({"digest": "stale"}))
    assert "regenerate" in selftest.run("diagram_current", pkg, tmp_path)[0]
    (pkg / "docs" / "specs" / "01-draft.spec.md").unlink()
    assert selftest.run("docs", pkg, tmp_path)


def _verify(pkg: Path, tmp_path: Path, *extra: str) -> tuple[int, dict[str, Any], Registry]:
    reg = Registry()
    reg.register(standin("claude"))
    out = io.StringIO()
    code = main(["author", "verify", str(pkg), "--json", *extra], registry=reg, cwd=tmp_path, out=out,
                err=io.StringIO())
    return code, json.loads(out.getvalue()), reg


def _states(doc: dict[str, Any]) -> dict[str, str]:
    return {r["name"]: r["state"] for r in doc["rungs"]}


def test_author_verify_passes_the_minimal_workflow(pkg: Path, tmp_path: Path) -> None:
    """SCF-B3 / SCF-AC-2: rungs 1 to 7 pass with no edit; rung 10 stamps; 8 and 9 were not asked."""
    from tempergraph.package import registry as reg_mod

    code, doc, reg = _verify(pkg, tmp_path)
    assert code == 0, json.dumps([r for r in doc["rungs"] if r["state"] != "passed"], indent=1)
    states = _states(doc)
    assert [states[n] for n in ("load", "compare", "literals", "generated_tests", "coverage", "audit",
                                "register", "stamp")] == ["passed"] * 8
    assert states["judge_seeds"] == states["trial"] == "skipped"
    assert (pkg / "stamp.json").is_file()
    assert any(e["name"] == "release-notes" for e in reg_mod.read_entries())
    rec = json.loads((pkg / "authoring.json").read_text())
    assert rec["verify"]["ok"] is True and rec["verify"]["rungs"]["stamp"] == "passed"
    assert reg.get("claude").calls == []  # type: ignore[attr-defined]  # SCF-AC-5: no executor session


def test_author_verify_stops_at_the_comparison(pkg: Path, tmp_path: Path) -> None:
    """SCF-B4: a person added approval to draft; rung 2 names it and the ladder stops."""
    decl = pkg / "workflow/release_notes/__init__.py"
    text = decl.read_text()
    assert "gate=Gate(check=draft_check," in text
    decl.write_text(text.replace("gate=Gate(check=draft_check,", "gate=Gate(check=draft_check, approval=True,", 1))
    code, doc, _ = _verify(pkg, tmp_path)
    assert code == 2
    states = _states(doc)
    assert states["load"] == "passed" and states["compare"] == "failed" and states["stamp"] == "skipped"
    msgs = [f["message"] for r in doc["rungs"] for f in r["findings"]]
    assert any("draft now pauses for approval after a pass; the blueprint does not" in m for m in msgs)


def test_author_verify_refuses_seeds_and_trial(pkg: Path, tmp_path: Path) -> None:
    """SCF §2.7: rungs 8 and 9 are not_in_release; rungs 1 to 7 still run, nothing is stamped, no session."""
    code, doc, reg = _verify(pkg, tmp_path, "--judge-seeds")
    assert code == 2
    states = _states(doc)
    assert states["register"] == "passed" and states["judge_seeds"] == "refused" and states["stamp"] == "skipped"
    assert "not_in_release" in doc["rungs"][7]["note"]
    assert reg.get("claude").calls == []  # type: ignore[attr-defined]
    code, doc, _ = _verify(pkg, tmp_path, "--trial")
    assert code == 2 and doc["refused"] == "trial-needs-case"


def test_verify_coverage_rung_and_decisions(pkg: Path) -> None:
    """Rung 5: without check fixtures nothing is trusted, so the final criteria are uncovered; a recorded
    decision on a criterion clears it (SCF §2.5, AUT §2.5)."""
    import shutil

    from tempergraph.author.verify import Rung, _coverage

    shutil.rmtree(pkg / "evals" / "checks")
    spec = load_package(pkg).spec
    assert spec.outcome is not None
    rung = Rung(n=5, name="coverage")
    _coverage(spec, set(), rung)
    ids = {c.id for c in spec.outcome.final}
    assert {f["code"] for f in rung.findings} == {"outcome-uncovered"} and len(rung.findings) == len(ids)
    rung = Rung(n=5, name="coverage")
    _coverage(spec, {str(i) for i in ids}, rung)
    assert rung.findings == []
