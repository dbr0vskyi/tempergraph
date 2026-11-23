#!/usr/bin/env bash
# Create or update every label of .github/labels.yml in a repository (default: this one's origin).
# Needs a signed-in `gh` and Python 3 with PyYAML. Labels not in the file are left alone.
set -euo pipefail
repo="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
here="$(cd "$(dirname "$0")" && pwd)"
python3 - "$here/labels.yml" <<'PY' | while IFS=$'\t' read -r name color desc; do
import sys, yaml
for l in yaml.safe_load(open(sys.argv[1])):
    print(f"{l['name']}\t{l['color']}\t{l['description']}")
PY
  gh label create "$name" --repo "$repo" --color "$color" --description "$desc" --force
done
