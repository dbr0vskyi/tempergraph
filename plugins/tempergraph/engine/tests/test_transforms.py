"""The engine-shipped transforms, each on a before and after fixture and applied twice (VER §2.3.4, VER-AC-3)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from tempergraph.package import transforms as tf

from .conftest import hash_tree

BEFORE = '''
from tempergraph.api import Gate, Judge, Step, Workflow, text
from tempergraph import api


def workflow():
    return Workflow(
        order=["draft", "review"],
        model_profile={"draft": ["small", "large"]},
        units={
            "draft": Step(prompt=text("prompts/draft.md"), tools=["read", "write"],  # keeps this comment
                          model=["small", "medium"],
                          gate=Gate(on_budget_spent="ask", check_timeout_s=1800,
                                    judge=Judge(stance="Verify {notes}."))),
            "review": api.Step(
                prompt="Review {notes} with Read",
                tools=["read"],
                model=["small", "medium", "large"],
                gate=Gate(judge=Judge(stance="Verify."), on_budget_spent="stop"),
            ),
        },
    )
'''


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    root = tmp_path / "pkg"
    (root / "workflow").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "docs").mkdir()
    (root / "workflow" / "__init__.py").write_bytes(BEFORE.lstrip().encode())
    (root / "prompts" / "draft.md").write_text("Write {notes} for {request}.\nUse Read, then ReadMany and `Read`.\n")
    (root / "docs" / "note.md").write_text("The key {notes} and the tool Read are described here.\n")
    return root


def code(root: Path) -> str:
    return (root / "workflow" / "__init__.py").read_text()


def twice(root: Path, migrate: dict[str, Any]) -> tf.Result:
    """Apply, then apply again: the second run changes nothing (idempotent)."""
    first = tf.apply(root, migrate)
    after = hash_tree(root)
    again = tf.apply(root, migrate)
    assert hash_tree(root) == after and again.changed == []
    compile(code(root), "workflow", "exec")
    return first


def test_rename_field(pkg: Path) -> None:
    got = twice(pkg, {"transform": "rename_field", "params": {"from": "units.*.gate.on_budget_spent",
                                                               "to": "units.*.gate.when_budget_spent"}})
    assert got.changed == ["workflow/__init__.py"]
    text = code(pkg)
    assert 'Gate(when_budget_spent="ask", check_timeout_s=1800' in text
    assert 'when_budget_spent="stop"' in text and "on_budget_spent" not in text
    assert "# keeps this comment" in text


def test_rename_field_refuses_what_it_cannot_express(pkg: Path) -> None:
    with pytest.raises(tf.TransformError, match="different builders"):
        tf.apply(pkg, {"transform": "rename_field", "params": {"from": "units.*.gate.on_budget_spent",
                                                                "to": "units.*.on_budget_spent"}})
    with pytest.raises(tf.TransformError, match="declares both"):
        tf.apply(pkg, {"transform": "rename_field", "params": {"from": "units.*.gate.on_budget_spent",
                                                                "to": "units.*.gate.check_timeout_s"}})
    with pytest.raises(tf.TransformError, match="not a transform"):
        tf.apply(pkg, {"transform": "rewrite_everything"})
    with pytest.raises(tf.TransformError, match="no parameter"):
        tf.apply(pkg, {"transform": "rename_field", "params": {"path": "x"}})


def test_set_field(pkg: Path) -> None:
    twice(pkg, {"transform": "set_field", "params": {"path": "units.*.gate.judge.effort", "value": "medium"}})
    text = code(pkg)
    assert 'Judge(stance="Verify {notes}.", effort="medium")' in text
    assert 'Judge(stance="Verify.", effort="medium")' in text
    twice(pkg, {"transform": "set_field", "params": {"path": "units.*.timeout_s", "value": 900}})
    text = code(pkg)
    assert "timeout_s=900)," in text  # the call that ends on its last argument
    assert 'on_budget_spent="stop"), timeout_s=900,\n' in text  # the call with a trailing comma keeps one
    twice(pkg, {"transform": "set_field", "params": {"path": "units.*.gate.on_budget_spent", "value": "ask"}})
    assert code(pkg) == text  # declared everywhere already: an explicit value is never overwritten


def test_drop_field(pkg: Path) -> None:
    twice(pkg, {"transform": "drop_field", "params": {"path": "units.*.gate.check_timeout_s", "default": 1800}})
    assert "check_timeout_s" not in code(pkg) and 'Gate(on_budget_spent="ask",\n' in code(pkg)
    twice(pkg, {"transform": "drop_field", "params": {"path": "units.*.gate.on_budget_spent", "default": "ask"}})
    text = code(pkg)
    assert 'on_budget_spent="stop"' in text and '"ask"' not in text  # another value stays for a person
    twice(pkg, {"transform": "drop_field", "params": {"path": "units.*.tools"}})
    assert "tools=" not in code(pkg) and 'prompt="Review {notes} with Read",\n                model=' in code(pkg)


def test_rename_symbol(pkg: Path) -> None:
    twice(pkg, {"transform": "rename_symbol", "params": {"from": "Step", "to": "ModelStep"}})
    text = code(pkg)
    assert "from tempergraph.api import Gate, Judge, ModelStep, Workflow, text" in text
    assert '"draft": ModelStep(prompt=' in text and '"review": api.ModelStep(' in text
    assert "Step(" not in text.replace("ModelStep(", "")


def test_rename_template_key(pkg: Path) -> None:
    got = twice(pkg, {"transform": "rename_template_key", "params": {"from": "notes", "to": "release_notes"}})
    assert got.changed == ["prompts/draft.md", "workflow/__init__.py"]
    assert (pkg / "prompts" / "draft.md").read_text().startswith("Write {release_notes} for {request}.")
    text = code(pkg)
    assert 'stance="Verify {release_notes}."' in text and 'prompt="Review {release_notes} with Read"' in text
    assert "{notes}" in (pkg / "docs" / "note.md").read_text()  # the package's documents are not model-facing


def test_rename_tool(pkg: Path) -> None:
    (pkg / "workflow" / "__init__.py").write_text(code(pkg).replace('tools=["read"],', 'tools=["Read"],'))
    twice(pkg, {"transform": "rename_tool", "params": {"executor": "claude", "from": "Read", "to": "View"}})
    assert (pkg / "prompts" / "draft.md").read_text() == "Write {notes} for {request}.\nUse View, then ReadMany and `View`.\n"
    text = code(pkg)
    assert 'tools=["View"],' in text
    assert 'prompt="Review {notes} with Read"' in text  # inside a longer string the name does not stand alone


def test_map_capability(pkg: Path) -> None:
    twice(pkg, {"transform": "map_capability", "params": {"from": "read", "to": "view"}})
    text = code(pkg)
    assert 'tools=["view", "write"]' in text and 'tools=["view"],' in text and 'text("prompts/draft.md")' in text
    twice(pkg, {"transform": "map_capability", "params": {"from": "small", "to": "tiny"}})
    assert 'model=["tiny", "medium"]' in code(pkg) and '"draft"' in code(pkg)


def test_model_list_to_escalation(pkg: Path) -> None:
    got = twice(pkg, {"transform": "model_list_to_escalation"})
    text = code(pkg)
    assert "from tempergraph.api import Escalation, Gate, Judge, Step, Workflow, text" in text
    assert 'model="small",' in text and 'escalation=Escalation(to="medium")),' in text  # one tier up
    assert text.count("Escalation(") == 1
    assert 'model_profile={"draft": "small"}' in text
    asked = {(o["where"].split(":")[0], tuple(o["was"])) for o in got.owner}
    assert asked == {("workflow/__init__.py", ("small", "medium", "large")),  # three rungs: the owner chooses
                     ("workflow/__init__.py", ("small", "large"))}
    assert all("escalation.to" in o["question"] for o in got.owner)


def test_line_endings_and_other_files_stay(pkg: Path) -> None:
    path = pkg / "workflow" / "__init__.py"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    other = pkg / "workflow" / "checks.py"
    other.write_text(textwrap.dedent('''
        def Gate(**kw):  # a local helper of the same name is not the engine's builder
            return kw

        G = Gate(on_budget_spent="ask")
    '''))
    before = other.read_bytes()
    twice(pkg, {"transform": "rename_field", "params": {"from": "units.*.gate.on_budget_spent",
                                                         "to": "units.*.gate.when_budget_spent"}})
    raw = path.read_bytes()
    assert b"when_budget_spent" in raw and raw.count(b"\r\n") == raw.count(b"\n")
    assert other.read_bytes() == before
