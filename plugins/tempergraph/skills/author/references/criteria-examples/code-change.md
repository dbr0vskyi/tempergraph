# Criteria examples: a code change

| Criterion | Class | Scale or verifier |
|---|---|---|
| The project's tests pass | `check` | `{"command": "pytest -q"}`, or the test command the inventory found (`existing:test`) |
| The type check passes | `check` | the inventory's `existing:type_check` command |
| The branch is committed and pushed | `check` | `git_clean` and `git_pushed` |
| Every acceptance criterion of the ticket is met by a change or a test | `judge` | met: each criterion maps to a named change or test; partial: no partial, any gap is UNMET; unmet: a criterion with nothing that meets it; evidence: criterion to file and line |
| The change touches no file outside the ticket's scope | `judge` | met: every changed file is named by the plan; unmet: a changed file the plan does not name; evidence: the changed files list |
