"""A spec's `Depends on` and `Does not own` (the spec rule): a behaviour or criterion added or changed that links
another spec has it under `Depends on` (ts-dis-form, ts-spec-form, ts-set-form), each row names an existing spec,
a listed spec nothing links is a lead (ts-dis-depends), and the capability list prints who uses a spec (CAPL)."""

from __future__ import annotations

import importlib
import subprocess
import time
from pathlib import Path
from typing import Any

from tempergraph.package.loader import load_package
from tempergraph.run.checks import CheckContext, GitFacts, run_check

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_package(ROOT).spec
routing = importlib.import_module("tgwf_temperspec.routing")
specfmt = importlib.import_module("tgwf_temperspec.specfmt")
FIXTURE = ROOT / "evals" / "checks" / "discovery" / "must-pass" / "2-new-spec"
SPEC_FILE = "docs/specs/config-file.spec.md"
OTHER = ("# Settings store\n\n## Purpose\n\nWhere settings live.\n\n## Behaviours\n\n### STO-B1 Settings are kept\n\n"
         "WHEN a setting is written THE store SHALL keep it.\n\n- GIVEN a setting WHEN it is written THEN it is kept\n\n"
         "## Acceptance criteria\n\n- STO-AC1 (STO-B1): A written setting is kept\n")
LINKED = "names the missing file, as the settings store does for each file it reads (STO-B1)."


def _work(tmp_path: Path, *, link: bool = True, depends: str = "", not_owned: str = "") -> Path:
    work = tmp_path / "w"
    for f in sorted(p for p in FIXTURE.rglob("*") if p.is_file()):
        target = work / f.relative_to(FIXTURE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
    (work / "docs" / "specs" / "settings-store.spec.md").write_text(OTHER)
    spec = work / SPEC_FILE
    text = spec.read_text()
    if link:
        text = text.replace("names the missing file.", LINKED)
    extra = (f"## Depends on\n\n{depends}\n\n" if depends else "") + (
        f"## Does not own\n\n{not_owned}\n\n" if not_owned else "")
    spec.write_text(text.replace("## Behaviours", extra + "## Behaviours"))
    return work


def _check(unit: str, work: Path, git: GitFacts | None = None) -> Any:
    artifacts = {"discovery": {"handoff": "handoff.md"}}
    ctx = CheckContext(unit=unit, workdir=work, request={}, artifacts=artifacts, git=git or GitFacts(),
                       allow=SPEC.allow_commands, out_dir=work.parent / f"{work.name}.out",
                       deadline_at=time.monotonic() + 60)
    return run_check(SPEC.units[unit].gate, ctx)[0]


def _named(res: Any, criterion: str) -> list[str]:
    return [f.status for f in res.findings if f.criterion == criterion]


def _messages(res: Any, criterion: str) -> str:
    return " ".join(f.message for f in res.findings if f.criterion == criterion)


def test_a_behaviour_that_links_a_spec_not_listed_fails(tmp_path: Path) -> None:  # ts-dis-form
    res = _check("discovery", _work(tmp_path))
    assert res.result == "FAIL" and _named(res, "ts-dis-form") == ["fail"], res.evidence
    assert "CFG-B1 links `docs/specs/settings-store.spec.md`" in _messages(res, "ts-dis-form")


def test_a_path_link_counts_like_an_id_link(tmp_path: Path) -> None:  # ts-dis-form
    work = _work(tmp_path, link=False)
    spec = work / SPEC_FILE
    spec.write_text(spec.read_text().replace("names the missing file.",
                                             "names the missing file, as [the store](settings-store.spec.md) says."))
    assert _named(_check("discovery", work), "ts-dis-form") == ["fail"]


def test_a_listed_dependency_passes(tmp_path: Path) -> None:  # ts-dis-form, ts-dis-depends
    work = _work(tmp_path, depends="- `settings-store.spec.md`: how a read file is named\n- Outside: the file system")
    res = _check("discovery", work)
    assert res.result == "PASS", res.evidence
    assert _named(res, "ts-dis-form") == ["pass"] and _named(res, "ts-dis-depends") == ["pass"]


def test_a_row_that_names_no_existing_spec_fails(tmp_path: Path) -> None:  # ts-dis-form
    work = _work(tmp_path, depends="- `settings-store.spec.md`: names\n- `gone.spec.md`: nothing\n- the clock")
    res = _check("discovery", work)
    assert _named(res, "ts-dis-form") == ["fail", "fail"], res.evidence


def test_a_listed_spec_nothing_links_is_a_lead(tmp_path: Path) -> None:  # ts-dis-depends
    res = _check("discovery", _work(tmp_path, link=False, depends="- `settings-store.spec.md`: nothing yet"))
    assert res.result == "MAYBE" and _named(res, "ts-dis-depends") == ["maybe"], res.evidence
    assert _named(res, "ts-dis-form") == ["pass"]


def test_a_does_not_own_row_names_another_existing_spec(tmp_path: Path) -> None:  # ts-dis-form
    good = _work(tmp_path / "a", link=False, not_owned="- Where settings are kept: `settings-store.spec.md`")
    assert _named(_check("discovery", good), "ts-dis-form") == ["pass"]
    for n, row in enumerate(("- Reading the file twice", "- Exit codes: `config-file.spec.md`")):
        bad = _work(tmp_path / f"b{n}", link=False, not_owned=row)
        res = _check("discovery", bad)
        assert _named(res, "ts-dis-form") == ["fail"] and "Does not own" in _messages(res, "ts-dis-form"), row


def _git(repo: Path, *args: str) -> str:
    cmd = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def test_an_old_spec_is_held_only_on_the_behaviours_a_run_changes(tmp_path: Path) -> None:  # ts-spec-form
    work = _work(tmp_path)  # CFG-B1 links the store, with no `Depends on`, already at the base
    _git(work, "init", "-q")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "base")
    base = _git(work, "rev-parse", "HEAD")
    spec = work / SPEC_FILE
    spec.write_text(spec.read_text().replace("SHALL exit with code 2.", "SHALL exit with code 3."))
    _git(work, "commit", "-qam", "change CFG-B2")
    git = GitFacts(base=base, changed_paths=(SPEC_FILE,))
    assert _named(_check("discovery", work, git), "ts-dis-form") == ["pass"]
    spec.write_text(spec.read_text().replace("SHALL exit with code 3.", "SHALL exit with code 3, as STO-B1 says."))
    _git(work, "commit", "-qam", "link from CFG-B2")
    res = _check("discovery", work, git)
    assert _named(res, "ts-dis-form") == ["fail"] and "CFG-B2 links" in _messages(res, "ts-dis-form"), res.evidence


