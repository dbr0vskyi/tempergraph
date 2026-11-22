"""The same result however the tests are spread (TST-B4).

The nested runs carry the guard variable (`tests/conftest.py`); these tests return at once when it is set, so
they never nest again.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .conftest import ENGINE_ROOT, SAMPLE_TEST_FILES, is_nested, nested_pytest, outcome_counts

SUITE_FILES = {"test_suite_runner.py", "test_suite_same_result.py", "test_suite_isolation.py"}
NO_ADDOPTS = ("-o", "addopts=--strict-markers")  # the project's `-q` would turn the id list into counts per file


def _ids(output: str) -> set[str]:
    return {ln.strip() for ln in output.splitlines() if "::" in ln and ln.startswith("tests/")}


def test_workers_and_one_process_pass_and_skip_the_same_tests() -> None:  # TST-AC4, AC 1
    if is_nested():
        return
    serial = nested_pytest("-n", "0", *SAMPLE_TEST_FILES)
    spread = nested_pytest(*SAMPLE_TEST_FILES)
    assert serial.returncode == 0, serial.stdout[-3000:]
    assert spread.returncode == 0, spread.stdout[-3000:]
    assert outcome_counts(serial.stdout) == outcome_counts(spread.stdout)
    assert outcome_counts(serial.stdout).get("passed", 0) > 0
    assert "failed" not in outcome_counts(spread.stdout)

    one = nested_pytest("-n", "0", *NO_ADDOPTS, "--collect-only", "-q", "tests")
    many = nested_pytest(*NO_ADDOPTS, "--collect-only", "-q", "tests")
    assert one.returncode == 0 and many.returncode == 0, (one.stdout + many.stdout)[-3000:]
    assert _ids(one.stdout) and _ids(one.stdout) == _ids(many.stdout)


def test_each_test_file_passes_alone() -> None:  # TST-AC5, AC 1
    if is_nested():
        return
    files = sorted(p.name for p in (ENGINE_ROOT / "tests").glob("test_*.py") if p.name not in SUITE_FILES)
    assert files

    def alone(name: str) -> tuple[str, int, str]:
        run = nested_pytest("-n", "0", f"tests/{name}")
        return name, run.returncode, run.stdout[-2000:] + run.stderr[-500:]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(alone, files))
    failed = [f"{name} (exit {code})\n{tail}" for name, code, tail in results if code != 0]
    assert not failed, "\n\n".join(failed)
