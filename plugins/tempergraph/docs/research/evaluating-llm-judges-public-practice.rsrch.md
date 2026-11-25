# Evaluating LLM judges: public practice

## Problem statement

Every gate, every quality figure and the whole self-improvement loop of tempergraph rest on LLM judges, and no one has yet measured how often those judges are wrong. Before the design fixes how judges are graded ([research `eval-and-judge-gap-analysis`](eval-and-judge-gap-analysis.rsrch.md)), this note collects what public work says about measuring an LLM judge, which errors judges are known to make, and how agent evals are built. It answers: which figures describe a judge, how many labels they need, which biases must be tested for, and how evals of steps and whole workflows are usually structured.

## Sources consulted

| # | Source | Type | Where | Read |
|---|---|---|---|---|
| S1 | Lee, Zeng, Jeong, Sohn, Lee, *How to Correctly Report LLM-as-a-Judge Evaluations* (2025) | Paper, statistics | arXiv 2511.21140 | Read 2026-11-19 |
| S2 | Collot et al. (Meta), *Balanced Accuracy: The Right Metric for Evaluating LLM Judges* (2025) | Position paper with simulation | arXiv 2512.08121 | Read 2026-11-19 |
| S3 | Jain, Ahmed, Sahai, Leong, *Beyond Consensus: Mitigating the Agreeableness Bias in LLM Judge Evaluations* (Oct 2025) | Paper, empirical | arXiv 2510.11822 | Read 2026-11-19 (later sections from a summary) |
| S4 | Grace, Hadfield, Olivares, De Jonghe, *Demystifying evals for AI agents* (Anthropic Engineering, Jan 2026) | Practitioner guide | anthropic.com/engineering/demystifying-evals-for-ai-agents | Read 2026-11-19 |
| S5 | Shankar, Zamfirescu-Pereira, Hartmann, Parameswaran, Arawjo, *Who Validates the Validators?* (UIST 2024) | Paper, user study | arXiv 2404.12272 | Abstract read 2026-11-19 |
| S6 | Panickssery, Bowman, Feng, *LLM Evaluators Recognize and Favor Their Own Generations* (NeurIPS 2024) | Paper, empirical | arXiv 2404.13076 | Abstract read 2026-11-19 |
| S7 | Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (NeurIPS 2023) | Paper, empirical | arXiv 2306.05685 | Cited from prior reading, not re-read |
| S8 | Verga et al., *Replacing Judges with Juries* (2024) | Paper, empirical | arXiv 2404.18796 | Cited from prior reading, not re-read |
| S9 | Yao et al., *τ-bench* (2024), the pass^k metric | Paper, benchmark | arXiv 2406.12045 | Cited from prior reading, not re-read |
| S10 | Wilson score interval for a binomial proportion | Standard statistics | any statistics text | — |

Sources S7 to S9 were not re-fetched for this note, so findings that rest on them alone are marked `supported` at most, and no control in the specs rests on them alone.

## Key findings

### A. What figure describes a judge

**F1 Report the two error rates apart, not agreement.** A judge that grades pass or fail has two error rates: it can pass bad work (a false pass) and fail good work (a false fail). One overall agreement or accuracy figure hides which one a judge makes, and at low prevalence of bad work it picks the wrong judge. In S2's worked case (8.3% bad), accuracy, F1 and macro-F1 all preferred the judge with the lower balanced accuracy; in 100,000 simulated selections balanced accuracy picked the best judge 75.2% of the time against 67.5% for accuracy. S3 recommends reporting the true-positive and true-negative rates separately for the same reason. `confirmed` (S2, S3)

**F2 Judges are agreeable: they rarely fail anything.** On 366 buggy programs graded by 14 LLMs, S3 found true-positive rates above 96% but true-negative rates below 25%: judges recognised correct work and missed most incorrect work, and every judge overestimated the precision of the graded generator (by up to 17.6 points). A judge set must therefore contain known-bad cases in number, and the false-pass rate is the figure to bound first. `supported` (S3)

