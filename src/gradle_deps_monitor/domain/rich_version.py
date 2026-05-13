"""Gradle "rich version" value object (RFC-0020).

Gradle Version Catalogs support version *tables* that carry richer
information than a single string. The four recognised keys are:

- ``strictly`` — hard pin; equivalent to forbidding any other version.
- ``require``  — declared baseline.
- ``prefer``   — soft preference; resolved when nothing stronger applies.
- ``reject``   — list of versions to forbid.

This module defines :class:`RichVersion`, the domain value object that
captures those keys plus a derived :attr:`effective` version used by
checkers for drift / compatibility comparisons.

A plain-string declaration in a catalog (``version = "1.2.3"``) does
**not** flow through :class:`RichVersion`. Only library entries that
genuinely use one of the four rich keys produce a :class:`RichVersion`
instance. This keeps the wire format additive: existing libraries
serialise unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from gradle_deps_monitor.domain.version import MavenVersion


@dataclass(frozen=True)
class RichVersion:
    """Immutable representation of a Gradle rich-version declaration.

    At least one of ``strictly``, ``require``, ``prefer``, or ``reject``
    must be set; constructing an empty :class:`RichVersion` is a
    programming error.

    The :attr:`effective` property resolves the canonical version per
    Gradle precedence (``strictly`` > ``require`` > ``prefer``). When
    only ``reject`` is set, ``effective`` falls back to an empty
    :class:`MavenVersion`, matching the sentinel used elsewhere in the
    domain for "no positive pin" cases (e.g. BoM-managed entries).
    """

    strictly: str | None = None
    require: str | None = None
    prefer: str | None = None
    reject: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (self.strictly or self.require or self.prefer or self.reject):
            raise ValueError(
                "RichVersion requires at least one of strictly/require/prefer/reject; "
                "plain-string versions should not be wrapped in RichVersion."
            )

    @property
    def effective(self) -> MavenVersion:
        """Resolve the rich declaration to a comparable :class:`MavenVersion`.

        Precedence: ``strictly`` > ``require`` > ``prefer``. When only
        ``reject`` is set, returns ``MavenVersion("")`` — the same
        sentinel used for BoM-managed entries — and the library is
        excluded from drift analysis by upstream checkers.
        """
        if self.strictly is not None:
            return MavenVersion(self.strictly)
        if self.require is not None:
            return MavenVersion(self.require)
        if self.prefer is not None:
            return MavenVersion(self.prefer)
        return MavenVersion("")

    @property
    def is_reject_only(self) -> bool:
        """``True`` when the entry declares rejections but no positive pin."""
        return (
            self.strictly is None
            and self.require is None
            and self.prefer is None
            and bool(self.reject)
        )
