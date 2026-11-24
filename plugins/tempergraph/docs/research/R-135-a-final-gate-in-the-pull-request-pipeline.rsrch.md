# R-135 A final gate in the pull request's pipeline

## Problem statement

The owner asked on 2026-11-21 for research into an engine capability: an optional, **extra** final gate that runs in a CI pipeline on a pull request a workflow opened. It adds to the gates inside the run and moves none of them. A workflow author gets it as an option while authoring; the engine then generates the pipeline file and guides the person through the configuration that is left. The owner's aim: a reviewer of the pull request sees a report that says whether the result can be trusted, for example how much of the planned work was done and whether the code agrees with the specs it claims to implement.

The questions: what the design already has for pipelines and pull requests; how this gate differs from the planned `pipeline` stage; what such a gate can read when the run's state stays on another machine; what it may post on a pull request; how to keep it safe, executor-agnostic, OS-agnostic and model-free where no model is needed; how authoring offers it; and what to build first.

This note answers the engine's side as a general capability. How one workflow shapes its report is that workflow package's business ([ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md)).

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S3 | This design: the outcome gate and outcome record ([OUT-B15, OUT-B16, OUT-B17, OUT-B18, OUT-B19](../specs/90-run-outcome.spec.md)); the judge prompt and verdict rule ([JDG](../specs/05-judge-and-verdict.spec.md)); judge views ([GRD](../specs/06-independence-guard.spec.md)); the check context and command runner ([CHK](../specs/75-check-contract-and-command-runs.spec.md)); the finalizer's context ([FIN-B6](../specs/78-finalizer-contract.spec.md)); the publish boundary ([SEC-B8 to SEC-B11](../specs/14-security.spec.md), OVR-B11) | Design set | [specs](../specs/00-overview.spec.md) |
| S4 | This design: the `pipeline` stage and `promote-check` ([ADR-0041](../adr/0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md), [PRO](../specs/95-promotion-check.spec.md)); carried state ([CAR](../specs/96-run-state-on-a-branch.spec.md)); the caller kind `pipeline` ([PRV-B7](../specs/85-caller-provenance.spec.md)); `schedule export --for github-actions\|gitlab-ci\|crontab` and unattended credentials per executor ([TCK-B18, TCK-B19, TCK-B20](../specs/84-schedule-ticks-and-unattended-fires.spec.md)); authoring phases and the blueprint ([AUT-B16, AUT-B17, AUT-B18](../specs/89-workflow-authoring.spec.md), [SCF-B9, SCF-B11](../specs/91-blueprint-and-scaffold.spec.md)) | Design set | [specs](../specs/00-overview.spec.md) |
| S5 | Live check L-25 (2026-11-21): every judgement came back `gap: true` with all criteria `MET`, because the judge has no shell and could not confirm the diff or `git log`; every judged gate paused | Live check record | [live-checks plan](../plans/live-checks.plan.md) |
| S6 | GitHub: `pull_request_target` runs with the base repository's secrets and is the root of "pwn request" compromises; `pull_request` from a fork gets no secrets and a read-only token; untrusted PR fields (title, branch name) cause script injection without a checkout; artifacts of fork runs are untrusted | Platform documentation, security research | [Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target), [GitHub Security Lab, preventing pwn requests](https://securitylab.github.com/research/github-actions-preventing-pwn-requests) |
| S7 | OWASP: an AI assistant in CI (PR reviewer, issue triager) that untrusted users can trigger, with secrets or a write token, risks secret exfiltration through prompt injection; give it the minimum tools | Security guidance | [OWASP GitHub Actions cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/GitHub_Actions_Security_Cheat_Sheet.html) |
| S8 | GitHub check runs: `output.summary` and `output.text` take Markdown up to 65,535 characters each; at most 50 annotations per request, more by updates; Actions job summaries render Markdown written to `$GITHUB_STEP_SUMMARY` | Platform documentation | [REST check runs](https://docs.github.com/en/rest/checks/runs), [job summaries](https://github.blog/news-insights/product-news/supercharging-github-actions-with-job-summaries/) |
| S9 | GitLab: merge request pipelines run for jobs whose rules match `CI_PIPELINE_SOURCE == "merge_request_event"`; running one needs the Developer role on the source project | Platform documentation | [Merge request pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/) |
| S10 | Claude Code's GitHub Action: authenticates with `anthropic_api_key` or `claude_code_oauth_token` (from `claude setup-token`); takes a `prompt`; tool limits go through `claude_args: --allowedTools` | Vendor documentation | [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions), [claude-code-base-action](https://github.com/anthropics/claude-code-base-action) |
| S11 | GitHub Copilot code review leaves a "Comment" review by default, never "Approve" or "Request changes", so it does not count toward required approvals; approving is an opt-in preview | Vendor documentation | [Copilot code review](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review) |
| S12 | Qodo Merge links a ticket to a pull request by a link in the description or the branch name, and its compliance tool rates the changes against the ticket's requirements (fully or partially compliant), optionally flagging unrelated changes | Vendor documentation | [Qodo ticketing integrations](https://docs.qodo.ai/qodo-documentation/qodo-merge/integrations/ticketing-integrations), [Qodo compliance](https://docs.qodo.ai/qodo-documentation/qodo-merge/features/compliance) |

## Key findings

### F1 The planned `pipeline` stage is a different thing `confirmed`

ADR-0041 and PRO mean by "pipeline" an unattended job that **runs the workflow** with the engine CLI, gated by a measured promotion stamp, later than release 2 (S4).

The owner's gate runs **no step**. The work was done wherever the run ran (a laptop today); the pipeline only grades what landed in the pull request. So it needs no promotion stamp, no carried state, no pause handling and no step executor in CI: one check and, optionally, one judge. It is buildable before pipeline runs and does not wait on them.

| | `pipeline` stage (ADR-0041) | Pull-request gate (this note) |
|---|---|---|
| Runs in CI | the whole workflow | the final check and judge only |
| Needs | promotion stamp, carried state, a person for pauses | the package at a pinned version, a credential for the judge |
| Writes | the run's commits | a report and a check status |
| Pauses | exit 3, resumed elsewhere | never: a gate in CI has no one to ask |

### F2 The bar already exists: the outcome gate `confirmed`

Every run ends at a mandatory `outcome` gate that grades the final criteria of `outcome.json` by check, judge or person, and leaves an `OutcomeRecord` with a status and trust per criterion (OUT-B15, OUT-B16, OUT-B17, OUT-B18, OUT-B19; S3). A pipeline gate that grades the same final criteria keeps "one bar": the step gates, the outcome gate, the improvement loop and now the reviewer read the same criteria. Inventing a second rubric for CI would let the two drift, the failure ADR-0031 and OUT-B20, OUT-B21 guard against.

What the pipeline adds is **independence of place**, not a new rubric:

- It sees only the repository at the pull request's head and the pull request's metadata, never the run's state, the step's account or a person's local feedback. A claim a step made and the in-run judge believed cannot reach it.
- It grades the branch **as pushed**, after any hand edits, rebases or forced pushes since the run finished. The in-run gate graded a tree that may no longer exist.
- It runs on a clean machine with the repository's own tools, so "the tests pass" is shown off the author's machine.
- Its executor and model may differ from the run's, which JDG's design notes count as a feature (a model rates its own kind of output well).

### F3 What a pipeline can and cannot read `confirmed`

The run's state root stays local: transcripts, prompts, the request and feedback files are local-only (SEC-B8 to SEC-B11, C9), and a carried state branch is deleted when the run finishes (CAR-B8, CAR-B3). So a pipeline gate grades from what git and the platform hold.

| Input | Available in CI | Note |
|---|---|---|
| The branch's files and history, the base, the diff | yes | a full-depth fetch; shallow clones lose the merge base  |
| The repository's own test, lint and type commands | yes | run by the engine's command runner, not by the judge (F4) |
| The package's `outcome.json`, checks and judge brief | yes, if the job installs the package at the version that ran | a different version grades against a different bar (F9) |
| The pull request's title, body, labels, author | yes | untrusted text (F5) |
| The request, a person's feedback, step outputs, the in-run judgement | no | local by design; a criterion that needs them cannot be graded here |
| The in-run outcome record | only as a published **receipt** of metadata (F9) | ids, statuses, trust, digests: words from fixed lists, which C9 allows |

So each final criterion is either **repository-gradable** or not. Checks that read only `GitFacts`, files and command results are; a judge criterion whose references are repository files is. A criterion that needs the request text (when the request is not a committed file) or a person's sign-off is not, and the report must list it as "not graded in CI" with the in-run status from the receipt, never drop it (OUT-B13, OUT-B14's rule that an unverified criterion is shown, never passed silently).

