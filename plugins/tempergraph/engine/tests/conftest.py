from __future__ import annotations

import os
import re
import site
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SRC = ENGINE_ROOT / "src" / "tempergraph"
DOCS = ENGINE_ROOT.parent / "docs"
REPO_ROOT = ENGINE_ROOT.parents[2]

# The suite tests the `src` next to it, never another copy of the engine installed in the environment; child
# processes the tests start find it the same way.
_SRC_ROOT = str(ENGINE_ROOT / "src")
if sys.path[:1] != [_SRC_ROOT]:
    sys.path.insert(0, _SRC_ROOT)
os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (_SRC_ROOT, os.environ.get("PYTHONPATH", "")) if p)


def workflow_packages() -> list[Path]:
    """The workflow packages next to the engine in this repository, found by their manifest. The engine's
    tests name none of them (WFM-AC4, ADR `the-engine-names-no-workflow`)."""
    return sorted(p.parent for p in (REPO_ROOT / "plugins").glob("*/tempergraph.json"))


def workflow_names() -> list[str]:
    """Each package's workflow name and plugin name, in the hyphen and underscore spellings."""
    import json

    names: set[str] = set()
    for root in workflow_packages():
        name = str(json.loads((root / "tempergraph.json").read_text(encoding="utf-8"))["name"])
        names |= {name, name.replace("-", "_"), root.name, root.name.replace("-", "_")}
    return sorted(names)


REAL_HOME = Path.home()
"""The home folder of whoever started the suite, read once before any test moves `HOME`: only the session guard
looks at it, and only at its `.tempergraph`."""

HOME_VARS = ("HOME", "USERPROFILE")  # what `Path.home()` reads, on POSIX and on Windows
SIGN_IN_FOLDER_VAR = "CLAUDE_CONFIG_DIR"  # moves the folder that holds the `claude` sign-in file
_USER_BASE = site.getuserbase()  # a changed HOME must not hide the user's installed packages from a child process


@pytest.fixture(autouse=True)
def _isolated_home(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory,
                   monkeypatch: pytest.MonkeyPatch) -> None:
    """No test touches the real home folder or a real state root (WSP-AC2), and no test sees the caller's sign-in
    (TST-B13): the user home is a temporary folder and the credential variables are unset, so a test that needs a
    sign-in creates it. A `live` test is the exception: it runs the real, signed-in `claude`."""
    from tempergraph.schedule.credentials import CREDENTIAL_NAMES

    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("TEMPERGRAPH_HOME", str(home / ".tempergraph"))
    monkeypatch.setenv("TEMPERGRAPH_LOOP", "off")  # no detached loop child from a test run (SIL-B1)
    for var in (
        "TEMPERGRAPH_STATE_ROOT",
        "TEMPERGRAPH_CALLER",
        "TEMPERGRAPH_CALLER_APP",
        "TEMPERGRAPH_SUPERVISOR_TOKEN",
        "TEMPERGRAPH_SESSION_KEY",  # a suite run from inside an engine session is not a step driving the engine (PRV-B13)
    ):
        monkeypatch.delenv(var, raising=False)
    if "live" in request.node.keywords:
        return
    # git finds no identity in an empty home on every machine; a test's own repository config still wins over this
    (home / ".gitconfig").write_text("[user]\n\tname = Test\n\temail = test@example.invalid\n", encoding="utf-8")
    for var in HOME_VARS:
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("PYTHONUSERBASE", os.environ.get("PYTHONUSERBASE") or _USER_BASE)
    for var in (*sorted(CREDENTIAL_NAMES), SIGN_IN_FOLDER_VAR):
        monkeypatch.delenv(var, raising=False)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch git repository with one commit."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("scratch\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "init")
    return root


def hash_tree(root: Path) -> dict[str, str]:
    import hashlib

    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[str(p.relative_to(root)) + "/"] = "dir"
    return out


# --- nested runs and the guard of the real folders (TST-B4, TST-B5) --------------------------------------------

NESTED_VAR = "TEMPERGRAPH_SUITE_NESTED"
"""Set on every pytest run that a test of the suite starts: the suite-level tests return at once when it is set,
so they never nest again, and the session guard below does not run in it."""

CACHE_DIRS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"})

# A suite run by a session that an engine drives is not alone in the real home folder and the real state root:
# the driving engine writes its own run there (PRV-B13). The two folders are compared only when it is not.
_DRIVEN_BY_ENGINE = "TEMPERGRAPH_SESSION_KEY" in os.environ

SAMPLE_TEST_FILES = (
    "tests/test_store.py",
    "tests/test_transforms.py",
    "tests/test_rerun.py",
    "tests/test_migration.py",
    "tests/test_settings.py",
)
"""Five test files from different areas: the sample that the same-result and no-leak tests run on workers."""


def is_nested() -> bool:
    return os.environ.get(NESTED_VAR) == "1"


def is_xdist_worker() -> bool:
    return bool(os.environ.get("PYTEST_XDIST_WORKER"))


