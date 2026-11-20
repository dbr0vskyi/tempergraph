# Criteria examples: data

| Criterion | Class | Scale or verifier |
|---|---|---|
| The output file matches its JSON Schema | `check` | the inventory's `existing:schema`, run by a fixed command |
| No row has an empty `id` | `check` | `pattern_absent` for an empty id field |
| Every total matches the sum of its rows | `check` | a hand-written check (`{"check": "totals_match"}`) |
| Each outlier kept in the data has a reason in the notes | `judge` | met: every flagged outlier has a reason; unmet: one has none; evidence: outlier to reason pairs |
