"""Unattended credential kinds and the per-executor check (TCK-B18, TCK-B19, TCK-B5, TCK-B6).

A fire runs with nobody present, so each executor declares the kinds it can use unattended (`Capabilities.
unattended_credentials`) and the check resolves what the operator's credentials profile (`config/credentials/default`
under the home store) and the environment hold. Presence only: no value is kept, no network call and no model call is
made (C13). Four kinds: `api_key`, `cloud`, `oauth_token`, `interactive_login`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tempergraph.executors.capabilities import DECLARED

PROFILE = "default"  # the credentials profile a fire reads (assumption recorded in R-150 F50)
CLOUD_FLAGS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
ENV_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "claude": {"api_key": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"), "cloud": CLOUD_FLAGS,
               "oauth_token": ("CLAUDE_CODE_OAUTH_TOKEN",)},
    "agent-sdk": {"api_key": ("ANTHROPIC_API_KEY",), "cloud": CLOUD_FLAGS},
    "messages-api": {"api_key": ("ANTHROPIC_API_KEY",), "cloud": CLOUD_FLAGS},
    "antigravity": {"api_key": ("GEMINI_API_KEY",)},
}
HELPER = "apiKeyHelper"  # a command in the profile that prints an API key
LOGIN_FILES: dict[str, tuple[str, ...]] = {"claude": (".claude/.credentials.json",), "antigravity": (".gemini/oauth_creds.json",)}
CREDENTIAL_NAMES = frozenset(n for kinds in ENV_NAMES.values() for names in kinds.values() for n in names) | {
    "CLAUDE_CODE_OAUTH_TOKEN"}
FIX = "an API key, an apiKeyHelper or cloud credentials (Bedrock, Vertex or Foundry) in the credentials profile"


@dataclass
class Check:
    checked: list[dict[str, Any]] = field(default_factory=list)  # one row per executor and role: what `executors_checked` keeps
    warnings: list[str] = field(default_factory=list)
    refusal: tuple[str, str] | None = None  # (code, message), the first refusal


WARNING_TEXT = {
    "credential_may_expire": "a signed-in session can end; fires then refuse",
    "credential_none": "no credential this check can see; every fire is refused `credential` until the profile or the "
                       "environment holds one",
}


def read_profile(home: Path | None = None, name: str = PROFILE) -> dict[str, str]:
    """`name=value` lines of the credentials profile (as the claude executor reads a judge's), or nothing."""
    from tempergraph.store.layout import home_path

    path = (home or home_path()) / "config" / "credentials" / name
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k.strip()):
                out[k.strip()] = v.strip()
    return out


def profile_values(profile: Mapping[str, str]) -> dict[str, str]:
    """The names of the profile that carry credentials: what a fire's child receives, never kept in any entry."""
    return {k: v for k, v in profile.items() if k in CREDENTIAL_NAMES or k == HELPER}


def resolve_kinds(executor: str, environment: Mapping[str, str], profile: Mapping[str, str], *,
                  login_present: bool = False) -> frozenset[str]:
    """Which kinds the environment and the profile hold for one executor (presence only)."""
    names = ENV_NAMES.get(executor, {})
    merged = {**profile, **environment}
    kinds = {kind for kind, vars_ in names.items() if any(merged.get(v) for v in vars_)}
    if executor == "claude" and profile.get(HELPER):
        kinds.add("api_key")
    if login_present and executor in LOGIN_FILES:
        kinds.add("interactive_login")
    return frozenset(kinds)


def login_cached(executor: str, user_home: Path | None = None, environment: Mapping[str, str] | None = None) -> bool:
    """A person's cached sign-in file of the product; the Keychain cannot be read model-free (P-SCH-2)."""
    base = user_home or Path.home()
    paths = [base / rel for rel in LOGIN_FILES.get(executor, ())]
    if executor == "claude" and (environment or {}).get("CLAUDE_CONFIG_DIR"):
        paths.append(Path(str((environment or {})["CLAUDE_CONFIG_DIR"])) / ".credentials.json")
    return any(p.is_file() for p in paths)


