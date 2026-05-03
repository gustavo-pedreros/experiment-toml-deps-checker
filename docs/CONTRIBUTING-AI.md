# AI Context

This file orients AI assistants and human contributors who pick up
work on this project mid-stream. Reading these files in order will
reconstruct the design context faster than re-reading every commit.

## Reading order

1. `README.md` — what the tool does today
2. `docs/roadmap.md` — current phase, status of each item
3. `docs/jtbd.md` — the user jobs the tool serves
4. `docs/adr/` — accepted architectural decisions; do not relitigate
   without a strong reason
5. `docs/proposals/` — open proposals that are not yet decided

## Project conventions

- **Repo language**: all code, comments, file names, README, output
  text, configuration keys, log messages, and proposal documents are
  in English. Maintainers may chat in any language; the artifact is
  always English. See [ADR-0005](adr/0005-language-convention-english-in-repo.md).
- **Output is for humans first**: the canonical report format is
  Markdown, written to be readable in a GitHub diff view. JSON is the
  machine-readable companion. See [ADR-0002](adr/0002-markdown-as-canonical-output-format.md).
- **Freeze report as artifact**: the tool is most often invoked at
  freeze time. Reports are committed to `freeze-reports/` and may be
  attached to release tags.
- **Configuration is layered**: defaults → user config → project
  overrides. Defaults must be sensible for general-purpose Android
  projects, not specific to any one team.

## Project context (current)

- The original tool was a Bash script wrapping a Python script.
  Phase 1 replaces this with a single Python CLI (see [ADR-0001](adr/0001-python-over-bash.md)).
- The tool is open source. It is also actively used in a fintech
  context where security and compliance features are
  non-negotiable. The design must serve both audiences.
- The project that uses it most actively has roughly 200 modules
  sharing a single `libs.versions.toml`. The tool must scale to that
  size without becoming painfully slow.

## How to propose a change

- New features start as a file in `docs/proposals/` (see the
  [proposal template](proposals/README.md))
- Architectural decisions that constrain the implementation go in
  `docs/adr/` (see the [ADR template](adr/README.md))
- The roadmap is updated when a proposal is accepted

## Anti-patterns to avoid

- Reintroducing Bash as glue between Python scripts
- Hardcoding values that vary by team (risk weights, severity
  thresholds, CVE policy) into the core; surface them as config
- Adding output formats before the existing ones are stable and
  schema-versioned
- Rejecting proposals silently. Rejected proposals stay in the repo
  with a documented rationale.
