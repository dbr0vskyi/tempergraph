# Criteria examples: a document

| Criterion | Class | Scale or verifier |
|---|---|---|
| The document has the template's headings, in order | `check` | `headings_in_order` over the document |
| Every section under "Decisions" names who decided and when | `judge` | met: each decision names a person and a date; partial: no partial, any gap is UNMET; unmet: a decision with no owner or date; evidence: the decision lines |
| No paragraph states a number without its source | `judge` | met: every figure is followed by a link or a named source; unmet: a figure with no source; evidence: the figures and their sources |
| The summary is at most 150 words | `check` | `pattern_absent` on a long summary, or a hand-written check that counts |
| It is safe to publish to customers | `person` | role: the release manager; question: "Is this safe to publish?" |
