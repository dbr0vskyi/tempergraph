"""The CLI shim in `~/.tempergraph/bin/` and the `PATH` block (UPD-B11, UPD-B12, UPD-B13, UPD-B18, UPD-B19 step 4).

The shim is content-independent of the release: it reads `engines/current.json` and execs that
environment's interpreter; with no complete environment it exits 127. `TEMPERGRAPH_PYTHON` overrides
the lookup (CI). Release 1 is macOS and Linux only, so no Windows wrapper is written.
"""

from __future__ import annotations

import os
from pathlib import Path

MARKER = "# >>> tempergraph >>>"
END = "# <<< tempergraph <<<"

SHIM = r'''#!/bin/sh
# tempergraph CLI shim (UPD-B11, UPD-B12, UPD-B13): written by `tempergraph install`; reads engines/current.json.
home="${TEMPERGRAPH_HOME:-$HOME/.tempergraph}"
if [ -n "$TEMPERGRAPH_PYTHON" ]; then
  exec "$TEMPERGRAPH_PYTHON" -m tempergraph "$@"
fi
env=$(sed -n 's/^ *"path": *"\(.*\)",\{0,1\} *$/\1/p' "$home/engines/current.json" 2>/dev/null | head -n 1)
if [ -z "$env" ] || [ ! -f "$env/.complete" ] || [ ! -x "$env/bin/python" ]; then
  echo "tempergraph: no engine is installed; run the tempergraph plugin's launcher: bin/tempergraph install" >&2
  exit 127
fi
exec "$env/bin/python" -m tempergraph "$@"
'''


def shim_path(home: Path) -> Path:
    return home / "bin" / "tempergraph"


def write_shim(home: Path) -> bool:
    """Write the shim when its content differs; True when it was written."""
    path = shim_path(home)
    if path.is_file() and path.read_text(encoding="utf-8") == SHIM:
        return False
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(SHIM, encoding="utf-8")
    tmp.chmod(0o755)
    tmp.replace(path)
    return True


def shell_file(shell: str | None = None, user_home: Path | None = None) -> tuple[str, Path]:
    """The detected shell and the file its `PATH` block belongs in."""
    name = Path(shell or os.environ.get("SHELL") or "sh").name
    h = user_home or Path.home()
    if name == "zsh":
        return name, h / ".zshrc"
    if name == "bash":
        return name, h / ".bashrc"
    if name == "fish":
        return name, h / ".config" / "fish" / "config.fish"
    return name, h / ".profile"


def path_block(home: Path, shell: str) -> str:
    bin_dir = home / "bin"
    line = f"fish_add_path {bin_dir}" if shell == "fish" else f'export PATH="{bin_dir}:$PATH"'
    return f"{MARKER}\n{line}\n{END}\n"


def on_path(home: Path) -> bool:
    want = str((home / "bin").resolve())
    return any(str(Path(p).resolve()) == want for p in os.environ.get("PATH", "").split(os.pathsep) if p)


def add_to_path(home: Path, shell: str | None = None, user_home: Path | None = None) -> tuple[Path, bool]:
    """Append the block after a marker check, so a second run adds nothing; True when it was appended."""
    name, file = shell_file(shell, user_home)
    text = file.read_text(encoding="utf-8") if file.is_file() else ""
    if MARKER in text:
        return file, False
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a", encoding="utf-8") as fh:
        fh.write(("\n" if text and not text.endswith("\n") else "") + path_block(home, name))
    return file, True
