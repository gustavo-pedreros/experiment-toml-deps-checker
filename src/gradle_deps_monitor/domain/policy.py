"""Policy — domain value objects for the CI gatekeeper (RFC-0018 v1).

A :class:`Policy` is a declarative description of *what would fail the
build* and *what would surface as a warning*. The application-layer
:class:`PolicyEvaluator` consumes a :class:`Policy` together with a
:class:`~gradle_deps_monitor.domain.FreezeReport` and produces a
:class:`PolicyResult`. The CLI maps ``PolicyResult.should_fail`` to
exit code ``1``.

Only the v1 flag-driven shape lives here. The v2 expression DSL
(``--fail-on "risk_score > 80"``) is deferred to a follow-up RFC and
is intentionally outside this module's scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from gradle_deps_monitor.domain.severity import CommonSeverity


class WarningCategory(StrEnum):
    """Closed set of categories the CLI accepts for ``--warn-on``.

    Each member maps 1:1 to one of the seven warning-level ``has_*``
    properties on :class:`~gradle_deps_monitor.domain.FreezeReport`.
    Membership is the *contract* the CLI validates against; unknown
    categories cause a usage error (exit code ``2``).
    """

    HIGH_VULNERABILITY = "high-vulnerability"
    COMPLIANCE = "compliance"
    TOOLCHAIN = "toolchain"
    LIBRARY_HEALTH = "library-health"
    DEPRECATED = "deprecated"
    BREAKING = "breaking"
    LICENSE = "license"


@dataclass(frozen=True)
class Policy:
    """Declarative gatekeeper configuration.

    Attributes:
        fail_on_errors: When ``True``, any error-level finding
            (critical CVE / compliance violation / toolchain error /
            license violation) produces a :class:`PolicyViolation`
            and causes :attr:`PolicyResult.should_fail` to be true.
        warn_on: Warning categories the operator wants surfaced as
            an explicit "Policy warnings" section (exit code stays
            ``0``).
    """

    fail_on_errors: bool = False
    warn_on: frozenset[WarningCategory] = field(default_factory=frozenset)


@dataclass(frozen=True)
class PolicyViolation:
    """One policy hit — either a violation (fails the build) or a
    warning (doesn't change exit code).

    The :attr:`category` is the human-readable section name
    (``"security"``, ``"compliance"``, etc.); the :attr:`severity`
    is the unified :class:`CommonSeverity` so consumers don't need to
    know each section's local vocabulary; :attr:`target` is the
    affected entity (library alias, ``"catalog"``, etc.) or ``None``
    when the finding has no concrete target.
    """

    category: str
    severity: CommonSeverity
    message: str
    target: str | None = None


@dataclass(frozen=True)
class PolicyResult:
    """Outcome of evaluating a :class:`Policy` against a report.

    :attr:`violations` are the findings that the policy declares
    must-fail; :attr:`warnings` are surfaced but never change the
    exit code.
    """

    violations: tuple[PolicyViolation, ...] = ()
    warnings: tuple[PolicyViolation, ...] = ()

    @property
    def should_fail(self) -> bool:
        """``True`` when at least one violation was recorded."""
        return bool(self.violations)