def test_a_spec_has_no_used_by_responsibilities_or_out_of_scope_section() -> None:  # ts-spec-form
    text = (FIXTURE / SPEC_FILE).read_text()
    for heading in ("Used by", "Responsibilities", "Out of scope"):
        spec = specfmt.parse_spec(text.replace("## Behaviours", f"## {heading}\n\n- a\n\n## Behaviours"))
        assert any(f"`## {heading}`" in m for _, m, _ in spec.problems), heading
    late = specfmt.parse_spec(text + "\n## Depends on\n\n- Outside: the clock\n")
    assert any("out of order" in m for _, m, _ in late.problems)
    assert specfmt.parse_spec(text.replace("## Behaviours", "## Depends on\n\n- Outside: x\n\n## Behaviours")).problems == []


def test_the_capability_list_prints_who_uses_a_spec(tmp_path: Path) -> None:  # CAPL-AC4
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)
    (specs / "settings-store.spec.md").write_text(OTHER)
    user = (FIXTURE / SPEC_FILE).read_text().replace(
        "## Behaviours", "## Depends on\n\n- `settings-store.spec.md`: names\n\n## Behaviours")
    (specs / "config-file.spec.md").write_text(user)
    routing.write_inventory(tmp_path)
    text = (tmp_path / routing.CAPABILITIES).read_text()
    store = text[text.index("`docs/specs/settings-store.spec.md`"):]
    assert "Used by: `docs/specs/config-file.spec.md`" in store
    assert "Used by" not in text[text.index("`docs/specs/config-file.spec.md`"):text.index("settings-store.spec.md`:")]


def test_the_rule_and_the_prompts_say_it() -> None:  # ts-dis-depends
    rule = (ROOT / "rules" / "spec.rule.md").read_text()
    assert "## Depends on" in rule and "## Does not own" in rule and "no `Used by`" in rule
    assert "who depends on it" not in rule
    for unit in ("discovery", "setup"):
        assert "`## Depends on`" in (ROOT / "prompts" / f"{unit}.md").read_text(), unit
    assert "ts-dis-depends" in (ROOT / "judges" / "discovery.md").read_text()
