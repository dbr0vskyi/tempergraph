"""The pattern scrubber (SEC-B8 to SEC-B11).

Patterns are a floor, not the control: the publish boundary is a file boundary. A scrubber that raises
drops the text and returns a fixed word, and the run continues (OVR-B4, SEC-B7, SEC-B8).
"""

from __future__ import annotations

import re

REDACTED = "[redacted]"
DROPPED = "[scrub-failed]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|auth)\b(\s*[:=]\s*)(\"?)[^\s\"']{6,}"),
    re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@"),  # credentials in a URL
)


def scrub(text: str | None) -> str:
    if not text:
        return text or ""
    try:
        out = text
        for pat in _PATTERNS:
            if pat.groups >= 2:
                out = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}", out)
            else:
                out = pat.sub(REDACTED, out)
        return out
    except Exception:
        return DROPPED


def clip(text: str | None, limit: int) -> str:
    """Clip to ``limit`` chars; one line, scrubbed."""
    one = scrub((text or "").replace("\r", " ").replace("\n", " ")).strip()
    return one if len(one) <= limit else one[: max(0, limit - 1)] + "…"


def head_tail(text: str, limit: int, marker: str = "⟨… {n} chars omitted …⟩") -> str:
    """Keep head and tail around an exact marker with the omitted count (JDG-B3, JDG-B13, JDG-B11)."""
    if len(text) <= limit:
        return text
    keep = max(0, limit - 40)
    head = keep // 2
    tail = keep - head
    omitted = len(text) - head - tail
    return text[:head] + marker.format(n=omitted) + text[len(text) - tail :]
