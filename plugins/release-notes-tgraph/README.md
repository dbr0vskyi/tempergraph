# release-notes

An example tempergraph workflow: the minimal package of the engine's [PKG-B25](../tempergraph/docs/specs/88-workflow-package.spec.md). One step writes `notes.md` for the changes since the last tag; its gate runs a model-free check (the four headings) and a judge (every entry matches its change), and the outcome gate checks that nothing merged is missing.

```
tempergraph workflows register plugins/release-notes-tgraph
tempergraph run release-notes v1.2
```

Read the package top-down: `outcome.json` (what a good result is), `workflow/release_notes/__init__.py` (the declaration), `prompts/` and `judges/`, then `evals/` (the cases and the check fixtures).
