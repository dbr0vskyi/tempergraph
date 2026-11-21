"""Tests of the missing config file behaviour."""


def test_missing_file_message(run_tool):  # CFG-AC1
    assert run_tool().stderr.count("tool.toml") == 1


def test_missing_file_exit_code(run_tool):  # CFG-AC2
    assert run_tool().returncode == 2
