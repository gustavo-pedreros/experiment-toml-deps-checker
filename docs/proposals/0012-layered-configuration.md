# RFC-0012: Layered configuration

**Status:** Shipped
**Created:** 2026-05-06
**Related JTBDs:** Cross-cutting infrastructure (no specific JTBD)
**Depends on:** none

## Problem

Several shipped features depend on values that are currently
hard-coded with no path for per-project overrides:

- **Risk score weights and thresholds** ([RFC-0008](0008-risk-score.md))
  are configurable in the proposal text, but the `score_libraries`
  function falls back to defaults because no loader exists. The
  fintech-vs-indie-app distinction promised by the RFC is
  unreachable today.
- **Cache TTL** for the on-disk HTTP cache is fixed at 1 hour.
  Teams running a freeze across multiple modules in a single CI
  pipeline would benefit from a longer TTL.
- **Default output directory** is hard-coded to `./reports`.
- **Library health KB extensions** ([RFC-0006](0006-library-health-and-deprecation.md))
  can only be added by editing the bundled YAML file.

The roadmap's "Cross-cutting infrastructure" section already lists
"Layered configuration (`config.toml` + per-project overrides)" as
a goal, but it has never had a dedicated proposal.

## Proposed solution

Introduce a single `gradle-deps-monitor.toml` file at the project
root (sibling of the `gradle/` directory). The file is **optional**
— absence is equivalent to an empty file, and built-in defaults
apply.

### Initial schema

```toml
[risk_weights]
outdatedness = 25
cve          = 30
abandonment  = 15
blast_radius = 15
compliance   = 10
license      = 5

[risk_thresholds]
critical = 70
high     = 50
medium   = 30

[cache]
ttl_seconds = 3600

[output]
default_dir = "freeze-reports"

[library_health]
extra_kb_path = "ops/extra-library-health.yaml"  # optional
```

All sections are optional; unknown sections produce a warning but
do not abort the run.

### Resolution order

For any setting:

1. Built-in default
2. `gradle-deps-monitor.toml` at project root
3. Environment variable (where applicable, e.g. `GITHUB_TOKEN`)
4. CLI flag

Higher steps override lower ones.

### Implementation outline

- New module `infrastructure/config/loader.py` with a single
  `load_config(project_root: Path) -> AppConfig` entry point.
- New domain DTO `domain/config.py` (`AppConfig`,
  `RiskWeights` reused from `domain/risk_score.py`,
  `RiskThresholds` reused).
- `bootstrap.create_check_command` accepts an `AppConfig` and wires
  the values into `GenerateFreezeReport` and the scorer.
- Validation reuses `RiskWeights.__post_init__` (sum-to-100 check
  raises a clear `ConfigError` referencing the file path).

## Alternatives considered

- **Configuration in `pyproject.toml` (PEP 518 style):** rejected.
  Pollutes Python project metadata; the tool is a CLI used against
  Android repos that are not Python projects.
- **Environment variables only:** rejected. Nested settings like
  `[risk_weights]` become unreadable as flat env vars; teams want
  to commit the config alongside the catalog.
- **JSON config:** rejected. TOML is already the format of
  `libs.versions.toml`; consistency wins.

## Cost estimate

~1 day:

- Loader, DTO, validation
- Bootstrap wiring for risk score (the only feature with config so
  far; cache TTL and output dir are mechanical follow-ups)
- Tests with valid file, missing file, malformed file, partial
  override, weights that don't sum to 100

## Success metrics

- A `gradle-deps-monitor.toml` setting `[risk_weights] cve = 40`
  produces a top-10 ranking that is visibly more CVE-driven than
  the same catalog without the file.
- Tool runs unchanged when the file is absent.
- Malformed config produces an error message that names the file
  and the offending section.
- Risk score's `RiskThresholds` and `RiskWeights` flow end-to-end
  from disk to scorer without intermediate hard-coded steps.
