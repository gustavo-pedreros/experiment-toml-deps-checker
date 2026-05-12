# RFC-0018: CI Gatekeeper (Policy Enforcement)

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-1 (CI automation), JTBD-2 (security gate)
**Depends on:** none

## Problem

The tool today is an informational reporting suite. It produces
high-signal data about risks and health, but it lacks a native way
to **break the build** based on project-specific quality gates.

Teams wanting to enforce policies (e.g. "no critical CVEs allowed")
must write custom scripts that parse `freeze.json`, which is fragile
and duplicates logic across organisations.

Worth noting: `FreezeReport` (see `src/gradle_deps_monitor/domain/report.py`)
already exposes **11 `has_*` boolean properties** that summarise the
state of each bounded context:

- Error-level (4): `has_critical_vulnerabilities`,
  `has_compliance_violations`, `has_toolchain_errors`,
  `has_license_violations`.
- Warning-level (7): `has_high_vulnerabilities`,
  `has_compliance_warnings`, `has_toolchain_warnings`,
  `has_high_health_findings`, `has_breaking_upgrades`,
  `has_license_warnings`, `has_deprecated_libraries`.

The domain model is therefore already rich enough for a meaningful
v1 gatekeeper — we just don't expose it.

## Proposed solution

Introduce **Policy Enforcement** into the `check` command in two
versions:

- **v1 (this RFC, ships as part of Phase 1):** flag-driven, no DSL.
  Consume the existing `has_*` properties to support a *fail* mode and
  a *warn* mode. Surface violations through CI-friendly annotations.
- **v2 (deferred):** expression DSL (`--fail-on "risk_score > 80 AND severity == error"`)
  and persisted `[policy]` section in `gradle-deps-monitor.toml`.

### 1. v1 — Flag-driven gatekeeper

Two flags on `check`:

```
--fail-on-errors           Exit 1 if any of the 4 error-level has_* is true.
--warn-on <category,...>   Print a highlighted warning section; do NOT
                           change exit code. Categories map 1:1 to the
                           7 warning-level has_* properties (e.g.
                           "deprecated,breaking,license").
```

Behaviour matrix:

| Condition                                  | Exit code | Console section          |
| ------------------------------------------ | --------- | ------------------------ |
| No findings                                | `0`       | (none)                   |
| Only warnings, `--warn-on` matches         | `0`       | "Policy warnings"        |
| Error-level finding, `--fail-on-errors`    | `1`       | "Policy violations"      |
| Usage error (bad flags, unknown category)  | `2`       | stderr                   |
| Config error (TOML unreadable, etc.)       | `3`       | stderr                   |

Exit codes intentionally follow the `sysexits.h` convention used by
most CI tooling: `0` success, `1` policy violation, `2` user/usage
error, `3` configuration error.

### 2. v1 — CI-aware output

The `check` command auto-detects GitHub Actions (`GITHUB_ACTIONS=true`)
and emits annotations alongside the human-readable section:

```
::error file=gradle/libs.versions.toml::Compliance violation: <message>
::warning file=gradle/libs.versions.toml::Library marked deprecated: <alias>
```

This is ~10 lines in the presentation layer and removes the need for
a Phase-2 spike. Bitrise gets the same content via stdout; a dedicated
formatter for other CI providers is out of scope for v1.

### 3. v2 — Expression DSL (deferred)

After v1 ships, evolve the flag into a small predicate language:

```
--fail-on "risk_score > 80"
--fail-on "severity == error"
--fail-on "vulnerability == critical"
```

Persisted equivalent in `gradle-deps-monitor.toml`:

```toml
[policy]
fail_on_error = true
max_risk_score = 75
disallow_major_drift = ["androidx.*"]
```

### 4. Domain model

`Policy` and `PolicyResult` belong in **`domain/policy.py`** as immutable
value objects:

```python
@dataclass(frozen=True)
class Policy:
    fail_on_errors: bool
    warn_on: frozenset[WarningCategory]  # enum, closed set

@dataclass(frozen=True)
class PolicyViolation:
    category: str           # e.g. "compliance", "toolchain"
    severity: CommonSeverity
    message: str
    target: str | None      # alias, module path, or None for catalog-level

@dataclass(frozen=True)
class PolicyResult:
    violations: tuple[PolicyViolation, ...]
    warnings: tuple[PolicyViolation, ...]

    @property
    def should_fail(self) -> bool:
        return bool(self.violations)
```

`PolicyEvaluator` lives in **`application/`** and only orchestrates:
it reads a `FreezeReport` + `Policy`, and produces a `PolicyResult`.
The CLI layer maps `PolicyResult.should_fail` to exit code `1`.

This split keeps the rule definitions (domain) testable in isolation
from the orchestration (application) and from CLI plumbing
(presentation), consistent with ADR-0006.

## Tracer Bullet Path (ADR-0009)

The risk we want to de-risk is the **"report → policy → exit code"
plumbing**. The tracer PR contains:

1. **Domain:** introduce `Policy`, `PolicyResult`, `PolicyViolation` as
   the value objects above, with `fail_on_errors=True` consuming only
   `has_critical_vulnerabilities` for the first cut.
