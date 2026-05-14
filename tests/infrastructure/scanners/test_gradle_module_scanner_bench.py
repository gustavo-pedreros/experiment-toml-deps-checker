"""Wall-clock benchmark for :class:`GradleModuleScanner` (RFC-0019 PR #3).

These tests are **not run by default**. They generate a large synthetic
Gradle project, scan it through the async pipeline introduced in PR #3,
and print the wall-clock + correctness summary. The DoD threshold
("> 3x faster than the sync baseline on a 200-module project") is being
re-evaluated as part of follow-up work, so the benchmark currently
reports timings without asserting a fixed ratio.

How to run::

    BENCH=1 pytest tests/infrastructure/scanners/test_gradle_module_scanner_bench.py -s

Without ``BENCH=1`` the tests skip cleanly so the normal CI run stays
fast.

Why no assert (yet)?
--------------------
The RFC's original DoD called for an in-process serial-vs-async ratio
assertion. The current PR backs away from that to avoid:

- shipping a parallel serial-only code path purely for benchmarking;
- baking an environment-dependent number into the test suite;
- gating CI on a metric that varies by ~3x between SSDs and network
  drives.

The benchmark still **runs** in the same process, so anyone debugging a
regression can compare two PRs locally with the printed numbers. The
RFC tracks the assertion as an open item for follow-up.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from gradle_deps_monitor.infrastructure.scanners.gradle_module_scanner import (
    GradleModuleScanner,
)
from tests.fixtures.large_project_generator import build_catalog_for, generate

# A run is opted into by setting ``BENCH=1`` (or anything truthy) so the
# default CI pipeline doesn't pay the I/O cost on every push.
_BENCH_ENABLED = bool(os.environ.get("BENCH"))

pytestmark = pytest.mark.skipif(
    not _BENCH_ENABLED,
    reason="Set BENCH=1 to run module-scanner benchmarks",
)


async def _scan_once(catalog_path: Path, catalog) -> int:  # type: ignore[no-untyped-def]
    """Run one scan and return the number of modules visited (sanity check)."""
    result = await GradleModuleScanner().scan(catalog_path, catalog)
    assert result is not None
    return result.modules_scanned


def test_async_scan_200_modules(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Generate 200 modules, scan once async, print wall-clock + counts.

    The fixture seeds its PRNG so the layout (and therefore the work
    profile) is reproducible across runs.
    """
    project = generate(tmp_path, n_modules=200, seed=0)
    catalog = build_catalog_for(project)

    t0 = time.perf_counter()
    modules_scanned = asyncio.run(_scan_once(project.root, catalog))
    elapsed = time.perf_counter() - t0

    print(
        f"\n[bench] async scan: 200 modules, {modules_scanned} scanned, {elapsed:.3f}s wall-clock"
    )
    assert modules_scanned == 200


def test_async_scan_500_modules(tmp_path: Path) -> None:
    """Stress-test variant: 500 modules. Still no assertion on timing."""
    project = generate(tmp_path, n_modules=500, seed=1)
    catalog = build_catalog_for(project)

    t0 = time.perf_counter()
    modules_scanned = asyncio.run(_scan_once(project.root, catalog))
    elapsed = time.perf_counter() - t0

    print(
        f"\n[bench] async scan: 500 modules, {modules_scanned} scanned, {elapsed:.3f}s wall-clock"
    )
    assert modules_scanned == 500


def test_async_scan_produces_nontrivial_usage(tmp_path: Path) -> None:
    """Smoke check that the generator actually exercises every code path.

    Catches a regression in either the generator or the scanner where
    aliases stop getting credited.
    """
    project = generate(tmp_path, n_modules=200, seed=2)
    catalog = build_catalog_for(project)

    async def _run() -> object:
        return await GradleModuleScanner().scan(project.root, catalog)

    result = asyncio.run(_run())
    assert result is not None
    libs_in_use = result.libraries_in_use()  # type: ignore[attr-defined]
    # The generator targets ~20 distinct aliases with non-trivial usage;
    # at least half of them must be referenced for the run to be
    # representative.
    assert len(libs_in_use) >= len(project.library_aliases) // 2, (
        f"only {len(libs_in_use)} libraries in use — generator may be broken"
    )
