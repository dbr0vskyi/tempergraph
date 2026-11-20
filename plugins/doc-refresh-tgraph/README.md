# doc-refresh

An example tempergraph workflow: three units that refresh named sections of a document so they match the repository.

| Unit | Kind | What it shows |
|---|---|---|
| `outline` | script (`call=`) | a unit with no session: it writes `outline.md`, the document's headings |
| `draft` | step | a model-free check (every outline heading kept, in order), a judge, and a route on the `size` value: `minor` goes straight to the finalizer, `major` to `review` |
| `review` | step | a judge, a person's approval, and a trip back to `draft` |
| finalizer | function | reports where the document was written (`written`) |

```
tempergraph workflows register plugins/doc-refresh-tgraph
tempergraph run doc-refresh "docs/guide.md: the install section, for Python 3.12"
```

It was authored the T9.2 way: an approved blueprint and outcome scaffolded with `tempergraph scaffold`, then the script, the route, the `dr-headings` check, the prompts and the finalizer written by hand. `outcome.json` says what a good result is; `evals/calibration/` holds two seed fixtures per judged criterion, unlabelled until a person labels them (JCL).
