# Capability list

## Purpose

The list of every capability the repository's specs own, which prepare writes at the start of each run so that triage and discovery can find the spec that owns a rule before they decide where a task's rule goes. Triage names the owning spec in each gap row from it, and discovery searches it before it writes a new spec. It is generated from the specs and never edited or committed, so no change to a spec has to touch it (documents rule 3). It does not own the specs' format, which `spec.rule.md` states. Part of the [overview](overview.spec.md); the unit is [prepare](prepare.spec.md).

## Behaviours

### CAPL-B1 Every spec of the repository is listed

WHEN prepare runs THE prepare step SHALL write `.tempergraph/capabilities.md` with one entry for each spec of the repository outside the folders of copies and fixtures, in path order, holding the spec's path, its title, the first sentence of its Purpose and the heading of each of its behaviours.

- GIVEN specs `docs/specs/a.spec.md` and `docs/specs/b.spec.md` WHEN prepare runs THEN the list holds an entry for each, `a` first, each with its title and behaviour headings
- GIVEN a spec only inside an `evals/` folder WHEN prepare runs THEN the list holds no entry for it

### CAPL-B2 The list carries no behaviour text

WHEN prepare writes an entry THE prepare step SHALL leave out the spec's behaviour sentences and scenarios, and cut the Purpose's first sentence at 300 characters.

- GIVEN a behaviour with a sentence and two scenarios WHEN prepare writes its spec's entry THEN the entry holds the behaviour's heading and neither the sentence nor the scenarios

### CAPL-B3 The list is never committed

WHEN a step of the run commits its files THE run SHALL leave the capability list out of the commit.

- GIVEN a run that wrote the list WHEN prepare commits THEN the commit holds no `.tempergraph/capabilities.md`

### CAPL-B4 The list prints who uses each spec

WHEN prepare writes an entry for a spec that other specs name under their `## Depends on` THE prepare step SHALL add to the entry one `Used by:` line that names each of those specs by its path, in path order.

- GIVEN `docs/specs/b.spec.md` whose `Depends on` names `a.spec.md` WHEN prepare runs THEN the entry of `a` holds `Used by:` with `docs/specs/b.spec.md`
- GIVEN a spec that no other spec names under `Depends on` WHEN prepare runs THEN its entry holds no `Used by:` line

## Acceptance criteria

- CAPL-AC1 (CAPL-B1): After prepare, `.tempergraph/capabilities.md` holds one entry per spec of the repository, in path order, and none for a spec inside `evals/`
- CAPL-AC2 (CAPL-B1, CAPL-B2): An entry holds the spec's path, title, the first sentence of its Purpose and its behaviour headings, and no behaviour sentence or scenario
- CAPL-AC3 (CAPL-B3): The commit prepare makes holds no file under `.tempergraph/`
- CAPL-AC4 (CAPL-B4): The entry of a spec that another spec names under `Depends on` holds a `Used by:` line with that spec's path, and the entry of a spec no other spec names holds none
