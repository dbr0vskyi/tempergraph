# R-110 Reading session logs for self-improvement

## Problem statement


## Sources consulted

| Id | Source | Type | Where |
|---|---|---|---|
| S8 | This design: SIL, SEC-B8 to SEC-B11, PRP-B23, LOS, EVT, IMD, R-030, R-045 | Design set | [specs/](../specs/00-overview.spec.md) |
| S9 | Zhang et al., *Which Agent Causes Task Failures and When? On Automated Failure Attribution of LLM Multi-Agent Systems* (ICML 2025) | Paper | [arXiv 2505.00212](https://arxiv.org/abs/2505.00212) |
| S10 | Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (NeurIPS 2025) | Paper | [arXiv 2503.13657](https://arxiv.org/abs/2503.13657) |
| S11 | LangSmith Insights Agent documentation | Vendor docs | [docs.langchain.com/langsmith/insights](https://docs.langchain.com/langsmith/insights) |
| S12 | Transluce, *Analyzing long agent transcripts (Docent)* | Practitioner write-up | [LessWrong cross-post](https://www.lesswrong.com/posts/Mj276hooL3Mncs3uv/analyzing-long-agent-transcripts-docent) |
| S13 | Hines et al., *Defending Against Indirect Prompt Injection Attacks With Spotlighting* | Paper | [arXiv 2403.14720](https://arxiv.org/abs/2403.14720) |
| S14 | MSRC, *How Microsoft defends against indirect prompt injection attacks* (July 2025) | Vendor blog | [microsoft.com/msrc/blog](https://www.microsoft.com/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks) |
| S15 | Grace et al., *Demystifying evals for AI agents* (Anthropic Engineering) | Practitioner guide | as cited in [R-045](R-045-evaluating-llm-judges-public-practice.rsrch.md) S4 |
| S16 | Claude Code `/insights` command, third-party write-ups | Search results only; the article fetched returned a bot challenge | e.g. [SSW rule](https://www.ssw.com.au/rules/use-claude-insights) (not read) |

## Key findings

### Principles and observations that bear on reading sessions

**B1 A separate transcript pipeline is the wrong place, not the wrong input.** A standalone pipeline that reads session transcripts from a session-end hook would duplicate what the engine already has: durable runs, a run log and workflows as data. The objection is architectural: improvement belongs inside the engine as a workflow, beside the run it reads. Nothing in it argues against reading session content as such. `inferred`.

**B2 Session content is kept local and linked, and only numbers are derived from it.** The run log keeps the session id "so the full transcript can be found"; raw step output "stays local and is never published". Session metrics (turns, peak context, turns above 200k, tokens before the first write, files read again) "come from the stream's own turns, numbers only". The time profile keeps "names, program words and numbers, never a command, a path or an output". Principle: "Anything shared holds names, counts, words and hashes. Local stores hold raw text and are not published." `confirmed` (S2).

**B3 The gate judge never sees the producer's transcript.** A judge session "is never a resume of the step's session and never sees the producer's transcript" (S3, 5.4); cross-executor judging keeps the same rule ([ADR-0013](../adr/0013-cross-executor-judging.adr.md)). The reason is independence: a judge that reads how the step argued its way to an answer grades the argument, not the work. A session reviewer is therefore a different role from a gate judge, and nothing it writes may reach a gate judge's view. `confirmed` (S3, S8).

**B4 Most of what reading a stream by hand shows is numeric.** A fresh retry starts with a fraction of the context the attempt before it ended with, spends a large share of its cost before its first write and rereads files the attempt before it read. Refused tool calls cluster on a few habits: the shell used to read or list files though file tools are declared, `cd` before git, a path outside the worktree. Shell calls slow down on a loaded host; a long session spends much of its cost at high context; a judge can make many tool calls on a step that has already passed. Each of these is a count that a fixed rule, a cause code or a lever can use, so most of the value of reading a session can be had by code that counts, if the counting rules are written down. `inferred`.

**B5 Reading can be signal-driven and partial, and a loop detector should only record.** A timed-out attempt can be sorted into hung, slow host or model-silent from its time profile and its session transcript, before anything more is built. An executor-neutral event stream can feed a per-attempt events log (private, unscrubbed, best-effort) and a loop detector that only records a signal (the same tool, target and error K times, or no worktree change for N minutes while tokens are spent) and never stops a run until it is calibrated on real runs. That is the owner's stable-mode idea: read the part of the session a signal points at. `inferred`.

**B6 Where code has the facts, code decides; the judge checks the result.** The friction judge carried one 2,002-character criterion of about fifteen counting rules the analyzer already computed; the plan moves those rules into code and shrinks the criterion (S5, calibration). "Never classify from text" holds with one exception ("Request timed out") (S4). Classification of causes stays on names and numbers; a model's reading of text can propose, not classify. `confirmed` (S4, S5).

**B7 Model confidence did not carry signal; what the judge saw does.** Of 694 judge confidence values none was below 0.60; area under the curve 0.45 for the friction floor. The planned anchored scale defines confidence by what the judge saw ("a deciding status rests partly on a source that was cut off or unopened") (S5). A judge session's own tool calls are the ground truth for that anchor: which files it opened, whether it opened any. `confirmed` for the numbers (S5); the use of the trace for the anchor is `inferred`.

**B8 Judges are graded by a person reading the judge's transcript.** Calibration's scoring step is "a person runs the judge over each output (a live development-mode run, then the judge's transcript and the gate's judgement)" (S6). The outcome judge reads only the evidence file with each step's last output cut to 2,000 characters, so 7 of 18 requirements of one accepted run were "not shown" though they were facts in git; the fix is mechanical git facts, not more text (S5). `confirmed`.

**B9 The loop cannot say why retries repeat.** temperspec's planned list: "Today two reports say 'no cause code' for retry bursts ... The loop sees the retries and cannot say why, so it cannot propose a fix" (S7, 14 G). This design added `judge_blocked:<criterion id>` ([SIL-B12 to SIL-B16](../specs/16-self-improvement.spec.md)), which says which criterion blocked; it still cannot say what the step did wrong each time, or whether attempt 2 repeated attempt 1's approach. `confirmed` (S7, S8).

**B10 Flagging is not selecting.** The friction lens flagged 89 of 90 delivery runs; of 137 filing records, 22 opened an issue (S1). Reading every flagged run's sessions would read almost every run. Selection has to come from specific signals and from what is already explained. `confirmed` (S1).

**B11 Dev and stable mode already split the loop by trigger.** Dev mode judges at every final exit; stable mode judges only when a trigger fires, under a $50 daily cap; the stable friction triggers include "a new version in its first five runs" (S1). The owner's split maps onto this existing axis. `confirmed` (S1, S8).

### What this design records today

**D1** Every session keeps `raw.jsonl` (verbatim stream) and `activity.jsonl` (normalized events, tool input summaries scrubbed and clipped to 200 characters, resource samples), retained 30 days, capture level lowerable per item ([LOS-B16, LOS-B17](../specs/33-local-observability-store.spec.md), [EVT-B17, EVT-B18, EVT-B7, EVT-B19, EVT-B21](../specs/30-run-events.spec.md)). `confirmed` (S8).

**D2** The loop reads `run.jsonl`, the ledger and `findings.json`; the friction judge gets finding metadata, per-unit record counts and blocker ids, with no tools ([SIL-B17, SIL-B18](../specs/16-self-improvement.spec.md)). The evidence file is clipped at 32 KB and only the recorder names it (source test). The proposer is specified to read its runs' local evidence ([PRP-B23](../specs/40-improvement-proposals.spec.md)). No component reads `raw.jsonl` or `activity.jsonl` for improvement. `confirmed` (S8 and the code in `improve/`).

**D3** The audit's tool-surface layer already compares grant, need and use per step and judge session ([TSA](../specs/57-tool-surface-audit.spec.md)), and OBS keeps session metrics. Several digest facts below exist in pieces. `confirmed` (S8).

### Public practice

**P1 Read the transcripts.** Anthropic's eval guide: a case nobody passes is usually broken, and graders must be checked by reading failures ([R-045 F13](R-045-evaluating-llm-judges-public-practice.rsrch.md)). `supported` (S15).

**P2 Reflective optimizers read traces.** GEPA proposes targeted prompt edits from execution traces and evaluator feedback in natural language ([R-030 F3](R-030-self-improving-agent-systems.rsrch.md)). `supported`.

**P3 Model attribution of a failure to a step is unreliable.** On the Who&When dataset (failure logs from 127 multi-agent systems, annotated with the responsible agent and decisive step), the best automated method found the responsible agent 53.5% of the time and the decisive step 14.2%; some methods were below random, and reasoning models "fail to achieve practical usability". `supported` (S9). For tempergraph: a model reading a session can suggest what went wrong, but a claim that "turn 17 is where it failed" must be checked against the record, not trusted.

**P4 A fixed failure taxonomy is feasible and agrees across people.** MAST: 1,600+ annotated traces across 7 frameworks; 14 failure modes in 3 categories (system design issues, inter-agent misalignment, task verification), built from 150 traces with inter-annotator kappa 0.88; an LLM-as-judge pipeline agreed highly with human annotation. `supported` (S10). For tempergraph: the reviewer should pick from a fixed category catalog, as the friction lens picks cause codes.

**P5 Summarize each trace first, then cluster; sample.** LangSmith's Insights Agent summarizes each trace with one model and clusters the summaries with another into a hierarchy; it analyzes a sample of at most 1,000 traces from a time range; 1,000 threads cost about $1 to $2 with OpenAI models and $3 to $4 with Anthropic models, and a report can take 30 minutes. `supported` (S11). The per-trace cost of summary-level reading is small; the cost of deep reading is not stated.

**P6 Transcripts show environment faults that records hide.** Docent: a single agent transcript can hold hundreds of thousands of tokens; reading them found missing packages in an environment, and adding them raised one model's solve rate from 68.6% to 78%. `supported` (S12).

**P7 Transcript content is untrusted input; layer the defence.** Spotlighting (delimiting, datamarking, encoding untrusted text) cut indirect prompt-injection success from above 50% to below 2% on GPT-family models with little effect on the task (S13). Microsoft's defence layers prevention (hardened prompts, spotlighting), detection (a classifier) and impact limits (least privilege, deterministic blocking of exfiltration, consent for risky actions), and "does not rely on our ability to block all prompt injections" (S14). `supported`. A session log holds web pages, file contents, tool output and the request: all of it can carry instructions aimed at whatever model reads it next.

**P8 Claude Code ships a local session-history report.** Write-ups describe an `/insights` command that reads a person's recent local sessions and reports where they ran into trouble with suggestions for instructions, skills and hooks. `uncertain` (S16, titles only; the one article fetched returned a bot challenge). Not relied on.

## Analysis: where reading sessions adds signal

Each case is sorted by what can see it. **Records** means today's run log, ledger and findings. **Digest** means a model-free pass over the session's `activity.jsonl` and `raw.jsonl` that counts, names and compares (ADR-0116). **Review** means a model reading a scrubbed, condensed view of the session.

| Case | Records | Digest | Review | Evidence |
|---|---|---|---|---|
| Tool thrash: the same tool, target and error repeated | no | **yes** (K repeats of (tool, target hash, error class)) | adds why | B5 |
| Shell used to read, search or list though file tools are declared; `cd` before git; a path outside the workspace | refusals only | **yes**, from input summaries and capabilities | no | B4 |
| Context bloat: peak context, turns above 200k, tokens before the first write, files read again | partly (OBS session metrics) | **yes** | adds why | B4 |
| Wasted turns: long read-only stretch, no workspace change for N minutes while tokens are spent | no | **yes** | adds why | B5 |
| A declared skill, subagent or tool never used; an undeclared one used | partly (TSA) | **yes** | adds whether it should have been | D3 |
| Subagents dominate the cost, or are started many times for one question | no | **yes** (subagent count and token share) | adds whether delegation was apt | B4 |
| A timeout sorted into hung, slow host or model-silent | partly (time profile) | **yes** (open tool at the end, tool share, last event age) | no | B5 |
| A judge passed criteria without opening anything, or opened none of the changed files | no | **yes** (judge reads ∩ changed paths) | adds whether its reasoning held | B7 |
| A judge ran far more turns or tool calls than its peers | partly | **yes** | adds why | B4 |
| The step misread the prompt: did something other than asked | no | no | **yes** | B9, P2 |
| An instruction or lesson in the prompt was not followed | no | weak (a named command never run) | **yes** | P2 |
| A subagent or agent used, but not as intended (wrong question, wrong type, result ignored) | no | weak | **yes** | P4 |
| A retry repeated the previous attempt's dead end despite the judge's feedback | criterion ids only | partly (same files and commands as attempt n−1) | **yes** | B9 |
| The judge trusted the step's own report instead of the work | no | partly (no reads before the verdict) | **yes** | B3, B8 |
| The judge's reasoning was shallow on a criterion it passed | no | no | **yes** | B8 |
| Environment faults visible only in tool output (missing package, permission, network) | partly (infra causes) | partly (error classes by tool) | **yes** for new kinds | P6, B4 |
| A request that was ambiguous or out of scope | outcome lens | no | partly (adds where the step guessed) | S1 |

Three conclusions from the table. First, about half the cases need no model at all: a digest finds them at near-zero cost and they become cause codes like any other (B4, B6). Second, the cases only a model can see are the ones the owner named: prompts and agents not working as intended, dead ends, and judges that do not look. Third, a model's reading is a suggestion about where and why, not an attribution (P3), so its output has to be checkable against the digest and the record.

### Where reading does not help, or costs too much

| Case | Why not |
|---|---|
| A clean first-pass run in stable mode with no signal | Low yield; the outcome lens's 1-in-20 audit already samples clean runs (S1) |
| A cause already classified as infra, host or executor drift | The digest and the record already say it; nothing to propose on the workflow (SIL-B11) |
| Grading whether the output is good | The gates and the outcome gate own that; a reviewer that re-grades results becomes a second, uncalibrated judge (B3) |
| A cause whose cluster already holds several corroborated observations for this version | Diminishing returns: reading more of the same explains nothing new until the version changes (B10) |
| A session past retention, pruned, or captured with `observe.raw = off` | Nothing to read; the digest falls back to the activity journal or records `not_captured` (D1) |
| Changing a verdict or a route of the run that was read | Never: the loop measures after the fact, and OVR-B16 holds |

### Cost of the reading itself

- A digest is a linear pass over files already on disk: no model, milliseconds to seconds per session. It can run on every exit, both modes.
- A review's input is the condensed view, not the raw stream. Tool outputs dominate raw size (B4: 87.6 KB in one plan write; P6: hundreds of thousands of tokens per transcript); the condensed view keeps tool names, input summaries, status, sizes, error tails and clipped assistant text, which is a fraction of the raw stream. The ratio is not measured; until it is, the design caps the input in tokens, not in turns.
- Public summary-level cost is a few dollars per thousand traces (P5); deep reading by a step and judge on a mid-tier alias has no measured cost. The design therefore caps review spend per review, per run (as a share of the run's own cost) and per day, all as parameters with provenance `default_no_data` ([IMD-B23](../specs/43-improvement-data.spec.md)).
- The cheapest model is a poor fit for reading across a long session, so the reviewer defaults to the mid-tier alias, like the loop's other judges.

### Privacy and security

- **Local only.** Session logs, the condensed view and the reviewer's text are evidence-class: local, owner-only, never published, never sent to a sink (B2, [SEC-B8 to SEC-B11](../specs/14-security.spec.md), IMD-B10). What crosses the publish boundary is category codes, unit names, turn counts and fixed remedy words.
- **No new provider.** The reviewer sends session content to a model. In release 1 that is the same `claude` executor that produced the session, so the content goes nowhere it has not been. With more executors, a review runs on an executor of the same provider as the session it reads, unless the operator allows another.
- **Scrubbed and condensed.** The view passes the pattern scrubber; tool outputs are elided except clipped error tails; the request text is included only through the evidence file's clipped copy.
- **Prompt injection.** Everything in a session log is untrusted (P7). The reviewer gets no tools, so an injected instruction has nothing to act with; the untrusted text is datamarked and fenced with a per-review random boundary; the output is a fixed schema of enum categories and turn numbers, and its free text never reaches filing, a gate judge or a step prompt. The engine checks each citation against the digest (ADR-0118). This follows S14's layering: the design does not rely on the model resisting the injection.
- **Independence.** A reviewer is not a gate judge, never runs inside the run it reads, and none of its output enters any judge's view (B3).

## Conclusions

1. A separate transcript pipeline is the wrong place, but transcript reading is not the wrong input; partial, signal-driven reading for timeouts and a record-only loop detector fit the engine, and most levers that reading a stream by hand finds are counts (B1, B4, B5).
2. About half the useful observations are counts and comparisons that code can take from `activity.jsonl` and `raw.jsonl` on every exit, model-free, with names and numbers only (B2, B4, B6).
3. A model's reading adds what the owner asked for: whether prompts, lessons, skills and subagents work as intended, whether retries repeat dead ends, and whether judges look before they pass (B9, P2).
4. A model's attribution of a failure to a step is wrong more often than right (P3), so review output must be categories from a fixed catalog with turn citations the engine verifies, and it is a candidate until corroborated (P3, P4, B6).
5. Reading depth should follow the improvement mode the design already has: dev mode reads every session of every final exit within a budget; stable mode reads only the sessions and slices a named signal points at; a new version reads its changed units for its first runs (B5, B11).
6. Session content is untrusted input to the reviewing model; the defence is layered and does not rely on the model resisting it (P7).
7. Summarize-first and sampling are the public pattern for scale (P5); a cap per review, per run and per day bounds the cost.

## Open questions

| Question | Owner |
|---|---|
| What is the condensed view's size against `raw.jsonl` on real `claude` sessions? Needed to set `review.max_input_tokens`. | Engine owner, at the first live dev-mode review |
| Does the reviewer's category agree with a person's reading often enough to file from it? A small gold set of reviewed sessions, graded like a judge ([JCL](../specs/50-judge-calibration.spec.md)), would answer it. | Owner |
| Do the terms of use of every planned executor allow sending a session's content to a second session of the same provider? Assumed yes for `claude`, since the content came from it. | Owner |
| Does Claude Code's `/insights` (P8) cover part of this for interactive sessions, and could its format be reused? Not verified. | Engine owner |
