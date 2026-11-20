# Revise mode: change the outcome after runs

1. **Evidence.** `tempergraph outcome candidates <workflow>` lists the signals with thread ids and counts. Read only what the person opens.
2. **Open a session.** `tempergraph author start <workflow> --revise` copies the package's drafts and approvals. `author show` says which phase moved.
3. **Draft.** For each candidate the person picks, draft a new or changed criterion and classify it by the search order of phase 4. Raise `revision` by one, and update the blueprint's `outcome_ref`.
4. **Show the change classes.** `tempergraph author check <id>` lists `changes`: `weakening` (a criterion removed, a blocker made a warning, a verifier of lower trust), `strengthening` or `neutral`. Show the outcome and verification tables before and after, with every weakening row marked. A weakening is never written without the person's yes on that table.
5. **Approve** the phases `author show` lists under `cleared`, up to 7, each with `tempergraph author approve <id> <phase>`.
6. **Write and check.** `tempergraph scaffold <id> --out <package> --update-docs` writes the new revision (`origin: revise_session`), the docs and the blueprint. Then `tempergraph author verify <package>`. A new check needs its fixtures.
7. **Producer changes come after.** A prompt or step change the revision suggests is a separate change, made after this one: the grader changes first.