**F3 Agreement between two judges is not correctness.** Two judges can agree on the same wrong answer, especially two of one family (F6). S3 found majority-vote ensembles cut the worst error only from 17.6% to 14.8%, while a small human-labelled calibration set cut it to 1.2%. Judge-against-judge agreement measures consistency; only labels from people (or from facts) measure correctness. `supported` (S3; consistent with S4's "calibrate model graders against human graders")

**F4 A raw judge-graded rate is biased, and the bias can be corrected.** If a judge's pass rate on a population is p̂, its true-negative rate q0 and its true-positive rate q1, the prevalence estimate θ̂ = (p̂ + q0 − 1)/(q0 + q1 − 1) (the Rogan-Gladen estimator) removes the bias; S1 gives a confidence interval that includes the uncertainty of q0 and q1 themselves, with near-nominal 95% coverage where the naive interval had almost none. With q0 = 0.7 and q1 = 0.9 the raw rate overstates the true rate whenever it is below 0.75. `supported` (S1)

**F5 Label counts per class matter more than total judgements.** S1: for an interval narrower than 0.1 around a 0.3 rate, roughly 200 labels per class were needed; labels should be split between the two classes deliberately, not in their natural ratio. S2: returns plateau beyond 1,000 to 2,000 golden labels. A Wilson interval (S10) at n = 20 known-bad cases with one miss gives a 95% lower bound of about 0.76 on the catch rate; at two misses it falls to about 0.70. Small sets bound a judge only loosely, so a bar must be stated on a lower bound, not on a point value. `confirmed` (S1, S2, S10)

### B. Known judge biases

**F6 Self-preference.** A model scores its own outputs higher than people judge them, and the effect grows with its ability to recognise its own text (S6). `supported` (S6, S7)

**F7 Position, verbosity and persuasion.** S7 documented position bias (in pairwise grading), verbosity bias (longer answers preferred) and self-enhancement. tempergraph grades one subject against criteria, so position between two answers does not arise, but the same mechanisms appear as order of criteria, length of the step's account and confident wording in the step's claims. tempergraph's "claims to verify, not facts" label ([JDG](../specs/judge-and-verdict.spec.md)) is a mitigation whose effect is not measured. `supported` (S7; mapping to tempergraph `inferred`)

**F8 Criteria drift.** People define their criteria by grading outputs, so a criterion and its labels change together (S5). A labelled case is tied to the criterion text it was labelled against; when the text changes, the label may no longer hold. `supported` (S5)

**F9 Panels of different models reduce single-family bias.** A panel of smaller models from several families can match or beat a single large judge at lower cost and with less intra-model bias (S8). A panel still multiplies the judge sessions per gate. `supported` (S8)

### C. How agent evals are built

**F10 Three grader kinds, in a fixed order of trust.** S4 names code graders (fast, objective, brittle to valid variations), model graders (flexible, non-deterministic, "require calibration with human graders") and human graders (the gold standard, used to calibrate the others). It recommends an explicit "unknown" exit for a model grader, and one isolated judge per dimension. tempergraph already has all three as check, judge and person, with UNVERIFIABLE as the unknown exit. `supported` (S4; tempergraph's side from [JDG](../specs/judge-and-verdict.spec.md))

**F11 Measure consistency with repeated trials: pass@k and pass^k.** pass@k is the chance that at least one of k trials succeeds; pass^k that all k succeed (S9, S4). A 75% per-trial rate gives pass^3 ≈ 42% (S4). For a gate that must behave the same on every run, the useful figure is pass^k for the producer and the flip rate for the judge (the share of criteria whose status differs between repeated judgements of one subject). `confirmed` (S4, S9)

**F12 Capability and regression suites differ in purpose.** A regression suite should pass at nearly 100% and guards against breakage; a capability suite starts low and measures progress; a capability case that saturates graduates into the regression suite. An eval at 100% "provides no signal for improvement" (S4). `supported` (S4)

**F13 Read the transcripts; a case nobody passes is usually broken.** A 0% pass rate over many trials most often signals a broken task, not a weak model; graders must be checked for fairness by reading failures (S4). `supported` (S4)

**F14 Keep tuning cases apart from scoring cases.** When a judge prompt is edited until it agrees with a labelled set, that set no longer measures it. Public practice keeps a held-out split for the score (S5 aligns evaluators on a graded subset; the paired-trial work of the parallel self-improvement design scores on out-of-sample pairs only). `inferred` (S5, general practice)

## Conclusions

1. A judge is described by two rates measured on labelled cases, the **catch rate** (share of known-bad findings it flags) and the **clean-pass rate** (share of known-good findings it passes), each stated with a lower confidence bound, plus a **flip rate** from repeated judging. Overall agreement and judge-to-judge agreement are not substitutes.
2. Judges fail by passing bad work far more than by failing good work, so a calibration set needs many known-bad cases and the bar on the catch rate is the first one to meet.
3. Labels come from people or facts. A second judge supplies consistency figures and candidates for labelling, not ground truth.
4. Small labelled sets are enough to start only if the bar is stated on a lower bound and grows tighter as cases accumulate.
5. A judge-graded rate shown in a report should be corrected with the judge's measured error rates, or flagged as uncorrected.
6. Self-preference, verbosity and persuasion are known biases that can be tested cheaply with paired variants of the same case.
7. Labels are bound to the criterion text they were made against, and cases used to tune a brief cannot also score it.
8. Step and workflow evals should grade with code first, a calibrated judge second and a person last, and measure consistency with pass^k over repeated trials.

## Open questions

| Question | Owner |
|---|---|
| Do the agreeableness figures of S3 (code correctness, single-turn) carry over to tool-using judges that read a workspace? Only a live calibration run of a tempergraph gate can say. | First live scoring run ([JCL](../specs/judge-calibration.spec.md)) |
| Is a panel (F9) cheaper than a stronger single judge for the gates that fail the bar? Deferred until per-gate bars exist. | Owner, after first scores |
