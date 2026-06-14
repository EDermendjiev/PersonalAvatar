"""Per-conversation moving-window rate limiter.

Caps each ``conversation_id`` to 20 chat messages per minute using the ``limits``
package with an in-memory backend. In-process state is sufficient because
OpenRouter caps overall spend and a browser's requests stick to one machine
(SPEC Q&A #12 / CONTRACT.md §7).
"""

from __future__ import annotations

from limits import RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from . import config

_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)
_limit = RateLimitItemPerMinute(config.RATE_LIMIT_PER_MINUTE)


def allow(conversation_id: str) -> bool:
    """Consume one unit for ``conversation_id``; return False when over the limit.

    ``hit`` both tests and records the request atomically, returning True while
    the window has capacity and False once it is exhausted.
    """
    return _limiter.hit(_limit, "chat", conversation_id)


def reset() -> None:
    """Clear all rate-limit state. Intended for tests."""
    _storage.reset()
