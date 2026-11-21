"""`tempergraph upgrade <workflow>` and its alias `upgrade-check <workflow> [--stamp]` (WUP §2.1, VER §2.5).

`--check` plans only: read-only and model-free. Without it the verb runs the phases of `package/upgrade.py` on
a branch of the workflow's source. The paired trial (`--trial`, V8) is not built in this release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tempergraph.constants import ExitCode
from tempergraph.package.stamp import check


def add_parsers(sub: Any) -> None:
    for verb in ("upgrade", "upgrade-check"):
        p = sub.add_parser(verb, help="bring a workflow up to the running engine, or only check it")
        p.add_argument("workflow")
        if verb == "upgrade":
            p.add_argument("--check", action="store_true", help="plan only: read-only, model-free")
            p.add_argument("--fail-on", choices=("pending", "never"), default="never")
            p.add_argument("--no-assist", action="store_true", help="transforms only; assisted items stay manual")
            p.add_argument("--executor", help="the executor of the upgrade workflow's sessions")
            p.add_argument("--cap", type=float, default=10.0, help="cost cap of the assist run, in USD")
            p.add_argument("--trial", action="store_true", help="also a paired trial of the result (later release)")
            p.add_argument("--cases", help="the case set of --trial")
            p.add_argument("--bump", action="store_true", help="write the proposed version to the branch")
            p.add_argument("--open-pr", action="store_true", help="open a draft pull request with the report")
            p.add_argument("--continue", dest="continue_id", metavar="UPGRADE_ID",
                           help="go on after a pause, a fix by hand or a failed check")
        p.add_argument("--stamp", action="store_true")
        p.add_argument("--format", choices=("text", "json"), default="json")


def cmd_upgrade(env: Any, a: argparse.Namespace) -> int:
    path = _source(env, a.workflow)
    if path is None:
        env.err.write(f"tempergraph: unknown workflow {a.workflow!r}; `tempergraph workflows list` shows them\n")
        return int(ExitCode.USAGE)
    caps = {n: env.registry.get(n).capabilities() for n in env.registry.available()}
    if a.verb == "upgrade-check" or a.check:
        rep = check(path, caps, stamp=a.stamp, fail_on_pending=getattr(a, "fail_on", "never") == "pending")
        if rep.refused:
            env.err.write(f"tempergraph: {rep.refused}\n")
        env.out.write(json.dumps(rep.to_json(), indent=2, default=str) + "\n")
        return rep.exit_code
    if a.trial or a.cases:
        env.err.write("tempergraph: upgrade --trial is not_in_release; verification runs V1 to V7\n")
        return int(ExitCode.USAGE)
    from tempergraph.package.upgrade import upgrade

    host = None
    if a.open_pr:
        from tempergraph.improve.codehost import GhCodeHost

        host = (getattr(env, "code_host", None) or GhCodeHost)()
    caller = env.caller(a)  # a mutating call: its caller is classified before any write (PRV §2.3)
    assist = getattr(env, "upgrade_assist", None)
    if assist is None and not a.no_assist:
        from tempergraph.builtin import upgrade as builtin

        settings = env.run_settings() if env.run_settings else None

        def assist(job: Any) -> Any:
            return builtin.assist(job, env.registry, caller=caller, settings=settings)
    out = upgrade(path, caps, no_assist=a.no_assist, stamp=a.stamp, bump=a.bump, open_pr=a.open_pr,
                  continue_id=a.continue_id, cap_usd=a.cap, executor=a.executor, host=host,
                  assist=assist)
    if out.refused:
        env.err.write(f"tempergraph: {out.refused}\n")
    env.out.write((text(out) if a.format == "text" else json.dumps(out.to_json(), indent=2, default=str)) + "\n")
    return out.exit_code


def text(rep: Any) -> str:
    lines = [f"upgrade {rep.workflow}: engine {rep.from_engine or 'unstamped'} to {rep.to_engine}"
             + (f", branch {rep.branch}" if rep.branch else "")]
    lines += [f"  before the upgrade: {b}" for b in rep.baseline_errors]
    lines += [f"  {i.item_id}: {i.action}, {i.state}" + (f" by {i.by}" if i.by else "")
              + (f" ({i.reason})" if i.reason else "") for i in rep.items]
    if rep.not_touched:
        lines.append("  not touched: " + ", ".join(rep.not_touched))
    lines += [f"  {v.check}: {v.state}. {v.evidence}" for v in rep.checks]
    if rep.proposed:
        lines.append(f"  proposed version {rep.proposed['version']} ({rep.proposed['level']}), "
                     f"requires_engine {rep.proposed['requires_engine']}")
    lines += [f"  warning: {w}" for w in rep.warnings]
    if rep.exit_code == 4:
        lines.append(f"  fix what failed on the branch, then `tempergraph upgrade {rep.workflow} --continue "
                     f"{rep.upgrade_id}`")
    return "\n".join(lines)


def _source(env: Any, name: str) -> Path | None:
    spec = env.catalog.specs.get(name)
    if spec is not None and spec.package_root is not None:
        return Path(spec.package_root)
    p = Path(name)
    p = p if p.is_absolute() else env.cwd / p
    return p if (p / "tempergraph.json").is_file() else None
