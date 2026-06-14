"""Tests for ``app.ratelimit`` — the per-conversation moving-window limiter.

Uses the real ``limits`` in-memory limiter (no network). The autouse
``reset_ratelimit`` fixture (conftest) clears state around each test
(CONTRACT.md §7, SPEC Q&A #12).
"""

from __future__ import annotations

from app import config, ratelimit


def test_allows_up_to_limit_then_blocks():
    cid = "conv-a"
    allowed = [ratelimit.allow(cid) for _ in range(config.RATE_LIMIT_PER_MINUTE)]
    assert all(allowed), "all of the first N requests must be allowed"
    # The very next request in the same window is blocked.
    assert ratelimit.allow(cid) is False


def test_limit_is_per_conversation():
    a, b = "conv-a", "conv-b"
    for _ in range(config.RATE_LIMIT_PER_MINUTE):
        assert ratelimit.allow(a) is True
    assert ratelimit.allow(a) is False
    # A different conversation has its own fresh budget.
    assert ratelimit.allow(b) is True


def test_reset_clears_state():
    cid = "conv-c"
    for _ in range(config.RATE_LIMIT_PER_MINUTE):
        ratelimit.allow(cid)
    assert ratelimit.allow(cid) is False
    ratelimit.reset()
    assert ratelimit.allow(cid) is True


def test_default_limit_is_twenty():
    assert config.RATE_LIMIT_PER_MINUTE == 20
