"""How model-facing text is built (PRA-B12, PRA-B13; GitHub issue #227): measures in `audit prompts` and the two
advisory definition rules, each with a fixture that raises it and a clean one that does not."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from tempergraph.audit import audit
from tempergraph.audit import catalog as cat
from tempergraph.audit.text_health import measure, sentences
from tempergraph.cli.main import main
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin
from tempergraph.package.loader import load_package

from .fixtures.packages import minimal_package, write
from .test_audit import ctx

HEAVY = "Write release notes for {request} into notes.md.\n\n" + "\n".join(
    f"- Never touch file {i}." for i in range(22)) + "\n"
SHARED = "Every claim in the notes cites the commit that makes it true, with its short hash."


def _rules(root: Path, tmp: Path) -> list[Any]:
    lp = load_package(root)
    return audit(lp.spec, {"definition"}, ctx(tmp), manifest=lp.manifests.engine).findings


def _rows(root: Path, tmp: Path) -> dict[str, Any]:
    out = io.StringIO()
    reg = Registry()
    reg.register(standin("claude"))
    assert main(["audit", "prompts", str(root), "--layer", "definition"], registry=reg, cwd=tmp, out=out,
                err=io.StringIO()) == 0
    return {r["file"]: r for r in json.loads(out.getvalue())["files"]}


def test_pra_ac7_measures_count_prohibitions_reasons_and_goal_branches() -> None:  # PRA-AC7 (PRA-B12)
    m = measure("Never edit tests, because a weakened test hides the defect.\n\nIf the plan has phases, run each.\n")
    assert (m.prohibitions, m.reasons) == (1, 1)
    assert 0 < m.goal_branch_share < 1
    assert measure("").goal_branch_share == 0.0
    assert sentences("Short one. " + SHARED) == {SHARED.lower()}


def test_pra_ac7_the_prompts_matrix_holds_sizes_structure_and_step_files(tmp_path: Path) -> None:  # PRA-AC7 (PRA-B12)
    root = minimal_package(tmp_path)
    manifest = json.loads((root / "tempergraph.json").read_text())
    write(root, "tempergraph.json", manifest | {"step_files": ["rules/*.md"]})
    write(root, "rules/notes.rule.md", "# Notes\n\nA heading per change kind.\n")
    write(root, "prompts/draft.md", "Write release notes for {request} into notes.md, following `rules/notes.rule.md`.\n")
    rows = _rows(root, tmp_path)
    draft = rows["prompts/draft.md"]
    assert draft["size"]["rendered"] > draft["size"]["chars"]  # the engine's blocks are appended
    assert draft["size"]["must_read_files"] == ["rules/notes.rule.md"]
    assert draft["size"]["must_read"] >= draft["size"]["rendered"] + len("# Notes\n\nA heading per change kind.\n")
    assert set(draft["structure"]) >= {"prohibitions", "reasons", "prohibitions_per_reason", "goal_branch_share",
                                       "repeated_sentences"}
    assert rows["rules/notes.rule.md"]["role"] == "step_file"
    assert rows["rules/notes.rule.md"]["used_by"] == ["draft:step_file"]


def test_pra_ac8_constraint_heavy_text_is_flagged_and_clean_text_is_not(tmp_path: Path) -> None:  # PRA-AC8 (PRA-B13)
    clean = minimal_package(tmp_path / "clean")
    assert not [f for f in _rules(clean, tmp_path) if f.rule.startswith("prompt-")]
    heavy = minimal_package(tmp_path / "heavy")
    write(heavy, "prompts/draft.md", HEAVY)
    found = [f for f in _rules(heavy, tmp_path) if f.rule == "prompt-constraint-heavy"]
    assert len(found) == 1 and found[0].unit == "draft" and found[0].severity == "warning"
    assert found[0].evidence["prohibitions"] == 22


def test_pra_ac8_a_sentence_in_three_files_is_repeated_text(tmp_path: Path) -> None:  # PRA-AC8 (PRA-B13)
    root = minimal_package(tmp_path)
    write(root, "prompts/draft.md", f"Write release notes for {{request}} into notes.md. {SHARED}\n")
    write(root, "judges/draft.md", f"# Stance\n\nVerify the notes. {SHARED}\n\n# Brief\n\nRead notes.md.\n")
    assert not [f for f in _rules(root, tmp_path) if f.rule == "prompt-repeated-text"]  # two files: under 3
    write(root, "skills/style/SKILL.md", f"---\nname: style\ndescription: d\n---\n{SHARED}\n")
    found = [f for f in _rules(root, tmp_path) if f.rule == "prompt-repeated-text"]
    assert len(found) == 1 and len(found[0].evidence["files"]) == 3


def test_pra_ac8_thresholds_are_parameters_without_data() -> None:  # PRA-AC8 (PRA-B13)
    for name in ("prompt_prohibitions_per_reason", "prompt_repeat_files"):
        assert cat.PARAMS[name].source.startswith("default_no_data")
    assert all(cat.rule(r).severity == "warning" for r in ("prompt-constraint-heavy", "prompt-repeated-text"))
