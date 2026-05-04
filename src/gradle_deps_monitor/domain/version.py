"""Maven version value object and stability classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# Patterns ordered from most to least specific.
_SNAPSHOT = re.compile(r"snapshot", re.IGNORECASE)
_ALPHA = re.compile(r"alpha", re.IGNORECASE)
_BETA = re.compile(r"beta", re.IGNORECASE)
_RC = re.compile(r"\brc\d*\b", re.IGNORECASE)
_DEV = re.compile(r"\bdev\d*\b", re.IGNORECASE)
_NUMERIC_ONLY = re.compile(r"^\d+(\.\d+)*$")


class Stability(StrEnum):
    """Coarse-grained stability tier of a Maven version string."""

    STABLE = "stable"
    RC = "rc"
    BETA = "beta"
    ALPHA = "alpha"
    DEV = "dev"
    SNAPSHOT = "snapshot"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MavenVersion:
    """Immutable value object wrapping a raw Maven version string.

    Parsing stays intentionally simple: no full Maven version-ordering
    semantics. The :attr:`stability` property covers the common Android/
    Kotlin pre-release naming conventions (alpha, beta, rc, dev, SNAPSHOT).
    """

    raw: str

    @property
    def stability(self) -> Stability:
        if _SNAPSHOT.search(self.raw):
            return Stability.SNAPSHOT
        if _ALPHA.search(self.raw):
            return Stability.ALPHA
        if _BETA.search(self.raw):
            return Stability.BETA
        if _RC.search(self.raw):
            return Stability.RC
        if _DEV.search(self.raw):
            return Stability.DEV
        if _NUMERIC_ONLY.match(self.raw):
            return Stability.STABLE
        return Stability.UNKNOWN

    @property
    def is_stable(self) -> bool:
        return self.stability is Stability.STABLE

    @property
    def is_prerelease(self) -> bool:
        return self.stability not in {Stability.STABLE, Stability.UNKNOWN}

    def __str__(self) -> str:
        return self.raw
