import pytest

from tool.config import load


def test_a_missing_file_is_named_on_standard_error(capsys):  # AC 1
    with pytest.raises(SystemExit):
        load("tool.toml")
    assert "tool.toml" in capsys.readouterr().err
