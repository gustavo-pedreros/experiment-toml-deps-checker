# RFC-0034: Slack output becomes opt-in

**Status:** Implemented
**Created:** 2026-05-19
**Shipped:** 2026-05-19
**Related JTBDs:** JTBD-5 (operator control), cross-cuts JTBD-3 (reproducible runs)
**Depends on:** RFC-0012 (layered config — uses the reserved `[output]` section)

## Problem

`gradle-deps-monitor check` currently produces five output files
unconditionally — `freeze.md`, `freeze.json`, `freeze-slack.json`,
`freeze-inventory.csv`, `freeze-findings.csv` — and `diff` produces
three. The Slack writer emits a Slack Block Kit JSON document that
exists for teams who POST it to an Incoming Webhook. In practice
most users never wire that webhook; the file lives next to
`freeze.md` and gets committed (or `.gitignore`-d) without being
read.

Of the five outputs, Slack is the only one **without an internal
consumer**:

| Output | Consumer |
|---|---|
| `freeze.md` | Humans (canonical per ADR-0002), git diff in PRs |
| `freeze.json` | `gradle-deps-monitor diff` (load-bearing) |
| `freeze-slack.json` | None internally — only Slack webhook posters |
| `freeze-inventory.csv` | `/analyze-freeze` skill (RFC-0033) |
| `freeze-findings.csv` | `/analyze-freeze` skill (RFC-0033) |

The user audited the CLI surface area after Phase 8 v1 closed and
asked for a minimum viable core. After considering wider options
(per-check toggles, `--quick` / `--full` profiles, a setup skill,
HTML migration) all other items were parked. This RFC ships the
surgical change: Slack output becomes opt-in.

## Non-goals

- **Per-check toggles** (the "I/O sin pedir" lever). Real value but
  bigger scope; parked.
- **`--quick` / `--full` / `--profile` modes.** Same reason.
- **Per-writer kill switches for the load-bearing outputs** (md,
  json, CSVs). Would let users break diff or `/analyze-freeze`. Not
  exposed.
- **Setup skill / sub-agent.** Parked.
- **HTML migration of `freeze.md`.** Out of scope; the user wants
  to separately re-evaluate the documentation framework (ADRs,
  RFCs, roadmap) with an HTML lens — a distinct future initiative
  about doc publishing, not the freeze output.

## Proposed solution

Two surfaces, one boolean knob.

### CLI flag

```bash
# Default (no Slack output):
gradle-deps-monitor check /path/to/gradle --out reports/2026-05-19/

# Restore previous behaviour:
gradle-deps-monitor check /path/to/gradle --out reports/2026-05-19/ --slack
```

The flag is a tri-state `--slack/--no-slack`. When unset, the
loader-resolved value from the TOML config applies (which defaults
to `false`). When set, the flag wins over the config — same
precedence as every other RFC-0012 knob.

The diff command mirrors the same flag:

```bash
gradle-deps-monitor diff old.json new.json --slack
```

### Config knob

```toml
# gradle-deps-monitor.toml — next to the gradle dir for check;
# read from cwd for diff.
[output]
slack = true
```

The `[output]` section was already reserved in
`infrastructure/config/loader.py` (`_KNOWN_SECTIONS`) for exactly
this kind of future opt-in; RFC-0034 turns it from "reserved" to
"consumed".

### Default outputs after this RFC

| Command | Default writers (count) | With `--slack` |
|---|---|---|
| `check` | md + json + 2 CSVs (4) | + slack (5) |
| `diff` | md + json (2) | + slack (3) |

## Alternatives considered

1. **`--no-slack` opt-out** instead of opt-in. Rejected: positive
   form matches the new default; the negative would imply slack is
   still on by default.
2. **Per-format flag `--format md,json,csv`.** Rejected:
   over-engineered for one toggle. Opens "which writers can I
   disable?" can of worms (the load-bearing writers can't be
   disabled without breaking diff or analytics).
3. **`[output] writers = [...]` list form.** Rejected: forces
   ordering decisions, opens the same "can I disable md?" question.
   Boolean-per-writer is forward-compatible — if more writers
   become opt-in (notably the planned HTML export from RFC-0010),
   they each get their own `[output] html = true` knob.
4. **Print a deprecation warning** during a grace release. Rejected:
   no projected affected users (the project has no production
   consumers per the project memory; CI pipelines using the Slack
   file are presumed zero). The CHANGELOG `### Changed` entry plus
   a README note is the migration path. If a real user surfaces
   post-merge, add the warning in a follow-up.
5. **Wider scope** (check-level reduction, profile modes, setup
   skill, HTML migration). Explicitly parked per user direction in
   the planning conversation.

## Cost estimate

Trivial. ~30 LoC across `cli.py` + `bootstrap.py` + `config.py` +
`loader.py`; ~50 LoC of test updates and new tests; docs.

## Schema impact

None. `freeze-slack.json` is unaffected when emitted; it is simply
not emitted by default. Existing files on disk are untouched (the
writers don't delete prior runs). The `freeze.json` schema version
stays at `1.7.0`.

## Rollback strategy

Single revert restores the previous always-emit default. No
downstream consumers within the project rely on the opt-in shape.
External CI pipelines that POSTed the Slack file would already be
using the explicit flag after this RFC, so a revert is a silent
no-op for them.

## PR budget

1.

## Migration

For users who relied on the previous default (Slack file emitted
unconditionally), one of these changes restores it:

```bash
# In a CI step:
gradle-deps-monitor check ./gradle --out reports/ --slack
```

```toml
# In gradle-deps-monitor.toml at the project root:
[output]
slack = true
```

## Definition of Done

- [x] `gradle-deps-monitor check <dir>` default run produces md +
  json + 2 CSVs, no slack file.
- [x] `--slack` flag (and `[output] slack = true` config) each
  independently re-enable the slack writer.
- [x] `--no-slack` flag explicitly disables even when config is
  `true` (CLI wins per RFC-0012 precedence).
- [x] Diff command behaves symmetrically.
- [x] Existing test suite green after updates; new tests cover
  both flag and config paths plus the precedence override.
- [x] CHANGELOG `[Unreleased] / Changed` entry with the migration
  line.
- [x] README and User Guide reflect the new default.
- [x] RFC-0034 status: Implemented in the merging PR.
