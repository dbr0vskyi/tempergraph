# Phase 2: the final outcome, the lint and the guidance ladder

## Three questions

Ask, in one turn: what would make you reject the result; what has gone wrong before; what does a reviewer check first. Each answer becomes one observable statement in `final`, with `id` (a short slug), `text`, `severity` and, later, a verifier.

- **One claim per criterion.** Split "X and Y" into two.
- **A vague word is rewritten** with a measure ("complete" becomes "every acceptance criterion in the ticket is addressed by at least one task"), or dropped with a note after asking.
- **Severity.** A blocker, unless the person would say "proceed, but fix it as you go"; then a warning.
- **Deliverables** name what the run leaves (`key`, `kind`, `where`). The statement names at least one deliverable.

The outcome draft follows `outcome.json`: `statement`, `deliverables`, `final`, `intermediate`, `assumptions`, `revision`.

## The sufficiency check

`tempergraph author check <id>` lists `sufficiency` gaps. Phase 2 needs all of these:

- an observable statement, with no `criterion-vague` or `criterion-unobservable` finding on it
- at least one deliverable
- at least one blocker final criterion
- every final criterion passing the lint

## Lint codes and what to do

| Code | Do |
|---|---|
| `criterion-vague` | Ask what they would look at to tell it is that word, and offer two observable rewrites |
| `criterion-compound` | Propose a split, one criterion per claim |
| `criterion-unobservable` | Ask where a reviewer would see it, listing the deliverables |
| `criterion-self-graded` | Rewrite as a fact the gate checks, not a report by the producer |
| `criterion-unanchored` | Draft `met`, `partial`, `unmet` and `evidence` from the examples, then let the person edit |
| `criterion-overlap` | Merge, or narrow the intermediate one to what its step decides |
| `criterion-no-seed` | Ask for one example of each, or offer a contrast pair. Seeds are graded in a later release, so this stays a warning |

## The guidance ladder

Take it in order for each criterion that fails, at most three questions per turn.

| Rung | Do | Stop when |
|---|---|---|
| 1 Clarify | Ask the question the lint code names, plus the three questions above | The answer gives an observable statement |
| 2 Examples | Show two or three criteria of the same task kind from `criteria-examples/<kind>.md` (document, code-change, analysis, ticket, data, message), each with its class and scale, and ask which is closest | The person adapts one |
| 3 Contrast pair | Write two short outputs that differ only in the property in doubt (or use the person's good and bad examples), and ask which passes and why | The reason names the property. It becomes the criterion, and the pair becomes its seeds |
| 4 Grade a draft | Write one full sample output and ask the person to mark what they would send back | Each mark becomes a criterion candidate |
| 5 Decide | After two rounds with no observable form, offer a `person` sign-off with their own question, `none` with a reason, or dropping it. Record the decision | A recorded decision |

When the sufficiency check holds and the person says yes, run `tempergraph author approve <id> 2`.
