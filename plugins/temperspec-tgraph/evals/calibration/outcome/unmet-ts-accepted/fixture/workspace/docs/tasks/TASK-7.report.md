# Code report: TASK-7

## Rows

| Row | Status | Note |
|---|---|---|
| 1.1 | done | `tests/test_config.py::test_missing_config_prints_one_line_naming_the_file` |
| 1.2 | done | `tests/test_config.py::test_missing_config_exits_with_code_2` |
| 1.3 | done | `src/tool/config.py`: new module |
| 1.4 | done | `src/tool/main.py` |
| 1.5 | done | `README.md`: new last paragraph |

## Verification

- `pytest tests/test_config.py`: passed, 2 tests
- `ruff check src tests`: passed

## Deviations

- None