def held_kinds(executors: Sequence[str], environment: Mapping[str, str], profile: Mapping[str, str],
               user_home: Path | None = None) -> dict[str, frozenset[str]]:
    return {ex: resolve_kinds(ex, environment, profile, login_present=login_cached(ex, user_home, environment))
            for ex in dict.fromkeys(executors)}


def bare_judge(executor: str) -> bool:
    """A judge launched with `--bare` reads no sign-in, so it needs `api_key` or `cloud` (TCK-B6)."""
    caps = DECLARED.get(executor)
    return bool(executor == "claude" and caps is not None and caps.isolates_user_config)


def bindings_of(step_executors: Mapping[str, str], judges: Mapping[str, str]) -> list[dict[str, Any]]:
    """One binding per executor and role, from the preflight report's step and judge executors."""
    out: list[dict[str, Any]] = []
    for role, names in (("step", step_executors.values()), ("judge", judges.values())):
        for name in dict.fromkeys(names):
            out.append({"executor": name, "role": role, "bare": role == "judge" and bare_judge(name)})
    return out


def check_fire(entry: Mapping[str, Any], environment: Mapping[str, str], profile: Mapping[str, str],
               user_home: Path | None = None) -> Check:
    """The check at a fire (TCK-B19, TCK-B5): the executors and judges recorded in the entry at `add` and `edit`,
    resolved in the tick's own environment; a binding with no credential is the `credential` refusal."""
    bindings = [{"executor": c["executor"], "role": c.get("role") or "step",
                 "bare": c.get("role") == "judge" and bare_judge(str(c["executor"]))}
                for c in entry.get("executors_checked") or []]
    held = held_kinds([str(b["executor"]) for b in bindings], environment, profile, user_home)
    return check(bindings, held, at_fire=True)


def check(bindings: Sequence[Mapping[str, Any]], held: Mapping[str, frozenset[str]], *, at_fire: bool = False) -> Check:
    """TCK-B19: accept the kinds each executor declares; `credential_unattended` for any other kind held,
    `judge_credential` for a `--bare` judge with neither `api_key` nor `cloud`, and at a fire `credential` when nothing
    is held (TCK-B5). A weaker `interactive_login` is a `credential_may_expire` warning. Never a model call."""
    out = Check()
    seen: set[tuple[str, str]] = set()
    for b in bindings:
        executor, role = str(b["executor"]), str(b.get("role") or "step")
        if (executor, role) in seen:
            continue
        seen.add((executor, role))
        kinds = held.get(executor, frozenset())
        caps = DECLARED.get(executor)
        row: dict[str, Any] = {"executor": executor, "role": role, "kinds": sorted(kinds), "result": "ok",
                               "may_expire": False}
        out.checked.append(row)
        if caps is None or not caps.unattended_credentials:
            row["result"] = "not_checked"
            continue
        usable = kinds & caps.unattended_credentials
        problem: tuple[str, str] | None = None
        if not kinds:
            row["result"] = "none"
            if at_fire:
                problem = ("credential", f"{executor}: no credential in the profile or the environment; add {FIX}")
            elif "credential_none" not in out.warnings:  # saved all the same; every fire refuses until one is added
                out.warnings.append("credential_none")
        elif not usable:
            problem = ("credential_unattended", f"{executor}: {', '.join(sorted(kinds))} cannot be used unattended; "
                                                f"it takes {', '.join(sorted(caps.unattended_credentials))}")
        elif role == "judge" and b.get("bare") and not usable & {"api_key", "cloud"}:
            problem = ("judge_credential", f"{executor}: a judge launched with --bare needs {FIX}; "
                                           f"{', '.join(sorted(kinds))} alone does not reach it")
        elif usable == {"interactive_login"}:
            row["may_expire"] = True
            if "credential_may_expire" not in out.warnings:
                out.warnings.append("credential_may_expire")
        if problem is not None:
            row["result"] = "refused"
            row["reason"] = problem[0]
            out.refusal = out.refusal or problem
    return out
