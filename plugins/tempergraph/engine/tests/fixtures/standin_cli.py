#!/usr/bin/env python3
"""A recorded stand-in of the `claude` CLI for the launcher and conformance tests (EXI-B11).

Behaviour comes from the JSON scenario file named by STANDIN_SCENARIO. The stand-in records its argv,
the environment names it saw and the prompt it read to the scenario's ``record`` path.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    sc: dict = {}
    if os.environ.get("STANDIN_SCENARIO"):
        with open(os.environ["STANDIN_SCENARIO"]) as fh:
            sc = json.load(fh)
    if args[:1] == ["--version"]:
        print(sc.get("version", "2.1.329 (Claude Code)"))
        return 0
    if args[:1] == ["--help"]:
        print(sc.get("help", "--permission-prompts --tools --bare --setting-sources --max-budget-usd"))
        return 0
    if args[:2] == ["auth", "status"]:
        print(json.dumps({"loggedIn": sc.get("logged_in", True)}))
        return 0
    if sc.get("close_stdin"):
        os.close(0)
        time.sleep(sc.get("close_sleep", 0.5))
        return 1
    if sc.get("no_read"):
        time.sleep(sc.get("no_read", 1))
        return 0
    prompt = sys.stdin.read()
    if sc.get("record"):
        with open(sc["record"], "w") as fh:
            json.dump({"argv": args, "prompt": prompt, "env": dict(os.environ)}, fh)
    if sc.get("ignore_term"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if sc.get("graceful_exit"):
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if sc.get("grandchild"):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(sc["grandchild"], "w") as fh:
            fh.write(str(child.pid))
    for item in sc.get("lines", []):
        if isinstance(item, dict) and "sleep" in item and len(item) == 1:
            time.sleep(item["sleep"])
            continue
        sys.stdout.write((item if isinstance(item, str) else json.dumps(item)) + "\n")
        sys.stdout.flush()
    if sc.get("hang"):
        time.sleep(sc["hang"])
    if sc.get("kill_self"):
        os.kill(os.getpid(), signal.SIGKILL)
    return int(sc.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
