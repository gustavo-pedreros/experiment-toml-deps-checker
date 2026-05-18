# RFC-0032: Atomic Report Writes

**Status:** Implemented
**Created:** 2026-05-18
**Shipped:** 2026-05-18
**Related JTBDs:** JTBD-3 (reproducible runs), JTBD-5 (operator control)
**Depends on:** ADR-0006 (clean architecture)
**Closes audit risk:** R8 (no atomic writes — crash mid-write leaves
half-rendered reports)

## Problem

Every one of the eight infrastructure writers
(`markdown_writer`, `json_writer`, `slack_writer`,
`inventory_csv_writer`, `findings_csv_writer`,
`diff_markdown_writer`, `diff_json_writer`, `diff_slack_writer`)
writes its output with bare `dest.write_text(...)` or
`dest.open("w") as fh`. If the process is killed mid-write (SIGTERM
from CI runner, OOM kill, network disk hiccup, operator Ctrl-C just
as the writer flushes) the file on disk is left in a
half-rendered state — typically truncated to whatever the OS had
flushed when the signal arrived.

Concrete consequences:

- A downstream tool that reads `freeze.json` for schema validation
  gets a `json.JSONDecodeError` on the next invocation. The
  operator sees "broken output" but the bug is the previous run, not
  the parser.
- A CI step that uses `freeze-findings.csv` as the source of a
  gate (`grep ERROR | wc -l`) returns a smaller-than-real count
  because the trailing rows never made it to disk.
- The diff workflow (`gradle-deps-monitor diff old.json new.json`)
  silently loses signal when `new.json` was truncated — the diff
  reports "no changes" because both inputs match prefix-wise up to
  the truncation point.

None of these failure modes are theoretical for a tool whose primary
consumers are CI runners and operator scripts.

## Goals

1. **Atomicity per writer.** A writer either produces the complete
   target file or leaves the previous file untouched. No third
   state.
2. **One shared helper.** All eight writers go through a single
   atomic-write primitive so the invariant is enforced at one place,
   not eight.
3. **Both write shapes covered.** The text writers
   (`write_text(...)`) and the CSV writers (`open("w") + csv.writer`)
   share the same helper without forcing CSV to build its output as
   a single string in memory.
4. **No leftover temp files** on success or on failure (including
   on `KeyboardInterrupt` / `SIGTERM`).

## Non-goals

- **Crash-safety across process boundaries.** If the OS itself
  crashes between `write()` and `replace()` the temp file may
  survive in `~/.cache/gradle-deps-monitor/` for the next operator
  to discover. Cleaning *those* requires a startup-time sweep,
  out of scope here.
- **fsync()-level durability.** `Path.replace()` is atomic on POSIX
  for same-directory paths; we don't promise post-power-loss
  durability of the new contents. Operators who need that guarantee
  run `sync` themselves.
- **Concurrent-writer coordination.** Two `gradle-deps-monitor check`
  processes targeting the same output directory at the same time
  is operator error; this RFC doesn't add a lock. The atomic
  rename means each will overwrite the other cleanly though.
- **Migrating non-writer adapters.** Diskcache, log files, etc.
  use their own write paths and aren't in scope.

## Proposed solution

### Single helper: `atomic_write` context manager

New file `src/gradle_deps_monitor/infrastructure/writers/_atomic.py`
exposing one public symbol:

```python
@contextmanager
def atomic_write(
    dest: Path,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> Iterator[TextIO]:
    """Open *dest* for atomic text-mode writing.

    Writes are buffered to a sibling temp file. On clean context
    exit the temp file is renamed to *dest* via :func:`os.replace`,
    which is atomic on POSIX for same-directory paths. On any
    exception (including ``KeyboardInterrupt`` / ``SystemExit``)
    the temp file is removed and *dest* is left untouched.

    Parent directories are created with ``mkdir(parents=True,
    exist_ok=True)`` before opening.
    """
```

Implementation outline:

