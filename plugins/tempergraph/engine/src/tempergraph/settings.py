"""Run settings: one catalog over fixed layers, resolved the same way everywhere (RST §2; ADR-0070, 0071, 0072).

`resolve` and `validate_overrides` are pure and model-free. `run --check`, `run`, `resume` and `config show` call
them. The operator layers (flag, profile and both files) are snapshotted on the thread at start and reapplied on
resume (RST §2.6); the workflow layers come from the content the thread runs.
"""

from __future__ import annotations

import contextlib
import dataclasses
import difflib
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tempergraph.contracts import (
    GateSpec,
    JudgeSpec,
    ResolvedSettings,
    RunOptions,
    SessionOptions,
    SettingDecl,
    SettingRow,
    StepSpec,
    UnitSpec,
    WorkflowSpec,
)
from tempergraph.model.validate import Finding
from tempergraph.security.launch import has_shell_metacharacter

SETTINGS_FILE = "settings.json"

# Rank order of RST §2.3. The `arm:` layer sits below the first four: it is applied where a session request is
# built, for the keys no operator layer set (SWM §2.3).
LAYERS = ("flag", "profile", "project:overrides", "user:overrides", "workflow:unit", "workflow:default",
          "project:defaults", "user:defaults", "engine")
OPERATOR_LAYERS = ("flag", "profile", "project:overrides", "user:overrides", "project:defaults", "user:defaults")

SESSION = frozenset({"steps", "judges", "unit", "judge"})
STEP_SIDE = frozenset({"steps", "unit"})
JUDGE_SIDE = frozenset({"judges", "judge"})
SCRIPT = frozenset({"script"})
ALIAS = re.compile(r"^(inherit|small|medium|large|[a-z][a-z0-9-]*:[A-Za-z0-9._-]+)$")
SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
REF_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")

# Keys of the catalog whose feature is not in release 1 (ADR-0090): refused rather than silently ignored.
NOT_IN_RELEASE = {
    "audit_rate": "the audit judge (JDG-B7) is release 2",
    "audit_executor": "the audit judge (JDG-B7) is release 2",
    "attempt_cost_cap_usd": "council and contest units are release 2",
    "concurrency": "contest units are release 2",
    "deadline_s": "wait and ask units are release 2",
}
# Keys whose effect is not built yet on this branch, with the plan row that builds it.
NOT_BUILT: dict[str, str] = {}
WIDENING = frozenset({"tools.add", "commands.add", "views.add"})  # RST §2.8, T6.3


class SettingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------------------------
# Values


def _int(lo: int, hi: int | None = None) -> Callable[[Any], int]:
    def check(v: Any) -> int:
        if isinstance(v, bool):
            raise SettingError("setting_value", f"{v!r} is not a whole number")
        try:
            n = int(v) if not isinstance(v, float) or v.is_integer() else None
        except (TypeError, ValueError):
            n = None
        if n is None or n < lo or (hi is not None and n > hi):
            raise SettingError("setting_value", f"{v!r} is not a whole number from {lo}" + (f" to {hi}" if hi else ""))
        return n
    return check


def _float(lo: float, hi: float | None = None, *, open_lo: bool = True) -> Callable[[Any], float]:
    def check(v: Any) -> float:
        try:
            x = float(v) if not isinstance(v, bool) else None
        except (TypeError, ValueError):
            x = None
        if x is None or (x <= lo if open_lo else x < lo) or (hi is not None and x > hi):
            raise SettingError("setting_value", f"{v!r} is not a number {'above' if open_lo else 'from'} {lo}"
                               + (f" to {hi}" if hi is not None else ""))
        return x
    return check


def _choice(*choices: str) -> Callable[[Any], str]:
    def check(v: Any) -> str:
        if v not in choices:
            raise SettingError("setting_value", f"{v!r} is not one of {', '.join(choices)}")
        return str(v)
    return check


def _true(v: Any) -> bool:
    if v is True or v == "true":
        return True
    raise SettingError("tighten_only", "this key can only be set to true (RST §2.3)")


def _bool(v: Any) -> bool:
    if v in (True, "true"):
        return True
    if v in (False, "false"):
        return False
    raise SettingError("setting_value", f"{v!r} is not true or false")


def _alias(v: Any) -> str:
    if not isinstance(v, str) or not ALIAS.match(v):
        raise SettingError("setting_value", f"{v!r} is not a model alias (inherit, small, medium, large or "
                                            "<executor>:<name>)")
    return v


def _ladder(v: Any) -> str | tuple[str, ...]:
    if isinstance(v, str) and "," in v:
        v = [p.strip() for p in v.split(",")]
    if isinstance(v, (list, tuple)):
        if not 1 <= len(v) <= 8:
            raise SettingError("setting_value", "a model ladder has 1 to 8 aliases")
        return tuple(_alias(a) for a in v)
    return _alias(v)


def _slug(v: Any) -> str:
    if not isinstance(v, str) or not SLUG.match(v):
        raise SettingError("setting_value", f"{v!r} is not a name")
    return v


def _prefix(v: Any) -> str:
    parts = str(v).split("/")
    if not 1 <= len(parts) <= 3 or not all(REF_PART.match(p) for p in parts) or ".." in str(v):
        raise SettingError("setting_value", f"{v!r} is not 1 to 3 ref-safe components")
    return str(v)