### F4 The judge must get evidence, not a shell `confirmed`

L-25 found every in-run judgement marked `gap` because the judge could not run `git` (S5). In CI the pull is the other way: a judge with a shell and the job's token is exactly the prompt-injection-to-exfiltration path OWASP warns about (S7), and an executor that cannot restrict tools never hosts a judge ([R-003](R-003-executor-capability-matrix.rsrch.md)).

The design already has the answer: checks run commands through the engine's allow-listed runner, and the judge reads the check's evidence and findings (CHK-B12, CHK-B13, CHK-B14; JDG-B11, JDG-B12 "workspace facts: branch, base, changed files, diff stat, computed by the engine"; JDG-B6). In CI the gate's check must therefore assemble, model-free: the diff against the base (clipped with a marker), the changed paths, the result of the repository's verification commands, and the per-criterion findings, and hand them to a judge with read-only views and no shell. This is also the general fix for L-25 inside runs; the pipeline gate makes it non-optional.

### F5 Running a model on a pull request is a security surface `confirmed`

From S6 and S7:

- Trigger on `pull_request`, never `pull_request_target`: a fork's pull request then gets no secrets and a read-only token, so the gate cannot call a model and must end **neutral** with "no credential on fork pull requests", not fail.
- Two jobs: a grading job with `contents: read` only and the model secret, and a posting job with `checks: write` (and `pull-requests: write` for a comment) that reads the grading job's report artifact and runs no model and no repository code. The model never holds a write token.
- Untrusted PR fields (title, branch, body) never enter a shell expression; they pass through environment variables or files.
- The judge reads repository content and PR text as untrusted input: read-only views, no network, no MCP servers, no setting sources, the API key absent from any command it could run (SEC-B12, SEC-B13, the tool host's stripping). This is the same posture the session reviewer already has (ADR-0118).
- A gate on a pull request from a stranger costs money per push; a label only writers can add, or a "ready for review" trigger, bounds it.

### F6 What may be posted conflicts with the publish boundary as written `confirmed`

SEC-B8 to SEC-B11 says pull-request text carries "names, counts, hashes and words from fixed lists only", which keeps judge text out of the pull request because a judge's quotation of a secret or a local path could leak. The owner wants a report a reviewer can trust, which a table of statuses alone serves only partly.

The boundary exists because local evidence (the request, feedback, transcripts) may hold private text. A pipeline judge never sees local evidence: everything it can quote is already in the repository or the pull request, visible to the same audience. What remains is a secret committed to the repository (the scrubber's job) and injected output (a link or markup the judge was told to write).

| Report content | Leak risk | Proposal |
|---|---|---|
| Criterion id, the author's criterion text from `outcome.json`, status, trust, grader | none: package content and fixed words | always |
| Evidence pointers: `path:line`, command and exit code, counts | low | always, paths relative to the repository root |
| The judge's one-line reason per non-MET criterion | low in CI (no local evidence), not zero | opt-in per workflow, scrubbed, clipped (300 characters), rendered as plain text with links and markup removed |
| The judge's full answer, the diff, command output | medium | job artifact only, never in a comment |

That third row needs a recorded exception to SEC-B8 to SEC-B11: a "pipeline report" class whose only free text comes from a judge that read nothing local. This is a decision, not a finding, so it goes to a decision record.

### F7 Where the report shows on each platform `supported`

| Platform | Surface | Fits |
|---|---|---|
| GitHub | A **check run** named for the workflow: conclusion, a Markdown summary up to 65,535 characters, annotations on `path:line` (50 per request) (S8) | The status reviewers already read; can be made a required check |
| GitHub | One **sticky comment**, edited in place on each push, keyed by a hidden marker | Visible in the conversation tab; optional, since it notifies |
| GitHub | The **job summary** | Free, but one click away; good for the long form |
| GitLab | A merge request **note**, edited in place, plus the job's status in the merge request pipeline (S9) | Same roles; annotation formats (code quality report) `uncertain`, not checked here |
| Any other | The engine's `report.md` and `report.json` as job artifacts, and the exit code | The floor every CI system can show |

The engine stays CI-agnostic by **writing files** (`report.md`, `report.json`, optional SARIF later) and an exit code; posting is a thin platform step in the generated pipeline file, using the platform's own CLI or API. This matches `schedule export`, which prints a snippet and keeps nothing (TCK-B20).

### F8 The gate should advise by default, and block only on trusted evidence `supported`

Copilot's reviewer leaves a "Comment" review that never counts as an approval (S11), and the merge decision stays with a person. A pipeline gate is the same kind of reviewer. Two modes:

| Mode | Check conclusion | When |
|---|---|---|
| `report` (default) | `neutral` (GitHub) or allowed-failure job (GitLab), whatever the grades | Always safe to turn on |
| `block` | `failure` only on a **check** criterion's failure or a blocker UNMET from a judge whose binding is `accepted` (trust `calibrated`, OUT-B13, OUT-B14, JCL); everything else stays advisory | The person makes it a required check |

Blocking only on trusted evidence is the rule ADR-0121 set for ladders: an uncalibrated judge's grade is not evidence enough to change what happens. A judge in CI on a new executor or model starts `uncalibrated` on that binding (JRK, JCL) until scored there, so `block` is a no-op for its criteria until then, and the report says so.

The gate never approves a pull request and never requests changes; it only sets its own status.

### F9 The pipeline must know which run made the pull request `inferred`

A pull request alone does not say which workflow, version, outcome revision or task it came from, and a person may open one by hand. Qodo links a ticket by a link in the body or the branch name (S12). The finalizer already writes the body (FIN-B6) and may carry metadata (C9). Proposal: the engine renders a **receipt**, a hidden marked block from fixed fields only, and offers it in the finalizer's context; a finalizer that opens a pull request appends it to the body:

| Receipt field | From |
|---|---|
| `workflow`, `workflow_version`, `outcome_revision` | the run (VER, OUT-B20, OUT-B21) |
| `task_id`, `thread_id` (hashed) | the run |
| `head`, `base` | the commit the run finished on and its base |
| per final criterion: id, in-run status, trust | the outcome record |
| `engine_version` | the engine |

The pipeline then grades against exactly that workflow version, reports "version drift" when the installed package differs, and shows the in-run status beside its own, so a reviewer sees where the two disagree. A body is editable by anyone with write access, so the receipt is a **claim**: the gate checks that `head` is an ancestor of the pull request's head, marks "commits since the run" when it is not the head itself, and never trusts a receipt status over its own grade. A file committed on the branch would carry the same data but leave a trace in the base branch after the merge, against the owner's "no traces" rule (CAR).

A pull request with no receipt gets a neutral "not opened by a tempergraph run" unless the pipeline file names the workflow explicitly, for repositories that want the bar applied to hand-made pull requests too.

### F10 Disagreement is improvement data, read back later `inferred`

A pipeline grade that contradicts the in-run outcome record is the "escape" OUT-B18, OUT-B19 counts in `later[]`: a run graded `met` that a later signal contradicts. The pipeline runs elsewhere, so its records do not reach the local store. The finalizer's pull-request adapter already reads a pull request's state later for the loop (FIN-B1, FBK `pr_state`); the same read can fetch the gate's `report.json` (a check run's output, or a job artifact) and append it as a `later[]` signal. A first build can skip this and still be useful to reviewers.

### F11 Credentials and executors: no new executor work, one trap `supported`

The judge in CI runs on any executor with unattended credentials (TCK-B18, TCK-B19): `messages-api` and `agent-sdk` with an API key; `claude` with an API key, cloud credentials or `CLAUDE_CODE_OAUTH_TOKEN` (S10). TCK records that a judge launched with `--bare` does not read the OAuth token, so a `claude` judge in CI needs an API key or cloud credentials or is refused `judge_credential` (TCK-B6). The `--bare` behaviour itself is `supported` by one source and its probe (P-CC-1) has an open finding on plugins in the 0.2.0 live report, so the guide must state the credential rule and the gate's preflight must refuse early rather than fail mid-job. The runner's OS does not matter: the engine is a Python package (ADR-0115) and the posting step uses the platform's own tools.

### F12 Authoring and setup split between the package and the repository `inferred`

The package and the repository that uses it are different places: a workflow package is a plugin installed for the engine; the pipeline file belongs to each repository where the workflow opens pull requests. So:

- **Authoring** records the decision in the blueprint (an optional `pr_gate` block: mode, platform hint, which final criteria to grade, whether reasons are shown, the judge's executor and sizing with its reason, as SCF-B10 requires for every session). Phase 4 of the interview already asks how each final criterion is verified; it adds one question: should a reviewer see this graded on the pull request? `author verify` checks the block model-free (criteria exist, are repository-gradable, sizing stated).
- **Setup in a repository** is a verb, like `schedule export`: generate the pipeline file for a named platform with the engine and package pinned to exact versions, the two-job shape of F5, the triggers of F8, a concurrency group that cancels stale runs and a cost cap. A model-free doctor checks the file against the package (versions, permissions, trigger, secret name present as a reference) and lists what only a person can do: add the secret, decide whether the check is required. The plugin skill walks the person through those steps and shows each command; it never writes a secret.

### F13 Cost is bounded by model-free work first `inferred`

The gate runs checks first, and the judge only when the checks pass and the head changed since the last graded head (cache by head commit and outcome revision). On a draft it does nothing until "ready for review", unless a writer adds a label. One judge session per graded head, under `--run-cost-cap`, is the whole model spend. Its cost lands in the job's own record, not in the run's ledger, until F10's read-back exists.

## Conclusions

1. The pull-request gate is a capability of its own, separate from the `pipeline` stage of ADR-0041: it re-grades a finished run's result in CI and runs no step, so it needs no promotion, no carried state and no pause handling, and can be built before pipeline runs.
2. It grades the final criteria of `outcome.json`, the same bar as the in-run outcome gate; it adds independence of place (only the pushed branch, a clean machine, possibly another model), not a second rubric.
3. Each final criterion is repository-gradable or not; the report lists the rest with their in-run status and never omits one.
4. The judge gets engine-assembled evidence (diff, changed paths, command results, check findings) and no shell; this also closes L-25's finding inside runs.
5. The engine writes `report.md`, `report.json` and an exit code; a thin, generated platform step posts them, so the engine stays CI-agnostic and the model never holds a write token.
6. The default mode is advisory; `block` fails only on check failures and on blockers from `accepted` judges, and the gate never approves.
7. The engine renders a metadata-only receipt that the finalizer puts in the pull request body so the pipeline knows the workflow version and can show in-run against pipeline grades; the receipt is a claim checked against the branch.
8. Showing judge reasons on a pull request needs a recorded exception to the publish boundary (SEC-B8 to SEC-B11); without it the report is statuses, trust and `path:line` evidence only.
9. Authoring records the option in the blueprint; a separate setup verb writes the pipeline file into each repository, and a model-free doctor plus the skill guide the person through secrets and required-check settings.

## Recommendation

Build it as one engine capability with its own spec and two decision records, after the documents below are reviewed:

| Document | Holds |
|---|---|
| ADR-0130 A run's result is re-graded in the pull request's pipeline by its own outcome criteria, advisory by default | F1, F2, F8: the separate capability, one bar, `report` and `block`, never approving |
| ADR-0131 A pipeline report may carry a judge's scrubbed one-line reasons | F6: the exception to SEC-B8 to SEC-B11, opt-in, clipped, plain text |
| Spec 98 PRG, pull-request gate | The receipt (F9), what is graded (F3), the evidence assembly (F4), the report files (F7), the two-job pipeline shape and triggers (F5, F13), the modes (F8), the setup verbs and doctor (F12), refusals (fork, no credential, version drift) |
| Amendments | OUT (repository-gradable criteria; the receipt fields), FIN (the context offers the rendered receipt; a validation warning when a workflow with `pr_gate` has a finalizer that never uses it), SEC-B8 to SEC-B11 (the report class), SCF-B9, SCF-B11 and AUT-B16, AUT-B17, AUT-B18 (the `pr_gate` blueprint block and the phase 4 question), CLI (reserve the verbs), JDG (evidence from the check, no shell, as the general fix of L-25) |

First build, smallest useful slice: GitHub Actions only, `report` mode, check criteria plus judge criteria with statuses and `path:line` evidence (no reasons until ADR-0131 is accepted), receipt in the body, generated file and doctor. Then GitLab, `block`, reasons, and the read-back of F10. Proposed verbs, to be fixed in the spec: `tempergraph pr-gate run <workflow> [--pr-head <sha>] [--receipt <file>] [--out <dir>]`, `tempergraph pr-gate init <workflow> --for github-actions|gitlab-ci`, `tempergraph pr-gate doctor <workflow>`.

## Open questions

| Question | Owner | Default assumed in this note |
|---|---|---|
| May a pull-request report carry judge reasons (ADR-0131), or statuses and evidence pointers only? | Owner | Opt-in per workflow, scrubbed and clipped; off in the first build |
| Is `block` mode wanted at all, given that an uncalibrated judge never blocks? | Owner | Built after `report`; check failures can block from the start |
| Which platforms after GitHub? | Owner | GitLab second; others through the report files and exit code |
| Should the gate run on pull requests a person opened by hand? | Owner | Only when the pipeline file names the workflow explicitly |
| Which release? | Owner | Release 3, beside the pipeline work, but not waiting for it |
| GitLab annotation and code quality report formats | Research when GitLab is built | `uncertain` |