```python
@contextmanager
def atomic_write(dest, *, encoding="utf-8", newline=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fh = tmp.open("w", encoding=encoding, newline=newline)
    try:
        yield fh
    except BaseException:
        fh.close()
        tmp.unlink(missing_ok=True)
        raise
    else:
        fh.close()
        os.replace(tmp, dest)
```

Why a context manager (not the `_atomic_write_text(path, content)`
function shape the plan sketched): CSV writers already iterate row
by row through `csv.writer.writerow`. Forcing them to build the
output as a single string in memory works (CSVs are tiny) but loses
the streaming idiom for no benefit. A context manager fits both call
sites with one line of change each.

Why **sibling** temp file (not `tempfile.mkdtemp()` in `/tmp`):
`os.replace` is only atomic across the same filesystem. Same-directory
guarantees that. `/tmp` is commonly a different filesystem.

Why **hidden temp prefix** (`.{name}.{pid}.{hex}.tmp`): keeps `ls`
output clean if a temp file ever survives a hard crash, and the
PID+hex suffix avoids collisions if a future concurrent invocation
ever targets the same `dest`.

### Migration: each writer becomes ~3 lines different

`markdown_writer.py` before:

```python
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(_render(report), encoding="utf-8")
```

after:

```python
with atomic_write(dest) as fh:
    fh.write(_render(report))
```

(`atomic_write` does the `mkdir` itself.)

`inventory_csv_writer.py` before:

```python
dest.parent.mkdir(parents=True, exist_ok=True)
with dest.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
    ...
```

after:

```python
with atomic_write(dest, newline="") as fh:
    writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
    ...
```

Identical behaviour to the caller; only the file-on-disk lifecycle
changes.

### Tests: `tests/infrastructure/writers/test_atomic.py`

Eight focused unit tests covering the contract:

| # | Behaviour | Test |
|---|---|---|
| 1 | Writes content correctly under happy path | `test_writes_full_content_on_clean_exit` |
| 2 | Creates parent directories | `test_creates_parent_directories` |
| 3 | No temp files left on success | `test_no_temp_file_after_clean_exit` |
| 4 | Exception → dest unchanged | `test_dest_unchanged_when_writer_raises` |
| 5 | Exception → no temp file left | `test_temp_file_removed_when_writer_raises` |
| 6 | Pre-existing dest survives a failed write | `test_existing_dest_preserved_on_failure` |
| 7 | `KeyboardInterrupt` mid-write cleans up | `test_keyboard_interrupt_cleans_temp` |
| 8 | `newline=""` passes through (CSV path) | `test_newline_passthrough_for_csv` |

The "kill pytest mid-write via SIGTERM" verification from the audit
is performed once manually after the PR opens; the unit tests cover
the API contract which is what the helper actually guarantees.

## Definition of done

- [x] `infrastructure/writers/_atomic.py` exists with `atomic_write`
  and module docstring.
- [x] All 8 writers use `atomic_write` (zero remaining
  `dest.write_text` or `dest.open("w"` calls in the writers
  package).
- [x] `tests/infrastructure/writers/test_atomic.py` contains 10
  tests (8 from the table + `test_existing_dest_replaced_on_success`
  + `test_temp_filename_pattern` for the hidden-PID-hex suffix);
  all pass.
- [x] Existing writer tests pass unchanged (no behaviour drift) —
  baseline 1169 → 1179 passed (+10 atomic tests, no regressions).
- [x] CHANGELOG `[Unreleased]` ### Changed entry naming
  atomic-write semantics.
- [x] All five quality stages pass locally on Py 3.14; CI matrix
  verifies Py 3.11 / 3.12 / 3.13 / 3.14.
- [ ] Manual SIGTERM check: kill a `gradle-deps-monitor check`
  process during write phase and confirm `freeze.md` is either
  absent or fully rendered (never truncated).
- [x] RFC marked `Status: Implemented` at merge time.

## Out of scope

- Operator-facing `--no-atomic` flag — the helper is universally
  desirable and `os.replace` is fast enough that opt-out is
  pointless.
- Lock-file coordination across concurrent invocations.
- Atomic delete (e.g. for `--clear-cache`) — that path uses
  `shutil.rmtree` and is non-atomic by design.
