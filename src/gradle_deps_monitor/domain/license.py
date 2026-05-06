"""License domain model for RFC-0009 License Audit.

Each library in the version catalog is classified into a :class:`LicenseTier`.
Tier assignment is derived from the ``<licenses>`` block in the Maven POM of
the *pinned* version.  When no license information can be determined the tier
defaults to :attr:`~LicenseTier.UNKNOWN`.

Only non-permissive findings (WEAK_COPYLEFT, STRONG_COPYLEFT, UNKNOWN) are
stored in :class:`LicenseAudit`; the count of permissive libraries is derived
from ``libraries_audited - len(findings)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LicenseTier(StrEnum):
    """Risk tier assigned to a library's declared license.

    Members are ordered from least to most restrictive so that comparisons
    and sorting work intuitively (``PERMISSIVE < WEAK_COPYLEFT < …``).
    """

    PERMISSIVE = "permissive"
    WEAK_COPYLEFT = "weak_copyleft"
    STRONG_COPYLEFT = "strong_copyleft"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LicenseFinding:
    """A library whose license tier warrants attention.

    :param alias: Version-catalog alias (e.g. ``"retrofit"``).
    :param coordinate: Maven coordinate ``group:artifact``.
    :param version: Pinned version string.
    :param license_name: Raw ``<name>`` from the POM ``<licenses>`` block,
        or ``None`` when no license element was present.
    :param license_url: Raw ``<url>`` from the POM ``<licenses>`` block,
        or ``None`` when absent.
    :param tier: Classified :class:`LicenseTier`.
    """

    alias: str
    coordinate: str
    version: str
    license_name: str | None
    license_url: str | None
    tier: LicenseTier


@dataclass(frozen=True)
class LicenseAudit:
    """Aggregate result of a license scan across all catalog libraries.

    :param findings: Tuple of non-permissive :class:`LicenseFinding` objects
        (WEAK_COPYLEFT, STRONG_COPYLEFT, or UNKNOWN tier).
        Sorted by ``(tier, alias)``.
    :param libraries_audited: Total number of libraries that were checked
        (including those that are permissive and therefore not in *findings*).
    """

    findings: tuple[LicenseFinding, ...]
    libraries_audited: int

    @property
    def permissive_count(self) -> int:
        """Number of libraries whose license is permissive."""
        return self.libraries_audited - len(self.findings)

    @property
    def flagged_count(self) -> int:
        """Number of non-permissive findings."""
        return len(self.findings)

    @property
    def has_violations(self) -> bool:
        """``True`` when at least one library has a STRONG_COPYLEFT license."""
        return any(f.tier == LicenseTier.STRONG_COPYLEFT for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        """``True`` when at least one finding is WEAK_COPYLEFT or UNKNOWN."""
        return any(
            f.tier in (LicenseTier.WEAK_COPYLEFT, LicenseTier.UNKNOWN) for f in self.findings
        )
