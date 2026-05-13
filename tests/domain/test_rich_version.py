"""Unit tests for :class:`gradle_deps_monitor.domain.RichVersion`."""

from __future__ import annotations

import pytest

from gradle_deps_monitor.domain.rich_version import RichVersion
from gradle_deps_monitor.domain.version import MavenVersion


class TestEffectivePrecedence:
    """``effective`` resolves per Gradle precedence: strictly > require > prefer."""

    def test_strictly_wins_over_require_and_prefer(self) -> None:
        rv = RichVersion(strictly="1.0.0", require="2.0.0", prefer="3.0.0")
        assert rv.effective == MavenVersion("1.0.0")

    def test_require_wins_when_no_strictly(self) -> None:
        rv = RichVersion(require="2.0.0", prefer="3.0.0")
        assert rv.effective == MavenVersion("2.0.0")

    def test_prefer_used_when_alone(self) -> None:
        rv = RichVersion(prefer="3.0.0")
        assert rv.effective == MavenVersion("3.0.0")

    def test_reject_only_has_empty_effective(self) -> None:
        rv = RichVersion(reject=("1.0.0", "1.0.1"))
        assert rv.effective == MavenVersion("")
        assert rv.is_reject_only is True

    def test_reject_combined_with_positive_pin_is_not_reject_only(self) -> None:
        rv = RichVersion(strictly="2.0.0", reject=("1.0.0",))
        assert rv.is_reject_only is False
        assert rv.effective == MavenVersion("2.0.0")


class TestConstructionValidation:
    """The value object refuses to be constructed empty."""

    def test_empty_rich_version_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one of"):
            RichVersion()

    def test_all_keys_none_or_empty_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            RichVersion(strictly=None, require=None, prefer=None, reject=())


class TestImmutability:
    """``RichVersion`` is a frozen value object."""

    def test_is_hashable(self) -> None:
        a = RichVersion(strictly="1.0.0")
        b = RichVersion(strictly="1.0.0")
        assert hash(a) == hash(b)

    def test_equality_by_value(self) -> None:
        assert RichVersion(require="1.0.0", reject=("0.9.0",)) == RichVersion(
            require="1.0.0", reject=("0.9.0",)
        )

    def test_cannot_mutate(self) -> None:
        rv = RichVersion(strictly="1.0.0")
        with pytest.raises(AttributeError):
            rv.strictly = "2.0.0"  # type: ignore[misc]
