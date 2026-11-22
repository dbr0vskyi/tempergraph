"""The audit rule catalog (ARC-B6 to ARC-B16, PRA-B7 to PRA-B10): engine data, versioned with the engine.

Every rule carries its layer, R-050 family, cause code, default severity and confidence, owner, the
minimum sample of a history rule, and a fixed remedy (ARC-AC1). Thresholds are named parameters with
their default and the R-050 finding they come from (ARC-AC3). Rules owned by another component are only
rendered; the audit calls that component (ARC-AC4, ADR-0054).

`built` names the release that builds the rule. Release 1 builds the `definition` and `host` layers and
the prompt audit (ADR-0090, plan item I-62); the `history` layer is release 2 (X2-9) and the tool-surface
audit of TSA is release 2 (X2-10). A rule not built here is listed as skipped, never as passed (AUD-B1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Layer = Literal["definition", "host", "history"]
Severity = Literal["error", "warning", "info"]
Confidence = Literal["high", "medium", "low"]
LAYERS: tuple[Layer, ...] = ("definition", "host", "history")
SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}
CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
FAMILY_RANK = {f"C{i}": i for i in range(1, 9)}


@dataclass(frozen=True, kw_only=True)
class Param:
    name: str
    default: float
    source: str  # the R-050 finding (or research note) that motivated the default


PARAMS: dict[str, Param] = {p.name: p for p in (
    Param(name="oversized_blockers", default=8, source="R-050 F1.2"),
    Param(name="oversized_file_artifacts", default=3, source="R-050 F1.2"),
    Param(name="oversized_template_chars", default=24_000, source="R-050 F1.2"),
    Param(name="engine_step_timeout_s", default=600, source="R-050 F3.4 (the engine default)"),
    Param(name="infra_tries", default=3, source="BUD default infra tries"),
    Param(name="no_idle_above_s", default=1_800, source="R-050 F3.5"),
    Param(name="unit_hold_h", default=4, source="R-050 F3.5 (6 h on one unit)"),
    Param(name="workflow_hold_h", default=12, source="R-050 F3.5"),
    Param(name="approval_share", default=0.5, source="R-050 F5.3"),
    Param(name="slow_login_shell_s", default=15, source="R-050 F2.5"),
    Param(name="slow_login_shell_ratio", default=5, source="R-050 F2.5"),
    Param(name="slow_login_shell_floor_s", default=1, source="release 1 default: below it the ratio is noise"),
    Param(name="template_chars", default=32_000, source="earlier runs (72 KB to 25 KB)"),
    Param(name="skill_chars", default=40_000, source="earlier runs"),
    Param(name="cell_chars", default=2_000, source="earlier runs"),
    Param(name="probe_budget_s", default=30, source="AUD-B11, AUD-B6, AUD-B9"),
)}


@dataclass(frozen=True, kw_only=True)
class Rule:
    id: str
    layer: Layer
    family: str
    cause: str
    severity: Severity | Literal["per owner"]
    confidence: Confidence | Literal["per owner"]
    owner: str = "audit"
    min_n: int | None = None
    remedy: str = ""
    built: int = 1  # the release that builds it
    spec: str = "ARC"

    @property
    def rank(self) -> tuple[int, int]:
        return FAMILY_RANK.get(self.family, 9), _ORDER.get(self.id, 999)


def _r(id: str, layer: Layer, family: str, sev: str, cause: str, remedy: str, *, owner: str = "audit",
       min_n: int | None = None, built: int | None = None, spec: str = "ARC") -> Rule:
    s, _, c = sev.partition("/")
    if layer == "history" and min_n is None:
        min_n = 1  # ARC-AC1: every history rule has a minimum sample; "any run" where ARC names none
    return Rule(id=id, layer=layer, family=family, cause=cause, severity=s.strip(),  # type: ignore[arg-type]
                confidence=(c.strip() or s.strip()), owner=owner, min_n=min_n,  # type: ignore[arg-type]
                remedy=remedy, built=built if built is not None else (2 if layer == "history" else 1), spec=spec)


OWN = "per owner"

RULES: tuple[Rule, ...] = (
    # C1 gate send-back loops (ARC-B8, ARC-B9)
    _r("oversized-step", "definition", "C1", "warning / medium", "oversized_step",
       "Split the step into passes (design, then tables); give each pass its own gate (R-050 F1.2: yield 29% to 62%)"),
    _r("no-change-blocker-retries", "definition", "C1", "warning / high", "no_change_retry",
       "Keep the default `no_change_policy: escalate`: a retry cannot fix what the step's output cannot change"),
    _r("unverified-blocker", "definition", "C1", "warning / high", "unverifiable_blocker",
       "Give the judge a view of that system, move the fact to a check, or make the criterion a warning"),
    _r("single-criterion-gate-judge-only", "definition", "C1", "info / low", "prefer_check",
       "Make the criterion a check: a file's existence, a command's result or a git fact is computed, not judged"),
    _r("loop-driver-criterion", "history", "C1", "error / high", "retry_burst",
       "Split the step, reword the criterion so a second visit can meet it, or move it to a check", min_n=5),
    _r("low-first-pass", "history", "C1", "warning / high", "low_first_pass",
       "Read `loop-driver-criterion` for the gate; consider a split", min_n=5),
    _r("no-change-retried", "history", "C1", "warning / high", "no_change_retry", "As `no-change-blocker-retries`"),
    _r("repeated-check-evidence", "history", "C1", "warning / medium", "retry_cannot_fix",
       "Mark the failure environmental in the check, or fix the environment"),
    _r("missing-field-rendered", "history", "C1", "error / high", "missing_input",
       "Supply the input or make the template field optional"),
    _r("judge-not-ready", "definition", "C1", OWN, "judge_not_ready", "owner: LIF readiness report",
       owner="readiness"),
    _r("brief-rule-branching", "definition", "C1", OWN, "", "owner: WFM-B12", owner="validate"),
    _r("criterion-without-method", "definition", "C1", OWN, "", "owner: WFM-B12", owner="validate"),
    # C2 environment (ARC-B10)
    _r("check-program-missing", "host", "C2", "error / high", "environment_missing",
       "Install the program, or change the prefix or resolver; the check would run nothing (F2.4)"),
    _r("interpreter-cannot-import", "host", "C2", "error / high", "environment_missing",
       "Install the runner in that environment (F2.2)"),
    _r("toolchain-not-covered", "host", "C2", "warning / medium", "toolchain_not_covered",
       "Add a `command_resolver` or declare the repository's commands (F2.4)"),
    _r("worktree-env-outside-worktree", "host", "C2", "warning / medium", "stale_import",
       "Resolve the interpreter inside the worktree, or install non-editable (F2.7)"),
    _r("slow-host", "host", "C2", "warning / high", "slow_host",
       "Fix the host before running; timeouts on it are classed `slow_host` and spend no retries (F2.5)"),
    _r("check-ran-nothing", "history", "C2", "error / high", "blocked_without_check",
       "As `toolchain-not-covered`", min_n=1),
    _r("infra-heavy", "history", "C2", "warning / medium", "infra_heavy", "Read the leading `infra_cause`",
       min_n=20),
    _r("executor-outside-tested-range", "host", "C2", OWN, "", "owner: LIF executor compatibility",
       owner="executor-compat"),
    # C3 timeouts (ARC-B11)
    _r("default-step-timeout", "definition", "C3", "warning / high", "default_timeout",
       "Set `timeout_s` near the p90 of the same work (F3.4, F3.6)"),
    _r("default-judge-timeout", "definition", "C3", "info / high", "default_timeout",
       "Set the judge's `timeout_s`; a judge never takes the step's limit"),
    _r("idle-limit-inert", "definition", "C3", "warning / high", "idle_inert",
       "Lower `idle_s` below the wall limit, or remove it; it can never fire"),
    _r("no-idle-limit", "definition", "C3", "info / medium", "no_idle_limit",
       "Declare `idle_s` below the wall limit, above the longest silent tool call (F3.5)"),
    _r("hold-time-exposure", "definition", "C3", "warning / high", "hold_exposure",
       "Lower the limit or the budget, or set an idle limit (F3.5)"),
    _r("timeout-below-pass-p90", "history", "C3", "error / high", "timeout_too_short",
       "Set the limit to about 1.5 x the p90 of passing attempts (F3.4)", min_n=5),
    _r("attempts-at-limit", "history", "C3", "warning / high", "timeout_share", "By split (F3.2, F3.7)", min_n=5),
    _r("limit-far-above-p90", "history", "C3", "info / medium", "timeout_loose", "Lower the limit", min_n=5),
    _r("request-timed-out", "history", "C3", "warning / high", "request_timed_out",
       "Write the long output in parts (F3.3)", min_n=1),
    # C5 pauses (ARC-B12)
    _r("every-retry-asks", "definition", "C5", "warning / high", "ask_without_budget",
       "Give one retry, or `on_budget_spent: stop`; every RETRY pauses for a person"),
    _r("approval-on-most-gates", "definition", "C5", "info / medium", "approval_heavy",
       "Keep approval where a person decides something a judge cannot"),
    _r("empty-pauses", "history", "C5", "warning / medium", "empty_pause", "The pause adds nothing (F5.3)", min_n=4),
    _r("interventions-per-run", "history", "C5", "info / high", "person_rate", "Read the leading pause kind",
       min_n=5),
    _r("agent-rescues-alone", "history", "C5", "warning / high", "agent_decided",
       "Make it a check or an environmental cause, or have the skill relay it", min_n=5),
    _r("supervision-cost-share", "history", "C5", "warning / medium", "supervision_heavy",
       "The leading supervision category names the fix", min_n=5),
    _r("polling-supervisor", "history", "C5", "warning / high", "supervisor_polling",
       "Wait on the run's exit in the background instead of polling", min_n=5),
    _r("callers-unknown", "history", "C5", "info / high", "caller_unknown",
       "Run through a marked host, or declare the caller", min_n=10),
    # C6 cost (ARC-B13)
    _r("small-judge-cross-file", "definition", "C6", "warning / medium", "model_too_small",
       "Use `medium` or `large` for reading across files (F6.4: 5 of 19 against 18 of 19)"),
    _r("sizing-unassessed", "definition", "C6", "error / high", "sizing_unassessed",
       "State the model tier, the effort and one sentence of why on the step or judge (SCF-B10)"),
    _r("large-everywhere", "definition", "C6", "info / low", "model_heavy",
       "Choose models by what each step must find; start mechanical steps lower"),
    _r("no-run-cost-cap", "definition", "C6", "info / high", "no_cost_cap", "Set `run_cost_cap_usd` near the p90 run cost"),
    _r("context-heavy-step", "history", "C6", "warning / medium", "context_heavy",
       "Split the step or narrow what it reads (F6.3)", min_n=5),
    _r("cost-lens-rules", "history", "C6", OWN, "", "owner: SIL-B10 cost lens", owner="cost-lens"),
    # C7 prompt defects and C8 engine side (ARC-B14)
    _r("prompt-lint", "definition", "C7", OWN, "", "owner: LIF prompt lint", owner="prompt-lint"),
    _r("template-grammar", "definition", "C7", OWN, "", "owner: WFM-B8, WFM-B9, WFM-B10, WFM-B11", owner="validate"),
    _r("outcome-unverified-blocker", "definition", "C7", "warning / high", "outcome_unverified",
       "Find a verifier by the search order of AUT-B16, AUT-B17, AUT-B18, calibrate the judge (JCL), or make the criterion a sign-off"),
    _r("outcome-uncovered", "definition", "C7", "warning / high", "outcome_uncovered",
       "Add a serving criterion on the units before the outcome gate, or verify it at the outcome gate"),
    _r("outcome-escapes", "history", "C7", "warning / medium", "outcome_escape",
       "Revise the outcome: `outcome candidates`, then revise mode", min_n=10),
    _r("engine-fault-open", "history", "C8", "info / high", "", "owner: SIL", owner="SIL"),
    # ARC-B15 newer unit kinds: their kinds are refused in release 1 by validation, so these are not built
    _r("council-one-family", "definition", "C1", "warning / medium", "council_monoculture",
       "Put at least one member on another family", built=3),
    _r("council-even-majority", "definition", "C5", "info / high", "tie_prone", "Use an odd count", built=3),
    _r("council-rounds-no-gain", "history", "C6", "warning / medium", "rounds_no_gain", "Set `rounds: 0`",
       min_n=10, built=3),
    _r("council-conformity", "history", "C1", "info / low", "council_conformity", "Check stances and anonymity",
       min_n=10, built=3),
    _r("contest-identical-slots", "definition", "C6", "warning / high", "contest_no_diversity",
       "Vary model, executor or `prompt_variant`", built=3),
    _r("contest-no-gain", "history", "C6", "warning / medium", "contest_no_gain", "Reduce `slots`",
       min_n=10, built=3),
    _r("fallback-rate", "history", "C1", "warning / high", "fallback_heavy",
       "Read the unit's `loop-driver-criterion` and `low-first-pass` findings", min_n=5),
    _r("unbounded-wait", "definition", "C5", "info / medium", "wait_unbounded",
       "Add a deadline and an `on_deadline`", built=2),
    _r("external-after-without-approval", "definition", "C7", OWN, "publish_before_review",
       "owner: WFM-B12 (validation warns on it in release 1)", owner="validate"),
    # PRA-B7 to PRA-B10 prompt audit (family C7)
    _r("ref-missing", "definition", "C7", "error / high", "ref_missing",
       "Fix or remove the reference; the session wastes turns looking for it (F7.2)", spec="PRA"),
    _r("ref-resolves-elsewhere", "host", "C7", "warning / high", "skill_clash",
       "Ship the skill with the workflow or name it by plugin path (F4.8)", spec="PRA"),
    _r("tool-name-unknown", "host", "C7", OWN, "unknown_tool_name",
       "owner: LIF prompt lint `lint-tool-name-foreign` for executor tool names; MCP names need the view "
       "catalog (TSA, release 2)", owner="prompt-lint", spec="PRA"),
    _r("tool-name-stale", "host", "C7", "warning / high", "unknown_tool_name",
       "Replace it with the current name; the engine's tools block already names it (F4.6)", spec="PRA"),
    _r("prompt-tool-conflict", "definition", "C7", "warning / high", "prompt_conflict",
       "Make the text and the declaration say the same; the engine's tools block is the source of truth",
       spec="PRA"),
    _r("skill-frontmatter-nonstandard", "definition", "C7", "info / high", "skill_nonportable",
       "Keep to name, description, license, compatibility, metadata, allowed-tools, or ship a second form",
       spec="PRA"),
    _r("artifact-not-asked", "definition", "C7", "warning / medium", "prompt_conflict",
       "Name each produced artifact in the template; declare what the text asks for", spec="PRA"),
    _r("criterion-not-in-reach", "definition", "C7", "warning / medium", "prompt_conflict",
       "Add the reference or view, or mark the system `unverified_system`", spec="PRA"),
    _r("one-shot-long-output", "definition", "C7", "warning / low", "long_response",
       "Write a skeleton, then one edit per part (F3.3)", spec="PRA"),
    _r("prompt-oversized", "definition", "C7", OWN, "prompt_size",
       "owner: LIF prompt lint `lint-oversized` (same limits)", owner="prompt-lint", spec="PRA"),
    _r("rendered-near-cut", "history", "C7", "warning / high", "missing_input",
       "Narrow what the step is given (F1.5)", min_n=1, spec="PRA"),
    # AUD-B14
    _r("ignore-rule-unknown", "definition", "C8", "info / high", "",
       "Fix the rule id in `audit.ignore`, or remove the entry", spec="AUD"),
    _r("prompt-change-moved-gate", "history", "C7", OWN, "", "owner: SIL post-release watch", owner="SIL",
       spec="PRA"),
)

_ORDER = {r.id: i for i, r in enumerate(RULES)}
BY_ID: dict[str, Rule] = {r.id: r for r in RULES}
OWNERS = frozenset({"validate", "prompt-lint", "readiness", "executor-compat", "cost-lens", "SIL"})


def rule(rule_id: str) -> Rule:
    return BY_ID[rule_id]


def known(rule_id: str) -> bool:
    """A catalog id, or an owned code `<owner>:<code>` (AUD-B14 ignores name either)."""
    return rule_id in BY_ID or rule_id.partition(":")[0] in OWNERS