def nested_env() -> dict[str, str]:
    """The environment of a nested run: not a worker, and marked as nested."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST")}
    env[NESTED_VAR] = "1"
    return env


def nested_pytest(
    *args: str, scratch: bool = False, timeout: float = 900, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """`python -m pytest` in a child process with the engine folder as working directory and the project's own
    configuration. `scratch` is for a module outside the engine folder: its root conftest and these fixtures are
    then loaded as plugins, because pytest finds conftest files only above the tests it runs. They go in through
    `PYTEST_PLUGINS`, which registers after the runner's own plugin, as a conftest in the rootdir does (a `-p`
    plugin registers before it and would be asked its hooks too late)."""
    cmd = [sys.executable, "-m", "pytest", "-c", str(ENGINE_ROOT / "pyproject.toml"), "-p", "no:cacheprovider"]
    full_env = {**nested_env(), **(env or {})}
    if scratch:
        full_env["PYTEST_PLUGINS"] = "conftest,tests.conftest"
    return subprocess.run([*cmd, *args], cwd=ENGINE_ROOT, env=full_env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=timeout, check=False)


def outcome_counts(output: str) -> dict[str, int]:
    """The counts of the summary line of a run (`12 passed, 1 skipped in 3.2s`)."""
    counts: dict[str, int] = {}
    for line in reversed(output.strip().splitlines()):
        found = re.findall(r"(\d+) (passed|failed|skipped|error|errors|xfailed|xpassed|deselected)", line)
        if found and " in " in line:
            for n, word in found:
                counts[word.rstrip("s") if word == "errors" else word] = int(n)
            break
    return counts


def repo_files_snapshot() -> dict[str, str]:
    """A hash of every file of the repository that git tracks or would add, outside cache folders."""
    import hashlib

    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO_ROOT,
                            capture_output=True, check=False).stdout.decode("utf-8", "replace")
    out: dict[str, str] = {}
    for rel in sorted(p for p in listed.split("\0") if p):
        if CACHE_DIRS & set(Path(rel).parts):
            continue
        path = REPO_ROOT / rel
        if path.is_file():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def real_folders_snapshot() -> dict[str, dict[str, str]]:
    """The repository's files, and, when nothing else drives the engine here, the real home folder's
    `.tempergraph` and the real state root."""
    from tempergraph.store.layout import state_root_path

    snap = {"repo": repo_files_snapshot()}
    if not _DRIVEN_BY_ENGINE:
        snap["home"] = stat_tree(REAL_HOME / ".tempergraph")
        snap["state_root"] = stat_tree(state_root_path(REPO_ROOT))
    return snap


def stat_tree(root: Path) -> dict[str, str]:
    """Every path under `root` with its size and modification time (cheap, for folders that may be large)."""
    out: dict[str, str] = {}
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            try:
                st = p.lstat()
            except OSError:
                continue
            out[str(p.relative_to(root))] = f"{st.st_size}:{st.st_mtime_ns}"
    return out


def changed_paths(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]]) -> list[str]:
    out: list[str] = []
    for area in sorted(set(before) | set(after)):
        a, b = before.get(area, {}), after.get(area, {})
        out += [f"{area}:{k}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    return out


def pytest_sessionstart(session: pytest.Session) -> None:
    """Remember the real folders once, on the controller (never on a worker, never in a nested run) (TST-B5)."""
    if is_xdist_worker() or is_nested():
        return
    session.config.stash[_BEFORE] = real_folders_snapshot()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the session when a test changed a file of the repository, the real home or the real state root (WSP-AC2)."""
    before = session.config.stash.get(_BEFORE, None)
    if before is None:
        return
    changed = changed_paths(before, real_folders_snapshot())
    if changed:
        session.config.get_terminal_writer().line(
            "the suite changed the real folders: " + ", ".join(changed[:20]), red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


_BEFORE: pytest.StashKey[dict[str, dict[str, str]]] = pytest.StashKey()


os.environ.setdefault("TEMPERGRAPH_LOG_LEVEL", "WARNING")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`live` tests spend money on a signed-in `claude`: skipped unless TEMPERGRAPH_LIVE=1 (live-checks plan).
    `suite_audit` tests run the suite again file by file: skipped unless TEMPERGRAPH_SUITE_AUDIT=1 (TST-AC5)."""
    live = os.environ.get("TEMPERGRAPH_LIVE") == "1"
    audit = os.environ.get("TEMPERGRAPH_SUITE_AUDIT") == "1"
    skip_live = pytest.mark.skip(reason="live: set TEMPERGRAPH_LIVE=1 on a machine with a signed-in claude")
    skip_audit = pytest.mark.skip(reason="suite_audit: set TEMPERGRAPH_SUITE_AUDIT=1 to run every test file alone")
    for item in items:
        if "live" in item.keywords and not live:
            item.add_marker(skip_live)
        if "suite_audit" in item.keywords and not audit:
            item.add_marker(skip_audit)