2. **Application:** skeletal `PolicyEvaluator.evaluate(report, policy)`.
3. **Presentation:** wire `--fail-on-errors` into the `check` command;
   propagate `PolicyResult.should_fail` to the CLI exit code; print a
   "Policy violations" section.
4. **CI annotation hook:** emit one `::error file=...::` line when the
   environment is GitHub Actions (env-detection helper, no logic on
   formatting yet — just one well-formed line).
5. **Composition Root:** register `PolicyEvaluator` in `bootstrap.py`,
   gated by the flag.
6. **Minimal Output:** integration test fixture with one critical CVE
   → assert exit code `1`, presence of the violations section, and
   presence of the GHA annotation when `GITHUB_ACTIONS=true`.

*Confirms that the gatekeeper sits correctly between report generation
and CLI exit, in domain-respecting layers, and that CI annotations
flow without a second pass.*

## Implementation Plan

### Phase 1 — Tracer (single PR)
- `Policy`, `PolicyResult`, `PolicyViolation` in `domain/`.
- `PolicyEvaluator` consuming `has_critical_vulnerabilities`.
- `--fail-on-errors` flag, exit code `1`.
- GitHub Actions annotation emitter (~10 lines).
- Integration test for exit code + annotation.

### Phase 2 — v1 completion
- Extend `PolicyEvaluator` to consume the remaining 3 error-level
  `has_*` properties.
- `--warn-on <categories>` flag mapped to the 7 warning-level `has_*`
  properties.
- Highlighted "Policy warnings" section (exit code stays `0`).
- Exit codes `2` (usage) and `3` (config) wired in `cli.py`.

### Phase 3 — v2 (deferred RFC follow-up)
- Expression parser (evaluate `simpleeval` vs hand-rolled splitter).
- `[policy]` section in `gradle-deps-monitor.toml`.
- Per-library / per-group overrides ("allow major drift for group X").

### Optional Spikes
- **Spike:** confirm the chosen expression parser strategy on a real
  set of policy strings *(only triggered when starting Phase 3).*
- **Spike:** evaluate CI providers beyond GitHub Actions / Bitrise
  (GitLab CI, CircleCI) to see whether a pluggable annotation interface
  is worth introducing *(only triggered if user demand appears).*

## Alternatives considered

- **Shell-based evaluation via `jq` on `freeze.json`:** Rejected.
  Fragile and lacks access to the rich domain model that already
  knows what an "error" is.
- **Hardcoded failure logic (always fail on critical CVE):**
  Rejected. Different projects need different thresholds
  (legacy vs greenfield), and `--fail-on-errors` is opt-in by design.
- **Ship the DSL directly (skip v1):** Rejected. We have a tested
  domain model with `has_*` booleans today; covering 80 % of the
  value with a boolean flag is a strictly smaller, lower-risk first
  delivery.

## Success metrics

- A user can break the CI build using a single CLI flag.
- Zero false positives: `check` exits `0` when no policy is violated.
- Violation messages point unambiguously to the offending library /
  finding.
- On GitHub Actions, violations appear inline in the PR diff via
  workflow annotations.

## Schema impact

`none` — `freeze.json` is unchanged. The policy result is presentation-
and exit-code-only.

## Rollback strategy

The flag is opt-in: omitting `--fail-on-errors` (and not setting the
flag in any future `[policy]` block) restores the pre-RFC behaviour
exactly. Revert order, if needed:

1. Revert the presentation PR → exit code falls back to `0`; the rest
   of the tool continues to work because no other module depends on
   `PolicyEvaluator`.
2. Revert the domain PR → value objects disappear with no cascading
   damage because nothing else imports them.

## PR budget

Estimated **3 PRs** from tracer to v1 DoD:

1. Tracer (domain types + `--fail-on-errors` for critical CVEs + GHA
   annotation for one finding).
2. Extend to the other 3 error-level `has_*` properties; add
   `--warn-on` and the warnings section.
3. Wire exit codes `2` and `3` for usage / config errors.

v2 (DSL + persisted `[policy]`) is tracked separately and is not
counted here.

## Definition of Done (DoD)

### v1 (this RFC)
- [ ] **Integration:** Policy evaluation wired in the **Composition
  Root** (`bootstrap.py`) and executes after report generation.
- [ ] **Architecture:** `Policy` / `PolicyResult` in `domain/`,
  `PolicyEvaluator` in `application/`, CLI mapping in `presentation/`,
  consistent with ADR-0006.
- [ ] **Functionality:** `check --fail-on-errors` exits `1` when any
  of the 4 error-level `has_*` properties is true.
- [ ] **Warnings:** `check --warn-on <categories>` prints the warnings
  section without changing exit code.
- [ ] **CI integration:** GitHub Actions workflow annotations are
  emitted for both errors and warnings when `GITHUB_ACTIONS=true`.
- [ ] **Exit codes:** `0` / `1` / `2` / `3` semantics implemented and
  documented in the user guide.
- [ ] **Testing:** Integration tests cover at least one violation per
  error category, a warn-only scenario, and the GitHub Actions
  annotation output.

### v2 (deferred)
- DSL parser, `[policy]` section, per-group overrides.
