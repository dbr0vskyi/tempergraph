#!/usr/bin/env python3
"""Collect the raw, text-free run statistics of one machine into this branch.

Copies the Tier 1 files (ids, enums, numbers, timestamps, costs, token counts,
verdicts, paths) from the tempergraph home folders, the state roots and the
operator folders of a machine into ``machines/<machine-id>/<path under home>``.
Source files are only read, never changed.

The files are kept raw. The only edits are:
  1. each home prefix (``--home`` and every ``--home-alias``) becomes ``~``;
  2. each host name (``--hostname``, default: this host) becomes the machine id;
  3. a ``.jsonl`` file that is being written while it is copied is cut at its
     last complete line.

A file is left out, and named in the report, when it fails a guard:
  - a JSON string value with a newline, more than 200 characters, or more
    than 8 words (free text does not belong in Tier 1);
  - a match of a secret pattern or an e-mail address;
  - a home prefix that is still present after the substitution;
  - a size over 50 MB.

Example (the call that produced machines/pi5-a):

  python3 tools/collect.py --machine-id pi5-a --home ~ \
      --home-alias /Users/dbr0vskyi \
      --tempergraph-home ~/.tempergraph --tempergraph-home ~/tg-runs/verify-home \
      --state-root ~/projects/tempergraph/.tempergraph --state-roots-from-index \
      --ops-dir ~/tg-runs

Standard library only; Python 3.9 or later.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import socket
import sys

# Tier 1 patterns, relative to a tempergraph home or to a state root. Both
# kinds of folder share one layout, so one list serves both.
STORE_PATTERNS = [
    "machine.json",
    "manifest.json",
    "index.json",
    "registry.json",
    "ledger.jsonl",
    "stats/*.jsonl",
    "stats/sessions/*.jsonl",
    "fleet/*.jsonl",
    "runs/*/*/exit.json",
    "runs/*/*/engine.json",
    "runs/*/*/manifest.json",
    "runs/*/*/carry.local.json",
    "runs/*/*/pause-workspace.json",
    "runs/*/*/loop.jsonl",
    "runs/*/*/sessions/*/meta.json",
    "runs/*/*/sessions/*/digest.json",
]
# Tier 1 patterns relative to an operator folder (launch logs and exit codes).
OPS_PATTERNS = ["*.exit"]

SECRET_PATTERNS = [
    r"ghp_[A-Za-z0-9]{20,}",
    r"gho_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"sk-ant-[A-Za-z0-9_-]{10,}",
    r"\bsk-[A-Za-z0-9]{20,}",
    r"Bearer\s+[A-Za-z0-9._-]{8,}",
    r"Authorization",
    r"password",
    r"token\"\s*:\s*\"",
    r"api[_-]?key",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"BEGIN [A-Z ]*PRIVATE KEY",
]
SECRET_RE = re.compile("|".join("(?:%s)" % p for p in SECRET_PATTERNS), re.I)
NEVER = ("credentials", "hosts.yml", ".env", "request_key", "id_rsa", "id_ed25519", ".pem", ".key")
MAX_BYTES = 50 * 1024 * 1024


def text_problem(value, where=""):
    """Return why a parsed JSON value holds free text, or None."""
    if isinstance(value, dict):
        for k, v in value.items():
            p = text_problem(v, where + "." + k if where else k)
            if p:
                return p
    elif isinstance(value, list):
        for v in value:
            p = text_problem(v, where + "[]")
            if p:
                return p
    elif isinstance(value, str):
        if "\n" in value:
            return "%s: string with a newline" % where
        if len(value) > 200:
            return "%s: string of %d characters" % (where, len(value))
        if len(value.split()) > 8:
            return "%s: string of %d words" % (where, len(value.split()))
    return None


def walk_store(root, patterns):
    """Yield (relative path, pattern) of each file under root that matches."""
    root = os.path.realpath(root)
    depth = max(p.count("/") for p in patterns)
    for d, dirs, files in os.walk(root):
        rel_d = os.path.relpath(d, root)
        rel_d = "" if rel_d == "." else rel_d
        level = rel_d.count("/") + 1 if rel_d else 0
        dirs[:] = sorted(x for x in dirs if x not in ("engines", "checkpoints", "node_modules", ".git"))
        if level >= depth:
            dirs[:] = []
        for f in sorted(files):
            rel = os.path.join(rel_d, f) if rel_d else f
            for p in patterns:
                if p.count("/") == rel.count("/") and all(
                    fnmatch.fnmatchcase(a, b) for a, b in zip(rel.split("/"), p.split("/"))
                ):
                    yield rel, p
                    break


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--machine-id", required=True, help="short public name of the machine, e.g. pi5-a")
    ap.add_argument("--home", default=os.path.expanduser("~"), help="home folder of the user")
    ap.add_argument("--home-alias", action="append", default=[], help="another home prefix found in the data (a second machine); becomes ~ too")
    ap.add_argument("--hostname", action="append", default=[], help="host name to replace by the machine id (default: this host)")
    ap.add_argument("--tempergraph-home", action="append", default=[], help="a tempergraph home folder (repeatable)")
    ap.add_argument("--state-root", action="append", default=[], help="a <main checkout>/.tempergraph state root (repeatable)")
    ap.add_argument("--state-roots-from-index", action="store_true", help="add every state root that the index.json of a home lists and that still exists")
    ap.add_argument("--ops-dir", action="append", default=[], help="operator folder with <name>.exit files (repeatable)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."), help="root of the stats branch checkout")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    home = os.path.realpath(os.path.expanduser(a.home))
    out = os.path.realpath(a.out)
    hostnames = a.hostname or [socket.gethostname()]
    prefixes = sorted({home, *[h.rstrip("/") for h in a.home_alias]}, key=len, reverse=True)
    subs = [(p.encode(), b"~") for p in prefixes] + [(h.encode(), a.machine_id.encode()) for h in hostnames if h]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    homes = [os.path.realpath(os.path.expanduser(p)) for p in a.tempergraph_home]
    roots = [os.path.realpath(os.path.expanduser(p)) for p in a.state_root]
    if a.state_roots_from_index:
        for h in homes:
            try:
                with open(os.path.join(h, "index.json")) as fh:
                    listed = [r.get("path") for r in json.load(fh).get("roots", [])]
            except (OSError, ValueError):
                listed = []
            for p in listed:
                if p and os.path.isdir(p) and os.path.realpath(p) not in roots + homes:
                    roots.append(os.path.realpath(p))
    sources = [(p, STORE_PATTERNS, "home") for p in homes]
    sources += [(p, STORE_PATTERNS, "state-root") for p in roots]
    sources += [(os.path.realpath(os.path.expanduser(p)), OPS_PATTERNS, "ops") for p in a.ops_dir]

    entries, skipped, n_subs = [], [], 0
    prefix_res = [re.compile(re.escape(p.encode())) for p in prefixes] + [re.compile(rb"/home/|/Users/")]
    for root, patterns, kind in sources:
        if not os.path.isdir(root):
            skipped.append((root, "source folder is missing"))
            continue
        under = os.path.relpath(root, home)
        outside = under.startswith("..")
        if outside:
            under = "_outside_home/" + root.strip("/")
        for rel, pattern in walk_store(root, patterns):
            src = os.path.join(root, rel)
            dest_rel = "/".join(["machines", a.machine_id, under, rel])
            base = root if outside else "~/" + under
            shown = base + "/" + rel
            if os.path.islink(src) or any(n in os.path.basename(src).lower() for n in NEVER):
                skipped.append((shown, "name is on the never-read list or is a link"))
                continue
            if os.path.getsize(src) > MAX_BYTES:
                skipped.append((shown, "larger than 50 MB"))
                continue
            with open(src, "rb") as fh:
                data = fh.read()
            if rel.endswith(".jsonl") and data and not data.endswith(b"\n"):
                data = data[: data.rfind(b"\n") + 1]  # a line still being written
            for old, new in subs:
                n_subs += data.count(old)
                data = data.replace(old, new)
            problem = None
            if rel.endswith((".json", ".jsonl")):
                try:
                    text = data.decode("utf-8")
                    docs = [json.loads(l) for l in text.splitlines() if l.strip()] if rel.endswith(".jsonl") else [json.loads(text)]
                    for doc in docs:
                        problem = text_problem(doc)
                        if problem:
                            break
                except (ValueError, UnicodeDecodeError) as e:
                    problem = "not valid JSON: %s" % e
            if not problem:
                m = SECRET_RE.search(data.decode("utf-8", "replace"))
                if m:
                    problem = "secret pattern: %r" % m.group(0)[:24]
            if not problem and any(r.search(data) for r in prefix_res):
                problem = "an absolute home path is left after the substitution"
            if problem:
                skipped.append((shown, problem))
                continue
            if not a.dry_run:
                dest = os.path.join(out, dest_rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(data)
            entries.append({
                "path": dest_rel,
                "bytes": len(data),
                "lines": data.count(b"\n"),
                "sha256": hashlib.sha256(data).hexdigest(),
                "source": base + "/" + pattern,
                "source_kind": kind,
                "collected_at": now,
            })

    manifest_path = os.path.join(out, "MANIFEST.json")
    manifest = {"schema_version": 1, "machines": {}, "files": []}
    if os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            manifest = json.load(fh)
    mine = "machines/%s/" % a.machine_id
    manifest["files"] = sorted([f for f in manifest["files"] if not f["path"].startswith(mine)] + entries, key=lambda f: f["path"])
    manifest["machines"][a.machine_id] = {
        "collected_at": now,
        "files": len(entries),
        "bytes": sum(e["bytes"] for e in entries),
        "substitutions": n_subs,
        "left_out": [{"source": s, "reason": r} for s, r in skipped],
    }
    if not a.dry_run:
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True)
            fh.write("\n")

    by = {}
    for e in entries:
        g = by.setdefault(e["source"], [0, 0, 0])
        g[0] += 1
        g[1] += e["bytes"]
        g[2] += e["lines"]
    for k in sorted(by):
        print("%6d files %10d bytes %8d lines  %s" % (*by[k], k))
    print("total: %d files, %d bytes, %d substitutions" % (len(entries), sum(e["bytes"] for e in entries), n_subs))
    for s, r in skipped:
        print("LEFT OUT %s: %s" % (s, r), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
