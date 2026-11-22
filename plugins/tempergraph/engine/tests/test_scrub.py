"""The scrubber (SEC-B8 to SEC-B11) and the canary helper later tracks reuse (SEC-B2)."""

from __future__ import annotations

from tempergraph.security.scrub import REDACTED, clip, head_tail, scrub

CANARY = "CANARY-7f3a9c1e-do-not-leak"


def test_scrubs_known_secret_shapes() -> None:
    samples = [
        "key sk-ant-api03-abcdefghijklmnop",
        "ghp_" + "a" * 36,
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "password=hunter2hunter2",
        "https://user:pass@example.com/x",
        "AKIAABCDEFGHIJKLMNOP",
    ]
    for s in samples:
        assert REDACTED in scrub(s), s


def test_plain_text_kept() -> None:
    assert scrub("the tests passed in 3.2s") == "the tests passed in 3.2s"


def test_clip_one_line() -> None:
    assert clip("a\nb" + "c" * 300, 20).count("\n") == 0
    assert len(clip("x" * 300, 200)) == 200


def test_head_tail_marker_counts() -> None:
    out = head_tail("a" * 100 + "b" * 100, 80)
    assert "chars omitted" in out and out.startswith("a") and out.endswith("b")
