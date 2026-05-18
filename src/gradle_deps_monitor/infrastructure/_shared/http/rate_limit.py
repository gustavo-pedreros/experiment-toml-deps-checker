"""GitHub-style rate-limit detection (RFC-0030).

Lifted verbatim from ``infrastructure/fetchers/changelog_fetcher.py``,
where the same heuristic was defined as a private ``_is_rate_limited``
helper. The changelog fetcher continues to expose the
``_is_rate_limited`` alias for compatibility with existing test
imports.
"""

from __future__ import annotations

import httpx


def is_rate_limited(response: httpx.Response) -> bool:
    """Return ``True`` for documented GitHub-style rate-limit responses.

    Two conditions count as rate-limit hits:

    - HTTP 429 (secondary / abuse-detection limit). Any upstream that
      uses 429 has been told to back off explicitly.
    - HTTP 403 with the response header ``X-RateLimit-Remaining: 0``
      (primary limit exhausted; GitHub's documented signal).

    Plain 403 *without* the rate-limit header is intentionally NOT
    counted — those can come from auth failures, blocked content, or
    other causes that don't map to "set a token to fix this".
    """
    if response.status_code == 429:
        return True
    if response.status_code == 403:
        return bool(response.headers.get("X-RateLimit-Remaining") == "0")
    return False
