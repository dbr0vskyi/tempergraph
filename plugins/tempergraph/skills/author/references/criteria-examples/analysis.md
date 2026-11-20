# Criteria examples: an analysis

| Criterion | Class | Scale or verifier |
|---|---|---|
| The report has a "Findings" and a "Recommendations" section | `check` | `headings_in_order` |
| Every finding cites the data it comes from | `judge` | met: each finding names a file, query or table; unmet: a finding with no source; evidence: finding to source pairs |
| Each recommendation follows from at least one finding | `judge` | met: each recommendation names the finding it answers; partial: one does not; unmet: most do not; evidence: the pairs |
| The conclusion fits the team's strategy | `person` | role: the team lead; question: "Does this fit our plan for the quarter?" |