@dataclasses.dataclass(frozen=True)
class Entry:
    scopes: frozenset[str]
    check: Callable[[Any], Any]
    default: Any = None
    release1: Callable[[Any], None] | None = None  # refuses a value whose feature is release 2


def _only(name: str, *ok: str) -> Callable[[Any], None]:
    def check(v: Any) -> None:
        if v not in ok:
            raise SettingError("setting_not_in_release", f"{name} {v!r} is release 2 (X2-23); release 1 takes "
                                                         f"{', '.join(ok)}")
    return check


def _base(v: Any) -> None:
    """WTR §2.5 release 1: `head` and `ref:<name>` (trial cases); `default_branch` is release 2."""
    if v == "head" or (isinstance(v, str) and v.startswith("ref:") and len(v) > 4):
        return
    raise SettingError("setting_not_in_release", f"worktree.base {v!r} is release 2 (X2-23); release 1 takes head "
                                                 "or ref:<name>")


RUN = frozenset({"run"})
CATALOG: dict[str, Entry] = {
    "executor": Entry(SESSION, _slug),
    "model": Entry(SESSION, _ladder, "inherit"),  # one alias on the judge side, checked in _value
    "subagent_model": Entry(STEP_SIDE, _alias),
    "effort": Entry(SESSION, _choice("low", "medium", "high", "max")),
    "session_cost_cap_usd": Entry(SESSION, _float(0)),
    "turn_cap": Entry(SESSION, _int(1, 500)),
    "fallback_alias": Entry(STEP_SIDE, _alias),
    "timeout_s": Entry(SESSION | SCRIPT, _int(1, 86_400), 600),
    "idle_s": Entry(SESSION, _int(30, 86_400)),
    "retry_budget": Entry(STEP_SIDE, _int(0, 10), 2),
    "loop_budget": Entry(STEP_SIDE, _int(0, 5), 1),
    "on_budget_spent": Entry(STEP_SIDE, _choice("stop", "ask", "fallback"), "ask"),
    "approve": Entry(frozenset({"unit"}), _true),
    "infra_tries": Entry(RUN, _int(0, 10), 3),
    "infra_backoff_max_s": Entry(RUN, _int(10, 300), 300),
    "attempt_cap": Entry(RUN, _int(1, 100), 15),
    "human_cap": Entry(RUN, _int(1, 100), 100),
    "run_cost_cap_usd": Entry(RUN, _float(0)),
    "daily_cap_usd": Entry(RUN, _float(0)),  # stable mode's self-improvement budget per day (SIL §4)
    "auto_reopen": Entry(RUN, _int(0, 10), 0),
    "workspace": Entry(RUN, _choice("auto", "in_place", "worktree"), "auto"),
    "session_review": Entry(RUN, _choice("auto", "full", "signals", "off"), "auto"),  # lowers only (SRV §2.3)
    "worktree.root": Entry(RUN, str, "sibling", _only("worktree.root", "sibling")),
    "worktree.base": Entry(RUN, str, "head", _base),
    "worktree.branch_prefix": Entry(RUN, _prefix, "tg"),
    "worktree.cleanup": Entry(RUN, _choice("never", "on_finish"), "never", _only("worktree.cleanup", "never")),
    "worktree.read_worktreeinclude": Entry(RUN, _bool, True),
    "enforce_tools": Entry(RUN, _true, False),
    "strict_permissions": Entry(RUN, _true, False),
    "audit_rate": Entry(RUN, _float(0, 1, open_lo=False), 0.0),
    "audit_executor": Entry(RUN, _slug),
    "arm": Entry(frozenset({"unit"}), str),
    "attempt_cost_cap_usd": Entry(frozenset({"unit"}), _float(0)),
    "concurrency": Entry(frozenset({"unit"}), _int(1, 5), 3),
    "deadline_s": Entry(frozenset({"unit"}), _int(1)),
    "tools.add": Entry(STEP_SIDE, lambda v: _caps(v, read_only=False)),
    "commands.add": Entry(STEP_SIDE | SCRIPT, lambda v: _prefixes(v)),
    "views.add": Entry(frozenset({"judge"}), lambda v: _caps(v, read_only=True)),
}
CAPABILITIES = frozenset({"read", "search", "list", "edit", "write", "shell", "web_fetch", "web_search", "subagent"})
READ_ONLY = frozenset({"read", "search", "list", "web_fetch", "web_search"})
MCP_CAP = re.compile(r"^mcp:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SKILL_CAP = re.compile(r"^skill:[a-z0-9][a-z0-9_-]*:[a-z0-9][a-z0-9_-]*$")


def _list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [p.strip() for p in v.split(",") if p.strip()]
    if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
        return [str(x) for x in v]
    raise SettingError("setting_value", f"{v!r} is not a list")


def _caps(v: Any, *, read_only: bool) -> tuple[str, ...]:
    """RST §2.8 What and Never: a capability name; a judge view is read-only (RST-B13)."""
    out = _list(v)
    for c in out:
        if not (c in CAPABILITIES or MCP_CAP.match(c) or SKILL_CAP.match(c)):
            raise SettingError("unknown-capability", f"{c!r} is not a tool capability (CON §2.5)")
        if read_only and c.startswith("mcp:"):
            raise SettingError("judge-view-unclassified", f"{c!r}: release 1 has no read-only MCP catalog; a judge "
                                                          "sees an MCP tool only as the derived view of its step's")
        if read_only and c not in READ_ONLY:
            raise SettingError("judge-view-not-read-only", f"{c!r}: a judge takes read-only views only")
    return tuple(out)


def _prefixes(v: Any) -> tuple[str, ...]:
    out = _list(v) if not isinstance(v, str) else [v.strip()]
    for c in out:
        if not c or has_shell_metacharacter(c):
            raise SettingError("command-metacharacter", f"command {c!r} holds a shell metacharacter")
    return tuple(out)


# Fields of a unit that verify the work: never a setting (ADR-0071).
VERIFICATION = frozenset({"criteria", "check", "judge", "stance", "brief", "tools", "prompt", "back_targets",
                          "flow", "references", "subject", "views", "fallback", "independence", "approval"})
SESSION_OPTIONS = {"effort": "effort", "session_cost_cap_usd": "cost_cap_usd", "fallback_alias": "fallback_alias",
                   "turn_cap": "turn_cap"}


def parse_value(raw: str) -> Any:
    """A `--set` value: JSON when it parses (numbers, booleans, lists), else the text itself."""
    try:
        return json.loads(raw)
    except ValueError:
        return raw


# ---------------------------------------------------------------------------------------------
# Keys


@dataclasses.dataclass(frozen=True)
class Key:
    scope: str  # run, steps, judges, unit, judge, script, settings
    name: str
    unit: str | None = None
    script: tuple[str, int] | None = None  # ("before" | "after", n from 1)

    def text(self) -> str:
        head = {"run": "run", "steps": "steps", "judges": "judges", "settings": "settings"}.get(self.scope)
        if head:
            return f"{head}.{self.name}"
        if self.scope == "judge":
            return f"judge:{self.unit}.{self.name}"
        if self.scope == "script":
            assert self.script is not None
            return f"{self.unit}.{self.script[0]}:{self.script[1]}.{self.name}"
        return f"{self.unit}.{self.name}"


def _nearest(word: str, names: Iterable[str]) -> str:
    near = difflib.get_close_matches(word, list(names), n=1)
    return f"; did you mean {near[0]!r}?" if near else ""


def parse_key(spec: WorkflowSpec, raw: str) -> Key:
    """RST §2.1 keys, checked against the workflow and the catalog (RST-B5, B10, §4)."""
    head, dot, rest = raw.partition(".")
    if not dot or not rest:
        raise SettingError("unknown_setting", f"{raw!r} is not <scope>.<name>")
    if head == "settings":
        if rest not in spec.settings:
            raise SettingError("unknown_setting", f"the workflow declares no setting {rest!r}"
                                                  + _nearest(rest, spec.settings))
        return Key("settings", rest)
    if head in ("run", "steps", "judges"):
        key = Key(head, rest)
    elif head.startswith("judge:"):
        key = Key("judge", rest, unit=head[6:])
    else:
        unit = head
        m = re.match(r"^(before|after):(\d+)\.(.+)$", rest)
        sub = re.match(r"^(member|chair|slot)(:[^.]*)?\.", rest)
        if sub:
            _unit_exists(spec, unit, raw)
            raise SettingError("setting_not_for_kind", f"{raw}: {unit} is a {spec.units[unit].kind}, not a council "
                                                       "or contest (those are release 2)")
        if m:
            key = Key("script", m.group(3), unit=unit, script=(m.group(1), int(m.group(2))))
        else:
            key = Key("unit", rest, unit=unit)
    name = key.name
    if name not in WIDENING and (name in VERIFICATION or name.split(".")[0] in VERIFICATION):
        raise SettingError("not_a_setting", f"{raw}: what verifies the work is not a setting (ADR-0071)")
    if name not in CATALOG:
        raise SettingError("unknown_setting", f"{raw}: no setting {name!r}" + _nearest(name, CATALOG))
    entry = CATALOG[name]
    if key.unit is not None:
        _unit_exists(spec, key.unit, raw)
    if name in NOT_IN_RELEASE:
        raise SettingError("setting_not_in_release", f"{raw}: {NOT_IN_RELEASE[name]}")
    if name in NOT_BUILT:
        raise SettingError("setting_not_built", f"{raw}: built in {NOT_BUILT[name]}")
    if key.scope not in entry.scopes:
        raise SettingError("setting_not_for_kind", f"{raw}: {name} is set on {', '.join(sorted(entry.scopes))}")
    if key.scope in ("unit", "script", "judge"):
        u = spec.units[str(key.unit)]
        if key.scope == "judge" and u.gate.judge is None:
            raise SettingError("setting_not_for_kind", f"{raw}: {key.unit} has no judge")
        if name == "arm":
            if u.switch is None:
                raise SettingError("setting_not_for_kind", f"{raw}: {key.unit} is a {u.kind}, not a switch")
        elif key.scope == "unit" and not (u.kind == "step" or (u.kind == "script" and name == "timeout_s")):
            raise SettingError("setting_not_for_kind", f"{raw}: {key.unit} is a {u.kind}")
        if key.scope == "script":
            phase, n = key.script or ("", 0)
            scripts = (u.step.before if phase == "before" else u.step.after) if u.step is not None else ()
            if not 1 <= n <= len(scripts):
                raise SettingError("setting_not_for_kind", f"{raw}: {key.unit} has no {phase} script {n}")
    return key


def _unit_exists(spec: WorkflowSpec, unit: str, raw: str) -> None:
    if unit not in spec.units:
        raise SettingError("unknown_setting", f"{raw}: no unit {unit!r}" + _nearest(unit, spec.units))


def _value(spec: WorkflowSpec, key: Key, value: Any) -> Any:
    if key.scope == "settings":
        return check_declared(spec.settings[key.name], value)
    entry = CATALOG[key.name]
    v = entry.check(value)
    if key.name == "model" and key.scope in JUDGE_SIDE and not isinstance(v, str):
        raise SettingError("setting_value", "a judge takes one alias, never a ladder")
    if entry.release1 is not None:
        entry.release1(v)
    if key.name == "arm":
        sw = spec.units[str(key.unit)].switch
        if sw is None or v not in sw.arms:
            raise SettingError("setting_value", f"{key.text()}: {v!r} is not one of the arms "
                                                f"{', '.join(sw.arms) if sw else ''}")
    if key.name == "on_budget_spent" and v == "fallback":
        units = [key.unit] if key.unit else [n for n, u in spec.units.items() if u.kind == "step"]
        if any(spec.units[str(n)].gate.fallback is None for n in units):
            raise SettingError("no_fallback_target", f"{key.text()}: the gate declares no fallback target")
    return v


def check_declared(decl: SettingDecl, value: Any) -> Any:
    """RST §2.5 value kinds."""
    kind = decl.kind
    if kind == "bool":
        return _bool(value)
    if kind in ("int", "duration_s"):
        lo = int(decl.min) if decl.min is not None else (0 if kind == "duration_s" else -(10**12))
        v = _int(lo, int(decl.max) if decl.max is not None else None)(value)
        return v
    if kind == "float":
        try:
            x = float(value)
        except (TypeError, ValueError):
            raise SettingError("setting_value", f"{value!r} is not a number") from None
        if (decl.min is not None and x < decl.min) or (decl.max is not None and x > decl.max):
            raise SettingError("setting_value", f"{x} is outside {decl.min} to {decl.max}")
        return x
    if kind == "choice":
        if value not in (decl.choices or ()):
            raise SettingError("setting_value", f"{value!r} is not one of {', '.join(decl.choices or ())}")
        return str(value)
    if not isinstance(value, str):
        raise SettingError("setting_value", f"{value!r} is not text")
    return value


# ---------------------------------------------------------------------------------------------
# Files


@dataclasses.dataclass(frozen=True, kw_only=True)
class ConfigFiles:
    """The two `settings.json` files (RST §2.4); `None` where the file does not exist."""

    project: Mapping[str, Any] | None = None
    user: Mapping[str, Any] | None = None
    project_path: Path | None = None
    user_path: Path | None = None
    errors: tuple[Finding, ...] = ()


@dataclasses.dataclass(frozen=True, kw_only=True)
class Capture:
    """The operator's capture level and observers (LOS §2.6, EVT §2.5): full capture unless lowered."""

    raw: bool = True
    tool_inputs: bool = True
    check_output: bool = True
    observers: tuple[str, ...] = ()

    def lowered(self) -> list[str]:
        return [k for k in ("raw", "tool_inputs", "check_output") if not getattr(self, k)]


def capture(files: ConfigFiles) -> Capture:
    """The `observe` map of the settings files: `raw`, `tool_inputs`, `check_output` (`on` or `off`) and
    `observers` (names to enable). The project file wins per key over the user file; never a run layer."""
    got: dict[str, Any] = {}
    for doc in (files.user, files.project):
        o = (doc or {}).get("observe")
        if isinstance(o, Mapping):
            got.update(o)

    def on(key: str) -> bool:
        return got.get(key, "on") not in ("off", False)

    names = got.get("observers")
    obs = tuple(str(n) for n in names if isinstance(n, str)) if isinstance(names, list) else ()
    return Capture(raw=on("raw"), tool_inputs=on("tool_inputs"), check_output=on("check_output"), observers=obs)


def config_paths(state_root: Path | None, home: Path) -> tuple[Path | None, Path]:
    return (state_root / "config" / SETTINGS_FILE if state_root else None), home / "config" / SETTINGS_FILE


def load_files(state_root: Path | None, home: Path) -> ConfigFiles:
    """Read both files once; a file that does not parse or has a newer schema is a finding (RST §4)."""
    pp, up = config_paths(state_root, home)
    docs: dict[str, Any] = {}
    errors: list[Finding] = []
    for name, p in (("project", pp), ("user", up)):
        if p is None or not p.exists():
            docs[name] = None
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(Finding(code="config_file", unit=None, message=f"{p}: {exc}"))
            docs[name] = None
            continue
        if not isinstance(doc, Mapping) or doc.get("schema_version") != 1:
            errors.append(Finding(code="config_file", unit=None, message=f"{p}: not a schema_version 1 object"))
            docs[name] = None
            continue
        docs[name] = doc
    return ConfigFiles(project=docs["project"], user=docs["user"], project_path=pp, user_path=up,
                       errors=tuple(errors))


def _file_layers(spec: WorkflowSpec, files: ConfigFiles) -> tuple[dict[str, dict[str, dict[str, Any]]],
                                                                    list[Finding]]:
    layers: dict[str, dict[str, dict[str, Any]]] = {}
    out: list[Finding] = list(files.errors)
    for where, doc, path in (("project", files.project, files.project_path), ("user", files.user, files.user_path)):
        if doc is None:
            continue
        ov: dict[str, dict[str, Any]] = {}
        named: set[str] = set()
        for i, entry in enumerate(doc.get("overrides") or []):
            if not isinstance(entry, Mapping) or entry.get("workflow") not in (spec.name, "*"):
                continue
            for k, v in (entry.get("set") or {}).items():
                if _widening(str(k)):
                    out.append(Finding(code="widening_in_file", unit=None, message=f"{path}: {k} widens tools; only "
                                                                                     "a person's flag may (RST §2.8)"))
                    continue
                specific = entry.get("workflow") == spec.name
                if k in ov and not specific and k in named:
                    continue  # a named entry beats `*` per key
                ov[str(k)] = {"value": v, "ref": f"{path}#overrides[{i}]"}
                if specific:
                    named.add(str(k))
        layers[f"{where}:overrides"] = ov
        df: dict[str, dict[str, Any]] = {}
        for k, v in (doc.get("defaults") or {}).items():
            head = str(k).split(".")[0]
            if head not in ("run", "steps", "judges", "settings"):
                out.append(Finding(code="unit_in_defaults", unit=None,
                                   message=f"{path}: defaults key {k} names a unit; use overrides"))
                continue
            if head == "settings" and str(k)[9:] not in spec.settings:
                continue  # another workflow's setting
            df[str(k)] = {"value": v, "ref": f"{path}#defaults"}
        layers[f"{where}:defaults"] = df
    return layers, out


def _widening(k: str) -> bool:
    return any(k.endswith("." + w) for w in WIDENING)


is_widening = _widening


def as_list(v: Any) -> list[str]:
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else _list(v) if isinstance(v, str) else [str(v)]


def find_profile(spec: WorkflowSpec, name: str, files: ConfigFiles) -> tuple[Mapping[str, Any], str] | None:
    """Project file, then user file, then the workflow's own; the first found is used whole (RST §2.4)."""
    for doc, path in ((files.project, files.project_path), (files.user, files.user_path)):
        prof = ((doc or {}).get("profiles") or {}).get(name)
        if isinstance(prof, Mapping):
            return prof, f"{path}#profiles.{name}"
    if name in spec.profiles:
        return spec.profiles[name], f"workflow:profiles.{name}"
    return None


# ---------------------------------------------------------------------------------------------
# Snapshot (RunOptions.settings) and validation


def snapshot(spec: WorkflowSpec, flags: Mapping[str, Any], profiles: Sequence[str], files: ConfigFiles,
             via: str = "cli") -> tuple[dict[str, dict[str, dict[str, Any]]], list[Finding]]:
    """The operator layers for `RunOptions.settings`: layer -> key -> {value, ref, via?} (RST §2.6)."""
    out: list[Finding] = []
    layers, file_findings = _file_layers(spec, files)
    out += file_findings
    prof: dict[str, dict[str, Any]] = {}
    for name in profiles:
        found = find_profile(spec, name, files)
        if found is None:
            out.append(Finding(code="unknown_profile", unit=None, message=f"no profile {name!r}"))
            continue
        values, ref = found
        if not ref.startswith("workflow:"):
            for k in values:
                if _widening(str(k)):
                    out.append(Finding(code="widening_in_file", unit=None,
                                       message=f"{ref}: {k} widens tools; only a workflow's own profile may"))
        prof.update({str(k): {"value": v, "ref": ref} for k, v in values.items() if not
                     (_widening(str(k)) and not ref.startswith("workflow:"))})
    layers["profile"] = prof
    layers["flag"] = {str(k): {"value": v, "ref": f"--set {k}", "via": via} for k, v in flags.items()}
    return {k: layers.get(k, {}) for k in OPERATOR_LAYERS}, out


def validate_layers(spec: WorkflowSpec, layers: Mapping[str, Mapping[str, Mapping[str, Any]]],
                    caller_kind: str = "person") -> list[Finding]:
    out: list[Finding] = []
    if caller_kind != "person":
        for raw in (layers.get("flag") or {}):
            if _widening(raw):
                out.append(Finding(code="widening_by_agent", unit=None,
                                   message=f"{raw}: only a person may widen a step's tools (RST §2.8, PRV §2.8)"))
    for layer in OPERATOR_LAYERS:
        for raw, cell in (layers.get(layer) or {}).items():
            try:
                key = parse_key(spec, raw)
                _value(spec, key, cell.get("value"))
            except SettingError as exc:
                out.append(Finding(code=exc.code, unit=None, message=f"{layer} {cell.get('ref', raw)}: {exc}"))
    return out


def options_snapshot(spec: WorkflowSpec, flags: Mapping[str, Any], profiles: Sequence[str], files: ConfigFiles,
                     via: str = "cli", caller_kind: str = "person") -> tuple[RunOptions, list[Finding]]:
    layers, out = snapshot(spec, flags, profiles, files, via)
    out += validate_layers(spec, layers, caller_kind)
    return RunOptions(settings={k: dict(v) for k, v in layers.items()}, profiles=tuple(profiles)), out


def validate_overrides(spec: WorkflowSpec, options: RunOptions, files: ConfigFiles) -> list[Finding]:
    """RST §2 contract: every operator value of these options and files, checked before spend."""
    flags = {k: c["value"] for k, c in (options.settings.get("flag") or {}).items()}
    _, out = options_snapshot(spec, flags, options.profiles, files)
    return out


# ---------------------------------------------------------------------------------------------
# Resolution


def _workflow_values(spec: WorkflowSpec) -> dict[str, dict[str, dict[str, Any]]]:
    """The two workflow layers as concrete keys: what the units and the workflow declare."""
    unit_l: dict[str, dict[str, Any]] = {}
    dflt: dict[str, dict[str, Any]] = {}

    def put(layer: dict[str, dict[str, Any]], key: str, value: Any, ref: str) -> None:
        if value is not None:
            layer[key] = {"value": value, "ref": ref}

    for name, u in spec.units.items():
        g = u.gate
        if u.kind == "step" and u.step is not None:
            st = u.step
            put(unit_l, f"{name}.executor", st.executor, f"units.{name}.executor")
            put(unit_l, f"{name}.model", st.model, f"units.{name}.model")
            put(unit_l, f"{name}.subagent_model", st.subagent_model, f"units.{name}.subagent_model")
            put(unit_l, f"{name}.timeout_s", st.timeout_s, f"units.{name}.timeout_s")
            put(unit_l, f"{name}.idle_s", st.idle_s, f"units.{name}.idle_s")
            for k, f in SESSION_OPTIONS.items():
                put(unit_l, f"{name}.{k}", getattr(st.session_options, f) if st.session_options else None,
                    f"units.{name}.session_options.{f}")
            for k, default in (("retry_budget", 2), ("loop_budget", 1), ("on_budget_spent", "ask")):
                if getattr(g, k) != default:
                    put(unit_l, f"{name}.{k}", getattr(g, k), f"units.{name}.gate.{k}")
            if g.approval:
                put(unit_l, f"{name}.approve", True, f"units.{name}.gate.approval")
            for phase in ("before", "after"):
                for i, sc in enumerate(getattr(st, phase), start=1):
                    if sc.timeout_s != 600:
                        put(unit_l, f"{name}.{phase}:{i}.timeout_s", sc.timeout_s, f"units.{name}.{phase}[{i - 1}]")
            put(dflt, f"{name}.model", spec.model_profile.get(name), f"model_profile.{name}")
        if u.kind == "script" and u.script is not None and u.script.timeout_s != 600:
            put(unit_l, f"{name}.timeout_s", u.script.timeout_s, f"units.{name}.script.timeout_s")
        j = g.judge
        if j is not None:
            put(unit_l, f"judge:{name}.executor", j.executor, f"units.{name}.gate.judge.executor")
            put(unit_l, f"judge:{name}.timeout_s", j.timeout_s, f"units.{name}.gate.judge.timeout_s")
            put(unit_l, f"judge:{name}.idle_s", j.idle_s, f"units.{name}.gate.judge.idle_s")
            for k, f in SESSION_OPTIONS.items():
                if k != "fallback_alias":
                    put(unit_l, f"judge:{name}.{k}", getattr(j.session_options, f) if j.session_options else None,
                        f"units.{name}.gate.judge.session_options.{f}")
            if j.model:
                put(unit_l, f"judge:{name}.model", j.model, f"units.{name}.gate.judge.model")
            elif u.step is not None and u.step.model:
                ladder = [u.step.model] if isinstance(u.step.model, str) else list(u.step.model)
                put(unit_l, f"judge:{name}.model", ladder[-1], f"units.{name}.model[-1]")  # CON §2.4
            prof = spec.model_profile.get(f"judge:{name}")
            put(dflt, f"judge:{name}.model", prof if isinstance(prof, str) or prof is None else list(prof)[0],
                f"model_profile.judge:{name}")
    put(dflt, "run.run_cost_cap_usd", spec.run_cost_cap_usd, "run_cost_cap_usd")
    put(dflt, "run.daily_cap_usd", spec.daily_cap_usd, "daily_cap_usd")
    if spec.workspace != "auto":
        put(dflt, "run.workspace", spec.workspace, "workspace")
    if spec.worktree is not None:
        put(dflt, "run.worktree.base", spec.worktree.base, "worktree.base")
        put(dflt, "run.worktree.cleanup", spec.worktree.cleanup, "worktree.cleanup")
    for name, decl in spec.settings.items():
        put(dflt, f"settings.{name}", decl.default, f"settings.{name}.default")
    return {"workflow:unit": unit_l, "workflow:default": dflt}


def targets(spec: WorkflowSpec) -> list[tuple[str, str, list[str]]]:
    """Every concrete key the run reads, its catalog name, and its matching keys narrowest first (RST §2.3)."""
    out: list[tuple[str, str, list[str]]] = []
    for name, e in CATALOG.items():
        if name in NOT_IN_RELEASE or name in NOT_BUILT:
            continue
        if "run" in e.scopes:
            out.append((f"run.{name}", name, [f"run.{name}"]))
    for unit, u in spec.units.items():
        for name, e in CATALOG.items():
            if name in NOT_IN_RELEASE or name in NOT_BUILT:
                continue
            if name == "arm":
                if u.switch is not None:
                    out.append((f"{unit}.arm", "arm", [f"{unit}.arm"]))
                continue
            if u.kind == "step" and e.scopes & STEP_SIDE:
                out.append((f"{unit}.{name}", name, [f"{unit}.{name}", f"steps.{name}"] if "steps" in e.scopes
                            else [f"{unit}.{name}"]))
            if u.kind == "script" and name == "timeout_s":
                out.append((f"{unit}.timeout_s", "timeout_s", [f"{unit}.timeout_s"]))
            if u.gate.judge is not None and e.scopes & JUDGE_SIDE:
                out.append((f"judge:{unit}.{name}", name, [f"judge:{unit}.{name}", f"judges.{name}"]))
        if u.step is not None:
            for phase in ("before", "after"):
                for i, _ in enumerate(getattr(u.step, phase), start=1):
                    for name in ("timeout_s", "commands.add"):
                        k = f"{unit}.{phase}:{i}.{name}"
                        out.append((k, name, [k]))
    for name in spec.settings:
        out.append((f"settings.{name}", "", [f"settings.{name}"]))
    return out


def _canonical(v: Any) -> Any:
    return list(v) if isinstance(v, tuple) else v


def resolve(spec: WorkflowSpec, options: RunOptions, files: ConfigFiles | None = None) -> ResolvedSettings:
    """Pure: the winning value, layer and ref of every key the run reads (RST §2.3, §2.7).

    `options.settings` is the snapshot of the operator layers. With `files`, the file and profile layers are
    built from them and only the flags are taken from the options (a start, `config show`, `run --check`).
    """
    layers: dict[str, Mapping[str, Mapping[str, Any]]] = dict(options.settings or {})
    if files is not None:
        flags = {k: c["value"] for k, c in (layers.get("flag") or {}).items()}
        layers = dict(snapshot(spec, flags, options.profiles, files)[0])
    layers.update(_workflow_values(spec))
    text_keys = {f"settings.{n}" for n, d in spec.settings.items() if d.kind == "text"}
    values: dict[str, Any] = {}
    rows: list[SettingRow] = []
    for target, name, matching in targets(spec):
        found: list[tuple[str, Any, str]] = []
        for layer in LAYERS[:-1]:
            cells = layers.get(layer) or {}
            for m in matching:  # inside a layer the narrowest matching scope wins
                if m in cells:
                    found.append((layer, cells[m]["value"], str(cells[m].get("ref") or m)))
                    break
        entry = CATALOG.get(name)
        if found:
            layer, value, ref = found[0]
            if layer in OPERATOR_LAYERS:
                with contextlib.suppress(SettingError):  # refused by validate_layers before any start
                    value = _value(spec, parse_key(spec, target), value)
            values[target] = value
            shown = (hashlib.sha256(str(value).encode()).hexdigest()[:16] if target in text_keys else value)
            rows.append(SettingRow(key=target, value=_canonical(shown), layer=layer, ref=ref,
                                   shadowed=tuple({"layer": lyr, "ref": r} for lyr, _, r in found[1:])))
        else:
            values[target] = entry.default if entry is not None else None
    table = [{"key": r.key, "value": r.value, "layer": r.layer} for r in rows]
    digest = hashlib.sha256(json.dumps(table, sort_keys=True, default=str).encode()).hexdigest()
    return ResolvedSettings(rows=tuple(rows), values=values, digest=digest, profiles=tuple(options.profiles))


def overridden_keys(res: ResolvedSettings) -> list[str]:
    """Keys whose winning layer ranks 1 to 4 (RST §2.7)."""
    return [r.key for r in res.rows if r.layer in LAYERS[:4]]


def changed_keys(old: ResolvedSettings | None, new: ResolvedSettings) -> list[str]:
    if old is None:
        return []
    keys = set(old.values) | set(new.values)
    return sorted(k for k in keys if _canonical(old.values.get(k)) != _canonical(new.values.get(k)))


# ---------------------------------------------------------------------------------------------
# Applying a resolution to the spec the run executes


def effective_spec(spec: WorkflowSpec, res: ResolvedSettings) -> WorkflowSpec:
    """The workflow with every resolved session, budget and workflow-wide value in its own field.

    Judges get their resolved model written in, so a step-side override never reaches them through the
    runner's step-to-judge inheritance (RST §2.3, Judges apart).
    """
    v = res.values
    layer_of = {r.key: r.layer for r in res.rows}
    units: dict[str, UnitSpec] = {}
    for name, u in spec.units.items():
        g: GateSpec = u.gate
        if u.kind == "step" and u.step is not None:
            st: StepSpec = u.step
            opts = SessionOptions(**{f: v.get(f"{name}.{k}") for k, f in SESSION_OPTIONS.items()})
            added = tuple(v.get(f"{name}.tools.add") or ())
            cmds = tuple(v.get(f"{name}.commands.add") or ())
            st = dataclasses.replace(
                st, tools=tuple(dict.fromkeys(st.tools + added)), commands=tuple(dict.fromkeys(st.commands + cmds)),
                executor=v.get(f"{name}.executor") or st.executor,
                model=_model(v.get(f"{name}.model")), timeout_s=v.get(f"{name}.timeout_s"),
                idle_s=v.get(f"{name}.idle_s"), subagent_model=v.get(f"{name}.subagent_model"),
                session_options=opts if opts.set_names() else None,
                before=tuple(dataclasses.replace(sc, timeout_s=int(v.get(f"{name}.before:{i}.timeout_s") or 600))
                             for i, sc in enumerate(st.before, start=1)),
                after=tuple(dataclasses.replace(sc, timeout_s=int(v.get(f"{name}.after:{i}.timeout_s") or 600))
                            for i, sc in enumerate(st.after, start=1)))
            g = dataclasses.replace(g, retry_budget=int(v.get(f"{name}.retry_budget", g.retry_budget)),
                                    loop_budget=int(v.get(f"{name}.loop_budget", g.loop_budget)),
                                    on_budget_spent=v.get(f"{name}.on_budget_spent") or g.on_budget_spent,
                                    approval=g.approval or bool(v.get(f"{name}.approve")))
            operator = tuple(k for k in ("model", "timeout_s", "idle_s", "effort")
                             if layer_of.get(f"{name}.{k}") in LAYERS[:4])
            u = dataclasses.replace(u, step=st, extra={**u.extra, "operator_set": operator} if operator else u.extra)
        if u.switch is not None and v.get(f"{name}.arm"):
            u = dataclasses.replace(u, extra={**u.extra, "arm": v.get(f"{name}.arm")})  # CMP-B7
        if u.kind == "script" and u.script is not None:
            u = dataclasses.replace(u, script=dataclasses.replace(u.script, timeout_s=int(
                v.get(f"{name}.timeout_s") or u.script.timeout_s)))
        if g.judge is not None:
            j: JudgeSpec = g.judge
            jopts = SessionOptions(**{f: v.get(f"judge:{name}.{k}") for k, f in SESSION_OPTIONS.items()
                                      if k != "fallback_alias"})
            model = v.get(f"judge:{name}.model")
            j = dataclasses.replace(j, executor=v.get(f"judge:{name}.executor") or j.executor,
                                    model=model if model and model != "inherit" else None,
                                    timeout_s=v.get(f"judge:{name}.timeout_s"), idle_s=v.get(f"judge:{name}.idle_s"),
                                    session_options=jopts if jopts.set_names() else None)
            g = dataclasses.replace(g, judge=j)
            views = tuple(v.get(f"judge:{name}.views.add") or ())
            if views:
                u = dataclasses.replace(u, extra={**u.extra, "views_add": views})
        units[name] = dataclasses.replace(u, gate=g)
    wt = spec.worktree
    if wt is not None:
        wt = dataclasses.replace(wt, base=v.get("run.worktree.base"), cleanup=v.get("run.worktree.cleanup"))
    allowed = tuple(dict.fromkeys(spec.allow_commands + tuple(
        p for k, val in v.items() if k.endswith("commands.add") for p in (val or ()))))
    return dataclasses.replace(spec, units=units, run_cost_cap_usd=v.get("run.run_cost_cap_usd"),
                               allow_commands=allowed,
                               workspace=v.get("run.workspace") or "auto", worktree=wt)


def _model(v: Any) -> str | tuple[str, ...] | None:
    if v is None or v == "inherit":
        return None
    return tuple(v) if isinstance(v, (list, tuple)) else str(v)


def run_values(res: ResolvedSettings) -> dict[str, Any]:
    """The run-scope values (`run.<name>` without the prefix)."""
    return {k[4:]: val for k, val in res.values.items() if k.startswith("run.")}


def workflow_settings(res: ResolvedSettings) -> dict[str, Any]:
    """`settings.<name>` values for checks, scripts and templates (RST §2.5)."""
    return {k[9:]: val for k, val in res.values.items() if k.startswith("settings.")}


def rows_json(res: ResolvedSettings) -> list[dict[str, Any]]:
    return [{"key": r.key, "value": r.value, "layer": r.layer, "ref": r.ref, "shadowed": list(r.shadowed),
             **({"widening": True} if _widening(r.key) else {})} for r in res.rows]


def grants(res: ResolvedSettings) -> list[dict[str, Any]]:
    """Every resolved widening value as one grant: `{unit, key, capability | prefix}` (RST §2.8 Shown)."""
    out: list[dict[str, Any]] = []
    for k, v in sorted(res.values.items()):
        if not _widening(k) or not v:
            continue
        unit = k.split(".", 1)[0].removeprefix("judge:")
        field_ = "prefix" if k.endswith("commands.add") else "capability"
        out += [{"unit": unit, "key": k, field_: item} for item in v]
    return out

