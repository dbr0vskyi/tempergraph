# Architecture decision records

Each record states one decision, the options weighed, and when to revisit it. All records are `proposed` until the owner reviews them. A record is never edited to change its decision: a new record supersedes it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-standalone-design-assumptions.adr.md) | Design tempergraph as a spec-driven doc set, standalone, with recorded assumptions | proposed |
| [0002](0002-langgraph-graph-runtime.adr.md) | Use LangGraph as the graph runtime | proposed |
| [0003](0003-workflows-as-data.adr.md) | Workflows are data in their own packages; the engine names none | proposed |
| [0004](0004-four-nodes-per-unit.adr.md) | Four nodes per unit; retries are edges; one interrupt per gate | proposed |
| [0005](0005-independent-judge-engine-verdict.adr.md) | An independent read-only judge reports; the engine derives the verdict | proposed |
| [0006](0006-executors-as-capability-adapters.adr.md) | Executors are capability-declaring adapters over headless agent CLIs | proposed |
| [0007](0007-two-first-class-executors.adr.md) | Ship two first-class executors: Claude Code CLI and Antigravity CLI | superseded by 0018 |
| [0008](0008-portable-model-aliases.adr.md) | Workflows name portable model tiers and tool capabilities; executors bind them | proposed |
| [0009](0009-normalized-session-event-stream.adr.md) | Executors translate CLI streams into one normalized session event stream | proposed |
| [0010](0010-judge-isolation-per-executor.adr.md) | Judge isolation is a declared, probe-gated capability per executor | proposed |
| [0011](0011-isolated-config-home-for-antigravity.adr.md) | Restrict Antigravity sessions with an isolated config home and a deny-only gatekeeper hook | proposed |
| [0012](0012-cost-when-executor-reports-tokens-only.adr.md) | Cost is reported and estimated apart; an engine price table fills gaps; unknown is never zero | proposed |
| [0013](0013-cross-executor-judging.adr.md) | A judge may run on another executor than its step; selection is a fixed order | proposed |
| [0014](0014-sqlite-checkpointer.adr.md) | One SQLite checkpoint database per workflow; Postgres stays a seam | proposed |
| [0015](0015-exit-codes-as-caller-contract.adr.md) | Exit codes, not prose, are the contract with every caller | proposed |
| [0016](0016-portable-authoring-surface.adr.md) | The engine adds nothing to instruction files; workflows carry per-executor authoring surfaces | proposed |
| [0017](0017-artifact-type-suffixes.adr.md) | Every SDD artifact names its type in a double file suffix | proposed |
| [0018](0018-add-messages-api-and-agent-sdk-executors.adr.md) | Add two Anthropic executors: the Messages API and the Claude Agent SDK | proposed |
| [0019](0019-in-process-executors-run-in-a-worker-process.adr.md) | Library-based executors run in an engine worker process behind the same launcher | proposed |
| [0020](0020-engine-owned-tool-loop-for-the-messages-api.adr.md) | The Messages API executor runs an engine-owned loop over a minimal engine tool host | proposed |
| [0021](0021-scope-of-planned-work.adr.md) | Fold planned work into the design by fixed rules | proposed |
| [0022](0022-observers-read-files-not-sockets.adr.md) | Observers follow a run through append-only files and read-only verbs, not a socket or a daemon | proposed |
| [0023](0023-local-activity-journal-with-tool-input-summaries.adr.md) | Keep a local activity journal per session, with scrubbed and clipped tool input summaries | proposed |
| [0024](0024-one-local-store-layout-with-a-manifest.adr.md) | One versioned layout for everything a repository's runs leave, with manual retention | proposed |
| [0025](0025-cross-machine-stats-through-opt-in-sinks.adr.md) | Gather numbers across machines through opt-in, metadata-only sinks; no tempergraph server | proposed |
| [0026](0026-telemetry-export-as-otel-genai-without-content.adr.md) | Export telemetry as OpenTelemetry with the GenAI conventions, pinned, never with content | proposed |
| [0027](0027-in-process-observers-and-wider-hook-events.adr.md) | Add an in-process observer interface for exporters, and widen lifecycle hook events | proposed |
| [0028](0028-stop-verb-as-the-only-observer-control.adr.md) | A stop verb with drain is the only run control an observer may ask for | proposed |
| [0029](0029-own-observability-first-export-deferred.adr.md) | Ship tempergraph's own observability first, capture everything locally, defer third-party export | accepted |
| [0030](0030-improvement-closes-through-measured-proposals.adr.md) | Improvement closes through measured proposals that a person merges | proposed |
| [0031](0031-steps-and-their-graders-change-apart.adr.md) | Steps and the gates that grade them change apart; weakening a gate is a person's act | proposed |
| [0032](0032-lessons-are-versioned-workflow-content.adr.md) | Lessons learned are versioned workflow content, not run-time memory | proposed |
| [0033](0033-improvement-data-is-a-requirement-on-the-run-store.adr.md) | The loop states its data needs as requirements on the shared run store | proposed |
| [0034](0034-paired-trial-on-a-fixed-case-set.adr.md) | Compare workflow versions by a paired trial on a fixed case set, decided by a sign test | proposed |
| [0035](0035-orchestration-is-data-run-by-a-model-free-supervisor.adr.md) | An orchestration of runs is data executed by a model-free engine supervisor | proposed |
| [0036](0036-orchestration-state-is-a-file-and-an-event-log.adr.md) | Orchestration state is the file plus an append-only event log; runs hold the truth; nodes are known by id | proposed |
| [0037](0037-attention-batched-waking-of-the-orchestrating-session.adr.md) | The orchestrating session is woken only when a person is needed, in batches | proposed |
| [0038](0038-batch-is-a-one-node-orchestration.adr.md) | A batch is a one-node map orchestration | proposed |
| [0039](0039-pauses-stay-with-the-person-failures-follow-node-policy.adr.md) | In an orchestration, pauses stay with the person; failures follow a declared node policy | proposed |
| [0040](0040-take-script-steps-attention-and-composition-from-archon.adr.md) | Take script and hybrid steps, an attention verb and composable workflow packs; keep step outputs free-form | accepted |
| [0041](0041-graduate-a-workflow-from-local-to-pipeline-by-measured-criteria.adr.md) | A workflow graduates from local runs to a pipeline by measured, model-free criteria | proposed |
| [0045](0045-judges-accepted-on-labelled-error-rates.adr.md) | Accept a judge on its two error rates over a labelled gold set, bounded from below | proposed |
| [0046](0046-calibration-cases-split-tune-and-holdout.adr.md) | Split calibration cases into tune and holdout, and score only on holdout | proposed |
| [0047](0047-judge-robustness-by-metamorphic-variants.adr.md) | Test judge robustness with templated variants of gold cases | proposed |
| [0048](0048-judge-graded-rates-carry-the-judges-error.adr.md) | Report judge-graded rates with the judge's state and a corrected estimate | proposed |
| [0049](0049-eval-graders-in-a-fixed-order-of-trust.adr.md) | Grade step and workflow evals by code, then an accepted judge, then a person | proposed |
| [0050](0050-advisory-read-only-audit-verb-in-three-layers.adr.md) | Audit a workflow with an advisory, read-only, model-free verb over three layers | proposed |
| [0051](0051-audit-rules-are-a-fixed-catalog-keyed-to-causes.adr.md) | Audit rules are a fixed engine catalog, each keyed to a measured cause and a shared cause code | proposed |
| [0052](0052-tool-audit-compares-grant-need-and-use.adr.md) | The tool audit compares each session's grant, need and use, judges first | proposed |
| [0053](0053-history-findings-need-a-minimum-sample.adr.md) | History findings need a minimum sample, report their n, and size limits from passing attempts | proposed |
| [0054](0054-audit-joins-existing-checks-and-files-nothing.adr.md) | The audit joins the checks other components own and files nothing | proposed |
| [0055](0055-side-by-side-engine-environments-switched-atomically.adr.md) | Install each engine release beside the current one and switch by one atomic pointer | proposed |
| [0056](0056-threads-move-to-the-new-engine-at-resume-unless-a-release-pins-them.adr.md) | Threads move to the current engine at their next resume; only a checkpoint-format break pins them | proposed |
| [0057](0057-typed-version-metadata-on-both-sides.adr.md) | Both sides carry typed version metadata: a release record and a typed changelog, a workflow version, range and stamp record | proposed |
| [0058](0058-upgrade-by-transforms-first-and-a-gated-model-workflow-for-the-rest.adr.md) | Upgrade a workflow by deterministic transforms first, and a built-in gated workflow for what needs judgement | proposed |
| [0059](0059-an-upgrade-is-done-when-model-free-checks-pass-against-the-old-baseline.adr.md) | An upgrade is done when model-free checks pass against the workflow's own pre-upgrade baseline | proposed |
| [0060](0060-registered-workflows-are-reinstalled-and-pinned-never-lost.adr.md) | Registered workflows live in a home registry, are reinstalled into every new engine, and are pinned to the old engine when they break | proposed |
| [0061](0061-lifecycle-skills-drive-plugin-commands-then-engine-verbs.adr.md) | Lifecycle skills drive Claude Code's plugin commands and then the engine verbs, from one plan and one yes | proposed |
| [0062](0062-new-node-kinds-keep-the-gated-unit.adr.md) | New node kinds keep the gated unit; LangGraph's self-routing stays out | proposed |
| [0063](0063-council-is-a-gated-step-with-engine-tallied-outcomes.adr.md) | A council is a gated step: blind members, opt-in anonymized rounds, an engine tally or a chair, one independent judge | proposed |
| [0064](0064-contest-picks-a-candidate-by-the-gates-own-judge.adr.md) | A contest runs several candidates and keeps the best by the gate's own judge and a fixed rule | proposed |
| [0065](0065-ask-unit-takes-a-persons-input-as-an-artifact.adr.md) | An ask unit takes a person's mid-run input as a validated artifact, in the human node | proposed |
| [0066](0066-flow-extensions-for-langgraph-parity.adr.md) | Five flow extensions for LangGraph parity: selective parallel, mapped sub-workflows, deadlines, fallback, breakpoints | proposed |
| [0067](0067-cache-only-model-free-script-results-per-thread.adr.md) | Cache only model-free script results, per thread, keyed by declared inputs | proposed |
| [0070](0070-one-catalog-of-run-settings-over-fixed-layers.adr.md) | One catalog of run settings, resolved over fixed layers from flags to engine defaults | proposed |
| [0071](0071-overrides-never-change-what-verifies-the-work.adr.md) | Overrides change cost, time, repetition and model choice, never what verifies the work | proposed |
| [0072](0072-threads-snapshot-settings-and-reapply-them-on-resume.adr.md) | A thread snapshots its operator settings at start and reapplies them on every resume | proposed |
| [0073](0073-rewind-on-the-thread-rerun-as-a-linked-fork.adr.md) | A person rewinds a live thread in place, and reruns any thread as a new linked thread forked from a checkpoint | proposed |
| [0074](0074-feedback-can-be-a-lasting-ruling.adr.md) | A person's feedback can be a lasting ruling that later steps and their judges are shown | proposed |
| [0075](0075-checks-get-a-context-and-an-engine-command-runner.adr.md) | Checks get a defined context and an engine command runner | proposed |
| [0076](0076-claims-may-target-a-route-skipped-back-target.adr.md) | Upstream claims and attributions may target a listed back target that a route skipped | proposed |
| [0077](0077-a-step-previews-its-own-check-in-the-attempt.adr.md) | A step previews its own gate's check inside its attempt through one engine command | proposed |
| [0078](0078-skills-are-a-declared-tool-capability.adr.md) | Skills are a declared tool capability, named by plugin path | proposed |
| [0079](0079-switches-are-measured-before-they-route.adr.md) | Switches can be measured in shadow, carry per-arm overrides, and re-arm on a spent budget | proposed |
| [0080](0080-a-person-may-grant-a-step-tools-for-a-run.adr.md) | A person may grant a step tools, commands or judge read views for a run, by a recorded flag | proposed |
| [0085](0085-classify-callers-by-the-strongest-signal.adr.md) | Classify every caller by the strongest signal it leaves; a declaration may only lower trust | proposed |
| [0086](0086-a-relayed-decision-counts-as-a-persons-only-with-host-turn-evidence.adr.md) | A relayed decision counts as a person's only with turn evidence from the host | proposed |
| [0087](0087-a-supervision-journal-written-by-the-host-not-by-read-only-verbs.adr.md) | Supervision cost is measured by a journal the host writes, not by the engine's read-only verbs | proposed |
| [0088](0088-attribute-supervision-spend-by-marginal-tokens-beside-turn-totals.adr.md) | Attribute a supervising session's spend to runs by marginal tokens, shown beside turn totals | proposed |
| [0089](0089-supervision-is-a-promotion-and-improvement-measure.adr.md) | Supervision by every decider is a promotion criterion and an improvement signal | proposed |
| [0090](0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) | The first release is simple, trusted workflows on one machine, with their creation and full observability | proposed |
| [0091](0091-first-release-ships-the-claude-executor-only.adr.md) | The first release ships the Claude Code executor only; the other three follow by release | proposed |
| [0095](0095-a-model-free-tick-behind-os-agnostic-triggers.adr.md) | A model-free, OS-agnostic tick holds every schedule rule; a portable engine loop calls it, OS and other schedulers are optional adapters | proposed |
| [0096](0096-exact-formats-first-and-an-optional-word-grammar-echoed-back.adr.md) | Exact date formats are the deterministic path; an optional word grammar sits on top; both are model-free and echoed back | proposed |
| [0097](0097-schedules-keep-an-iana-zone-and-rfc-5545-daylight-saving-rules.adr.md) | Schedules keep an IANA zone; calendar rules follow wall time, intervals elapsed time, by RFC 5545 | proposed |
| [0098](0098-missed-slots-catch-up-latest-and-a-live-run-skips-the-next.adr.md) | Missed slots catch up the latest one; a live or paused run skips the next slot; a slot runs at most once | proposed |
| [0099](0099-a-scheduled-fire-is-an-attested-caller-with-a-capped-unattended-spend.adr.md) | A scheduled fire is an attested `scheduler` caller; unattended spend needs a cap; pauses stay with a person | proposed |
| [0100](0100-the-engine-owns-the-run-worktree-executor-worktrees-are-not-used.adr.md) | The engine owns the run's worktree; executor-native worktrees are not used | proposed |
| [0101](0101-one-workspace-setting-with-an-auto-default.adr.md) | One workspace setting, `run.workspace`, with an `auto` default resolved from the target and the workflow | proposed |
| [0102](0102-worktrees-beside-the-repository-with-derived-ref-safe-names.adr.md) | Worktrees live beside the repository by default, with names derived ref-safe from the thread id | proposed |
| [0103](0103-worktree-removal-is-opt-in-clean-only-and-keeps-the-branch.adr.md) | Worktree removal is opt-in, only of clean worktrees, and never deletes the branch | proposed |
| [0104](0104-a-new-worktree-starts-from-the-main-checkouts-head.adr.md) | A new run worktree starts from the main checkout's HEAD unless the run names another base | proposed |
| [0105](0105-a-workflow-package-is-one-claude-plugin-with-a-python-part-and-a-docs-set.adr.md) | A workflow package is one Claude plugin with a Python part and a docs set | proposed |
| [0106](0106-declare-workflows-with-typed-python-builders-and-text-in-files.adr.md) | Declare workflows with typed Python builders; keep text in files | proposed |
| [0107](0107-the-good-outcome-is-one-data-file-of-final-and-intermediate-outcomes.adr.md) | The good outcome is one data file of final and intermediate outcomes, each criterion classed by its verifier | proposed |
| [0108](0108-a-run-is-measured-at-a-final-outcome-gate.adr.md) | A run is measured at a mandatory final outcome gate; unverified criteria are shown, never passed | proposed |
| [0109](0109-author-backwards-from-the-outcome-preferring-existing-verifications.adr.md) | Author backwards from the good outcome, from any of three entry paths, preferring verifications the person already has | proposed |
| [0110](0110-check-an-authored-workflow-model-free-then-by-one-consented-trial.adr.md) | Check an authored workflow model-free first, then by one consented, capped trial graded by the person | proposed |
| [0111](0111-outcome-revisions-are-grader-changes-and-verifiers-climb-a-ladder.adr.md) | Outcome revisions are grader-side changes; weakening is a person's act and verifiers climb a measured ladder | proposed |
| [0112](0112-plugin-content-reaches-each-executor-by-a-declared-route-or-is-refused.adr.md) | Plugin content reaches each executor by a declared route or the step is refused; workflow plugins ship no hooks, MCP servers or binaries | proposed |
| [0113](0113-the-workflow-docs-set-is-provisional-until-temperspec-owns-it.adr.md) | Every workflow package carries its own docs set, with provisional rules until temperspec owns them | proposed |
| [0114](0114-judged-criteria-carry-a-scale-and-authoring-guides-until-criteria-are-clear.adr.md) | Judged criteria carry a scoring scale with seeds; authoring guides the person until every criterion is clear | proposed |
| [0115](0115-the-engine-is-a-src-layout-python-package-inside-its-plugin.adr.md) | The engine is a src-layout Python package inside its plugin, with pytest, ruff and mypy | proposed |
| [0116](0116-session-logs-are-read-model-free-first-and-by-a-model-only-on-a-plan.adr.md) | Session logs are read model-free first, and by a model only on a plan | proposed |
| [0117](0117-review-depth-follows-the-improvement-mode-and-named-signals.adr.md) | Review depth follows the improvement mode and named signals | proposed |
| [0118](0118-the-reviewer-is-tool-less-and-reads-a-condensed-datamarked-view.adr.md) | The reviewer is tool-less and reads a condensed, scrubbed, datamarked view | proposed |
| [0119](0119-review-observations-are-candidates-corroborated-before-they-file.adr.md) | Review observations are candidates, corroborated before they file | proposed |
| [0120](0120-a-workflow-plugin-name-is-the-workflow-name-plus-tgraph.adr.md) | A workflow plugin's name is the workflow name plus `-tgraph` | accepted |
| [0129](0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md) | The engine names no workflow, and takes a workflow's request as a general capability | accepted |
