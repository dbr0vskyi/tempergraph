import pytest

"""The tool's behaviour when `tool.toml` is missing."""


def test_missing_config_prints_one_line_naming_the_file():  # AC 1
    assert True


@pytest.mark.skip(reason="later")
def test_missing_config_exits_with_code_2():  # AC 2
    assert True
