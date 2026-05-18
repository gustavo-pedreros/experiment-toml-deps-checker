# RFC-0031: Bootstrap Composition Tests

**Status:** Implemented
**Created:** 2026-05-18
**Shipped:** 2026-05-18
**Related JTBDs:** JTBD-3 (reproducible runs)
**Depends on:** ADR-0006 (clean architecture), RFC-0029 (cache controls)

## Problem

`src/gradle_deps_monitor/bootstrap.py` is the composition root — the
single module that wires every concrete infrastructure adapter into
the application use cases. Today it has **zero dedicated unit tests**
(audit risk R9). The 232 lines of wiring are exercised only indirectly
through `tests/presentation/test_cli_check.py`, which invokes the full
CLI end-to-end against a fixture catalog.

The indirect coverage hides wiring regressions:

- A bug in `_build_scanner`'s priority logic (e.g. returning OSS Index
  when both creds are present, instead of the composite) would pass
  the CLI test if the test catalog has no advisories.
- An accidental swap of writer filenames (`freeze.md` ↔ `freeze.json`)
  is invisible to the CLI test because both files are written and the
  test only checks the *count* of files.
- The cache-flag wiring added in RFC-0029 (`no_cache`,
  `clear_cache_first`, `cache_ttl_override`) is partially covered by
  the CLI flag tests (those check that flags reach bootstrap), but the
  *effect* on cache root resolution and per-adapter TTL propagation
  is untested at the unit level.

## Goals

1. Unit tests for the four behaviours that aren't visible at the CLI
   integration level:
   - `_build_scanner` priority logic (none / GHSA-only / OSS-only / both).
   - `_prepare_cache_root` lifecycle (default / no-cache / clear-first /
     env-var override).
   - `create_check_command` and `create_diff_command` writers-list
     contracts (count + exact filenames).
   - Opt-in flag wiring (`module_usage`, `risk_score`).

2. Tests run **offline** — no real HTTP calls, no real cache writes
   outside `tmp_path`. Use `monkeypatch.setenv` to redirect both
   credentials and the cache root.

3. No changes to production code beyond what is required to make
   composition observable. `_writers` and `_use_case` are already
   accessed via the conventional pattern of reading single-underscore
   attributes; the project's existing tests follow that convention.

## Non-goals

- Refactoring `bootstrap.py`. The plan explicitly excludes a structural
  rewrite of the composition root.
- Testing the runtime behaviour of the wired-up adapters — that's the
  job of each adapter's own test file.
- Replacing the CLI integration tests in `tests/presentation/test_cli_check.py`.
  Both layers add value: integration tests prove the wiring works
  end-to-end; unit tests catch wiring regressions before they reach
  integration.

## Proposed solution

### New test file: `tests/test_bootstrap.py`

Mirrors the project's existing top-level-test pattern (e.g. how the
domain tests sit directly under `tests/domain/`). Four test classes
matching the four behaviour groups:

```
TestBuildScanner            (5 tests — selection priority)
TestPrepareCacheRoot        (4 tests — lifecycle flags)
TestCreateCheckCommandWiring (6 tests — writers + opt-in flags)
TestCreateDiffCommandWiring  (3 tests — writers + loader)
```

### Test mechanics

- Use `monkeypatch.setenv("GRADLE_DEPS_MONITOR_CACHE_ROOT", str(tmp_path))`
  so adapter constructors (which create `diskcache.Cache(...)` during
  `__init__`) don't pollute the developer's `~/.cache/gradle-deps-monitor`.
- Use `monkeypatch.delenv` for `GITHUB_TOKEN`, `GH_TOKEN`,
  `OSSINDEX_USER`, `OSSINDEX_API_KEY` in scanner-priority tests so
  the host environment doesn't leak.
- Access `CheckCommand._writers` / `CheckCommand._use_case` directly.
  Single-underscore is the project's accepted private convention; the
  CLI test already accesses similar internals.
- Assert writer filenames by index (`writers[0][0] == "freeze.md"`)
  to catch silent reordering bugs that a set-based assertion would miss.

### Coverage matrix

| Behaviour | Test |
|---|---|
| No credentials → `_build_scanner` returns `None` | `test_no_credentials_returns_none` |
| `GITHUB_TOKEN` only → `GitHubAdvisoryScanner` | `test_github_token_only_returns_ghsa` |
| `GH_TOKEN` only → `GitHubAdvisoryScanner` (alias env var) | `test_gh_token_alias_works` |
| OSS Index creds only → `OssIndexScanner` | `test_oss_only_returns_oss` |
| Both → `CompositeScanner` | `test_both_credentials_return_composite` |
| Default cache root | `test_default_cache_root_under_home` |
| `--no-cache` returns tempdir | `test_no_cache_returns_ephemeral` |
| `--clear-cache` empties persistent root | `test_clear_cache_first_purges` |
| Env var beats default | `test_env_var_overrides_persistent_root` |
| `check` writes 5 files | `test_check_command_has_five_writers` |
| Exact writer filenames + order | `test_writer_filenames_and_order` |
| `module_usage=False` → no module scanner | `test_module_usage_default_off` |
| `module_usage=True` → module scanner wired | `test_module_usage_true_wires_scanner` |
| `risk_score=False` → disabled | `test_risk_score_default_off` |
| `risk_score=True` → enabled | `test_risk_score_true_enables` |
| `diff` writes 3 files | `test_diff_command_has_three_writers` |
| Exact diff filenames | `test_diff_filenames_and_order` |
| `diff` uses `JsonSnapshotLoader` | `test_diff_loader_type` |

## Definition of done

- [x] `tests/test_bootstrap.py` created with the 18 tests above.
- [x] All five quality stages pass on Py 3.11 / 3.12 / 3.13 / 3.14 CI matrix.
- [x] No new dependencies, no production-code changes, no schema changes.
- [x] CHANGELOG `[Unreleased]` test-coverage entry under ### Added.

## Out of scope

- A `BootstrapResult` dataclass wrapping the returned commands —
  speculative shape with no current consumer.
- Refactoring `_build_scanner` into a strategy pattern — works fine
  with simple if/elif today; refactor lands when a third option appears.
- Property-based testing of writer ordering — overkill for an 8-element
  list that almost never changes.
