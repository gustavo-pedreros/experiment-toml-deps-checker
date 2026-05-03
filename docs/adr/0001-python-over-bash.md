# ADR-0001: Python as the single language

## Status

Accepted — 2026-05-03

## Context

The original tool was structured as a Bash script (`check-dependencies.sh`)
that wrapped a Python script (`version-stats.py`). The Bash layer
managed virtual environment creation, dependency installation, and
invocation of the Python script.

This split introduced several costs without delivering value:

- Two error-handling models. Bash uses exit codes and `$?`; Python
  uses exceptions. Both layers had to be defensive, and failures in
  one were not always surfaced cleanly to the other.
- No portability to Windows. Contributors and CI agents on Windows
  could not run the tool without WSL.
- Setup was reinvented on every run. The script ran `pip install
  requests` every invocation, even when the package was already
  installed.
- Testing the orchestration logic required spinning up real shells.

Other languages were considered:

- **Kotlin / Gradle plugin**: a strong fit for a Gradle-native
  experience, but with significant build and distribution overhead
  for an early-stage open-source tool.
- **Go**: produces a single static binary with no runtime
  requirement, ideal for distribution. Rejected because Go is not
  familiar in the typical Android team and would slow community
  contribution.
- **Pure Python**: keeps the language familiar to the original
  author, has excellent libraries for the use case (`tomllib`,
  `httpx`, async I/O), and modern packaging tools (`uv`, `pipx`)
  remove the historical setup pain.

## Decision

The tool is implemented as a pure Python application with a single
entry point. The Bash wrapper is removed.

Setup and dependency management are handled inside Python, using one
of:

- A `pyproject.toml` consumable by `pipx` or `uv tool install`
- An optional auto-bootstrap path for users without `pipx` / `uv`
  installed

Python 3.11 or newer is required, so that `tomllib` is available in
the standard library and modern async features are usable.

## Consequences

**Positive**

- A single language and a single error-handling model
- Native cross-platform support (macOS, Linux, Windows)
- Faster startup: no shell process, no `pip install` on every run
- Easier testing: the entry point is callable from a test harness
- Smaller surface area for future contributors

**Negative**

- Existing users invoking the tool via `./check-dependencies.sh`
  must update their invocation. A migration note will live in the
  README and changelog.
- Python 3.11 is a hard floor; users on older Pythons need to
  upgrade or use `pipx`/`uv` which manage their own interpreter.
