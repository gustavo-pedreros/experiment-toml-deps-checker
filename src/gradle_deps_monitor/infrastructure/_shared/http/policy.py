"""HTTP policy DTO (RFC-0030).

One immutable dataclass capturing every operational tunable the
shared HTTP layer cares about. Per-adapter values are set at the
adapter's call site (e.g. ``HttpPolicy(timeout_seconds=10.0)`` for
Maven registries); the dataclass defaults are the conservative
fallback for any caller that doesn't override.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpPolicy:
    """Operational tunables shared by every HTTP adapter.

    :param timeout_seconds: ``httpx.AsyncClient`` timeout applied to
        all request stages (connect / read / write / pool). Single
        value for simplicity — matches the timeouts the adapters
        already use today.
    :param max_attempts: Total request attempts including the first
        try. ``max_attempts=3`` means initial + 2 retries.
    :param backoff_base_seconds: Base for the exponential backoff
        delay between retries. Actual delay is
        ``min(backoff_max_seconds, backoff_base_seconds * 2**(attempt-1))``
        with full jitter applied on top.
    :param backoff_max_seconds: Upper bound for any single backoff
        delay. Prevents pathological hour-long waits on a misbehaving
        upstream.
    :param max_concurrency: Maximum in-flight requests an adapter
        should issue at once. Consumed by adapter-level
        ``asyncio.Semaphore`` instances — the transport itself does
        not enforce this, because httpx transports are shared across
        concurrent tasks and tracking per-transport state would
        require synchronisation we don't otherwise need.
    """

    timeout_seconds: float = 30.0
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    max_concurrency: int = 20

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {self.timeout_seconds!r}")
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts!r}")
        if self.backoff_base_seconds < 0:
            raise ValueError(
                f"backoff_base_seconds must be >= 0, got {self.backoff_base_seconds!r}"
            )
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ValueError(
                "backoff_max_seconds must be >= backoff_base_seconds "
                f"({self.backoff_max_seconds!r} < {self.backoff_base_seconds!r})"
            )
        if self.max_concurrency < 1:
            raise ValueError(f"max_concurrency must be >= 1, got {self.max_concurrency!r}")
