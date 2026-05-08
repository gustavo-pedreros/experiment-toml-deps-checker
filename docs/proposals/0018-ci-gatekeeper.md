# RFC-0018: CI Gatekeeper (Policy Enforcement)

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-1 (CI automation), JTBD-2 (security gate)
**Depends on:** none

## Problem

Currently, the tool acts as an informational reporting suite. While it provides high-signal data about risks and health, it does not provide an automated way to "break the build" (exit with non-zero code) based on project-specific policies. Teams have to write custom wrappers or scripts to parse the `freeze.json` to enforce quality gates.

## Proposed solution

Introduce a `--fail-on` CLI flag for the `check` command. This flag allows users to define failure thresholds directly in their CI pipeline or `gradle-deps-monitor.toml` configuration.

### Policy Syntax

The flag will support simple expression-like strings:
- `--fail-on "risk_score > 80"`: Fails if any library has a risk score above 80.
- `--fail-on "severity == error"`: Fails if any finding with `ERROR` common severity is detected.
- `--fail-on "drift == major"`: Fails if any major version drift is detected.

### Multiple Policies

Users can provide the flag multiple times. The tool will exit with code `1` if *any* of the policies are violated.

```bash
gradle-deps-monitor check gradle --fail-on "risk_score > 90" --fail-on "severity == error"
```

## Implementation Plan

### Phase 1: Domain Logic
- Create a `PolicyEvaluator` in the application layer.
- Define a small set of supported metrics: `risk_score`, `severity`, `drift`, `vulnerability_severity`.

### Phase 2: CLI Integration
- Add the `fail_on` parameter to the `check` command in `cli.py`.
- Update `CheckCommand` to evaluate policies after report generation but before returning to the CLI.

### Phase 3: Configuration Support
- Update `AppConfig` and the TOML loader to support a `[policies]` section.

## Alternatives considered

- **Shell-based evaluation:** Rejected. Parsing JSON with `jq` in every CI pipeline is error-prone and duplicates logic.
- **Hardcoded failure logic:** Rejected. Different projects have different risk tolerances (e.g., a greenfield project vs. a legacy one).
