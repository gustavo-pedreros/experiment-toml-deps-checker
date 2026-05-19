# Contributing

This file orients new contributors who pick up work on `gradle-deps-monitor`
mid-stream. Reading the documents in order below reconstructs the design
context faster than re-reading every commit.

## Reading order

1. `README.md` — what the tool does today, install + first run, the
   five outputs.
2. `docs/user-guide/` — operator manual: getting started, configuration,
   each feature explained, CI integration recipes, troubleshooting.
3. `docs/roadmap.md` — phases shipped, current focus, backlog.
4. `docs/jtbd.md` — the user jobs the tool serves.
5. `docs/adr/` — accepted architectural decisions; do not relitigate
   without a strong reason.
6. `docs/proposals/` — RFCs (open and shipped) per feature.
7. `docs/diagrams/` — four hand-drawn architecture diagrams from
   system-context down to port↔adapter map.

## Dev setup

```bash
git clone https://github.com/gustavo-pedreros/experiment-toml-deps-checker.git
cd experiment-toml-deps-checker
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+. CI runs the matrix on 3.11 / 3.12 / 3.13 / 3.14.

Before committing or opening a PR, run the full five-stage local suite —
the same one CI runs:

```bash
ruff check . && ruff format --check . && mypy src && lint-imports && pytest
```

All five stages must pass. The repo has 1 200+ tests across the six
architectural layers plus 5 `import-linter` contracts enforcing layer
boundaries; any one failure blocks the merge.

## Project conventions

- **Repo language**: all code, comments, file names, README, output
  text, configuration keys, log messages, and proposal documents are
  in English. Maintainers may chat in any language; the artifact is
  always English. See [ADR-0005](docs/adr/0005-language-convention-english-in-repo.md).
- **Output is for humans first**: the canonical report format is
  Markdown, written to be readable in a GitHub diff view. JSON is the
  machine-readable companion. See [ADR-0002](docs/adr/0002-markdown-as-canonical-output-format.md).
- **Freeze report as artifact**: the tool is most often invoked at
  freeze time. Reports are committed to `freeze-reports/` and may be
  attached to release tags.
- **Configuration is layered**: defaults → user config → project
  overrides. Defaults must be sensible for general-purpose Android
  projects, not specific to any one team.
- **Schema-versioned JSON**: `freeze.json` follows SemVer per
  [ADR-0008](docs/adr/0008-json-schema-semver.md) — additive MINOR for new
  fields, wire-format-equivalent PATCH otherwise. Breaking changes
  bump MAJOR and require a migration plan.

## Project context

- The project is open source and released as `v0.1.0` (first public
  tag — see [CHANGELOG](CHANGELOG.md)). Before that point, work
  happened across seven internal phases captured in
  [`docs/roadmap.md`](docs/roadmap.md).
- The tool is also actively used in a fintech context where security
  and compliance features are non-negotiable. The design serves both
  audiences: open-source readability and freeze-time enterprise
  due-diligence.
- The most active deployment scans roughly 200 modules sharing a
  single `libs.versions.toml`. Performance benchmarks (cold ~6 s,
  warm ~4 s on a 200-library catalog) are the operational baseline;
  regressions there are noticed.

## How to propose a change

- **New features** start as a file in
  [`docs/proposals/`](docs/proposals/) (see the
  [proposal template](docs/proposals/README.md)).
- **Architectural decisions** that constrain the implementation go
  in [`docs/adr/`](docs/adr/) (see the
  [ADR template](docs/adr/README.md)).
- **The roadmap** is updated when a proposal is accepted into a
  phase.
- **Implementation** follows [ADR-0009](docs/adr/0009-tracer-bullets-for-rfc-implementation.md)
  (Tracer Bullets): ship a thin end-to-end slice first, then enrich.
  Each tracer typically lands as 1–3 small PRs.

## Anti-patterns to avoid

- Reintroducing Bash as glue between Python scripts.
- Hardcoding values that vary by team (risk weights, severity
  thresholds, CVE policy) into the core; surface them as config.
- Adding output formats before the existing ones are stable and
  schema-versioned.
- Bypassing the architectural layer contracts (`import-linter` will
  catch this, but the cleaner move is to design within the layer
  rules from the start).
- Rejecting proposals silently — rejected proposals stay in the repo
  with a documented rationale.
