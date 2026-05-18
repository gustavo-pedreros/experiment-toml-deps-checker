# RFC-0027: Stability-Gated `<release>` Fallback in Version Registries

**Status:** Implemented
**Created:** 2026-05-17
**Shipped:** 2026-05-17 (PR #57)
**Related JTBDs:** JTBD-1 (informed upgrade decisions), JTBD-5 (report accuracy)
**Depends on:** RFC-0026 (PRE_1_0 stability tier — uses `MavenVersion.is_stable` as the gate)

## Problem

`MavenMetadataRegistry._parse_release` (`infrastructure/registries/_base.py:78-84`)
trusts the publisher's `<versioning><release>` tag verbatim:

```python
def _parse_release(xml_text: str, group: str, artifact: str) -> str | None:
    try:
        root = ET.fromstring(xml_text)
        return root.findtext("versioning/release") or None
    except ET.ParseError as exc:
        raise VersionRegistryError(...)
```

This is fine when the publisher's release-management practice is sane.
It produces actively wrong reports when the publisher tags a
pre-release as `<release>`. Live evidence from
`com.google.protobuf:protoc` (validated 2026-05-17 against the live
Maven Central metadata):

```xml
<latest>21.0-rc-1</latest>          <!-- pre-release, Mar 2022 -->
<release>21.0-rc-1</release>        <!-- pre-release, Mar 2022 -->
<versions>
  …4.x.y line, ending with 4.34.1 stable + 4.35.0-RC2…
  <version>21.0-rc-1</version>      <!-- last in the list -->
</versions>
```

The protobuf publishing pipeline pushed `21.0-rc-1` more recently
than the 4.x stable line, which caused both `<latest>` and `<release>`
to point at it. The user pinned `4.29.2` (Dec 2024 stable, current
4.x line); the tool reported "17 majors behind" pointing at a release
that is **2.5 years older** than what they have pinned, **and is an
RC**.

The original stress-test memo (`#14` in
`stress_test_findings_2026_05.md`) misdiagnosed the mechanism as
lexicographic sorting. A spike on 2026-05-17 verified the actual
shape: the resolver does no sorting at all — it just trusts what the
publisher wrote.

This bug actively misleads readers about a correctness-sensitive
piece of data (the "latest version"). For a tool whose purpose is
freeze-time due diligence, that's a trust-eroding failure.

### Scope of the affected class

Spike survey of the two available validation corpora plus targeted
inspection of suspect coordinate families:

- **`com.google.protobuf:protoc`** (in `nowinandroid`) — confirmed
- **`com.google.protobuf:protobuf-kotlin-lite`** (same family) —
  highly likely (same publishing pipeline, same metadata namespace)
- No other coordinates with this shape were found in
  `mach-android` or `nowinandroid`

The class is real but small in the corpora seen. Path A (per-coordinate
allowlist) was considered and rejected — it rots, doesn't generalise,
and treats the symptom rather than the underlying trust pattern.

## Proposed solution

Add a stability gate to `_parse_release`: if the publisher's
`<release>` tag does **not** classify as `Stability.STABLE`, fall
back to scanning `<versioning><versions><version>` in reverse
document order for the most recent stable entry.

```python
def _parse_release(xml_text: str, group: str, artifact: str) -> str | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise VersionRegistryError(...)

    release = root.findtext("versioning/release") or None
    if release and MavenVersion(release).is_stable:
        return release

    # Publisher tag missing or pre-release. Scan <versions> in
    # reverse document order for the latest stable entry. Maven
    # Central writes versions in publishing order, so the last
    # stable entry is the most recently released stable artifact
    # across all release lines maintained at this coordinate.
    for v in reversed(root.findall("versioning/versions/version")):
        text = v.text
        if text and MavenVersion(text).is_stable:
            return text

    # No stable in the versions list either — preserve current
    # behaviour and return the original <release> tag (or None).
    return release
```

### Behaviour matrix

| Catalog state | Today | After RFC-0027 |
|---|---|---|
| `<release>` is stable (e.g. `4.12.0`) | returns `4.12.0` | returns `4.12.0` (unchanged) |
| `<release>` is RC and `<versions>` has stables (protoc case) | returns RC | **returns latest stable from versions** |
| `<release>` is RC and `<versions>` has no stables | returns RC | returns RC (fallback preserves today) |
| `<release>` is missing (rare) | returns None | scans versions; None if also empty |
| `<release>` is `0.x.y` ([[pre-1-0-stability-tier]]) | returns `0.x.y` | scans for ≥1.0 stable; falls back to `0.x.y` if none |

The `0.x.y` row is the only intentional behaviour shift outside the
target bug. Pre-RFC-0026 `0.x.y` classified as STABLE so we
returned it. Post-RFC-0026 it classifies as PRE_1_0. After this RFC,
a library at `<release>0.5.0</release>` with no stable in `<versions>`
still resolves to `0.5.0` via the fallback — same final result, just
via a longer path. A library that genuinely has both `0.x.y` and
`1.0.0` entries (rare; usually publishers stop publishing 0.x once
1.0 ships) would route to `1.0.0` — which is the correct answer per
SemVer.

### Why document order is the right scan strategy

Maven Central writes `<version>` entries in publishing order
(chronological by upload time). Reverse-iterating means "most
recently published stable artifact wins". This is exactly the
semantic users expect from "latest": the freshest stable release.

For protoc specifically, reverse scan from the end:
1. `21.0-rc-1` — RC, skip
2. `4.35.0-RC2` — RC, skip
3. `4.34.1` — stable, **return**

User's `4.29.2` → tool now reports "latest stable: 4.34.1" (5 patch
versions newer, same major line). Accurate, actionable.

### Why not sort by parsed SemVer

Considered. Rejected because:

1. **No comparator exists in the codebase today.** Adding one is a
   significant surface; the project explicitly avoided it (see
   `domain/version.py`: "Parsing stays intentionally simple: no
   full Maven version-ordering semantics").
2. **Document order is empirically correct for Maven Central.** The
   chronological-write guarantee is documented in the Maven repository
   metadata spec and is what publishers actually do.
3. **A SemVer sort would not have caught the protoc bug differently** —
   it'd pick `4.34.1` too, same result. The marginal robustness gain
   doesn't justify the comparator surface area.
4. **If/when** a comparator becomes necessary for other reasons
   (cross-line `latest` semantics, version ordering in diff output),
   it can be introduced as a separate domain concern and this
   adapter can switch to it transparently.

## Tracer Bullet Path (ADR-0009)

Whole change is the tracer: single file change in
`_base.py:_parse_release` plus parametrised test additions. No new
files, no port signature changes, no schema impact.

1. **Infrastructure**: rewrite `_parse_release` with the
   stability-gated fallback. Imports `MavenVersion` from the domain
   layer (already in scope at module top).
2. **Composition Root**: no wiring change. Both `MavenCentralRegistry`
   and `GoogleMavenRegistry` inherit from `MavenMetadataRegistry`
   and pick up the fix automatically.
3. **Minimal Output**: existing 9 parametrised registry tests
   continue to pass without modification. Add new tests covering
   the four new behaviour rows from the table above.

## Implementation Plan

### PR #1 — Single PR: stability-gated `<release>` fallback

- Rewrite `_parse_release` in `infrastructure/registries/_base.py`
  with the four-step stability gate.
- Extend `tests/infrastructure/registries/test_registries.py` with:
  - `_METADATA_PROTOC_SHAPE` fixture: `<release>` = RC, `<versions>`
    has stable + RC interleaved, last entry is RC
  - `_METADATA_NO_STABLE` fixture: every version is alpha/beta/RC
  - `_METADATA_PRE_1_0_ONLY` fixture: every version is `0.x.y`
  - Parametrized test cases for each of the four new rows in the
    behaviour matrix
- CHANGELOG entry under `[Unreleased] / Fixed` documenting the bug,
  the validated impact on `protoc`, and the explicit fallback to
  `<release>` when no stable exists in `<versions>`.

## Validation Strategy

Post-merge, re-run against `nowinandroid` (which has the affected
`protoc` pin). Confirm:

- `protoc` row in the Markdown libraries table now shows latest
  somewhere in the 4.x line (current latest stable is `4.34.1` at
  time of writing)
- JSON `version_status.latest` for protoc matches
- Risk score and drift category re-derive correctly from the new
  latest

## Schema impact

`none`. Pure adapter-internal change; the registry's public
contract (`get_latest() -> MavenVersion | None`) is unchanged.
`freeze.json` content for affected libraries changes (the `latest`
field now points at a different version), but the schema shape and
all field names/types are identical.

## Alternatives considered

- **Path A — per-coordinate allowlist.** Hardcode
  `{"com.google.protobuf:protoc", ...}` as "ignore `<release>`, scan
  versions". Rejected — rots, doesn't generalise, and treats the
  symptom rather than the underlying trust pattern. Any new protoc-
  shaped coordinate (e.g. `protobuf-kotlin-lite` post-publishing-
  reshuffle) would silently re-introduce the bug until someone
  notices and updates the list.
- **Path B — proper SemVer comparator + release-line clustering.**
  Detect multiple parallel release lines (major-version clusters
  with non-overlapping date ranges) and route per-line. Rejected —
  over-engineered for what is a 1-2 library problem in the corpora
  seen; introduces significant new domain surface; high regression
  risk. Reserve for if/when the affected class grows.
- **Path C — prefer `<latest>` over `<release>`.** The spike's
  initial recommendation. Rejected after live verification: for
  `com.google.protobuf:protoc` both tags are set to the same broken
  value (`21.0-rc-1`). Prefer-`<latest>` would not have fixed the
  validated case.
- **Pin to library-specific knowledge in the curated KB.** Same
  rot problem as Path A; KB is for *deprecation* signal, not for
  patching upstream publisher bugs.
- **Return `None` instead of falling back to `<release>` when no
  stable found.** Rejected — current behaviour for alpha-only
  libraries is to surface the alpha; downgrading to `None` would
  show "drift: UNKNOWN" for libraries where today we show
  "drift: behind/current" (correctly relative to the alpha). The
  fallback preserves current behaviour for the edge case.

## Cost estimate

Tiny. ~15 LoC of resolver change in
`infrastructure/registries/_base.py`. ~30 LoC of parametrised test
extensions in `tests/infrastructure/registries/test_registries.py`.
One CHANGELOG entry. No new dependencies, no port changes, no
domain changes, no schema bump.

## Success metrics

- **Correctness on protoc**: `nowinandroid` re-run reports a 4.x.y
  stable as "latest" for `com.google.protobuf:protoc` rather than
  `21.0-rc-1`.
- **No regression on sane publishers**: existing 9 parametrised
  registry tests continue to pass without modification.
- **Stability gate honoured**: a pre-release tag in `<release>`
  triggers the fallback; a stable tag doesn't.
- **Empty-stable fallback honoured**: a versions list with no
  stable entries still returns the `<release>` tag rather than
  `None`.

## Rollback strategy

Revert the single PR → resolver returns to verbatim `<release>`
trust. `protoc` reverts to reporting `21.0-rc-1` as latest. Other
libraries unaffected.

## PR budget

Estimated **1 PR** from tracer to DoD.

## Definition of Done (DoD)

- [ ] **Integration**: Reachable via both `MavenCentralRegistry`
  and `GoogleMavenRegistry` (inheritance from `MavenMetadataRegistry`).
- [ ] **Architecture**: Follows ADR-0006 (Clean Architecture) — the
  change is contained to the infrastructure adapter; the domain's
  `MavenVersion.is_stable` is the only crossing.
- [ ] **Testing**: Existing 9 registry tests pass unmodified; four
  new parametrised cases cover the new rows of the behaviour
  matrix.
- [ ] **Documentation**: CHANGELOG entry under `[Unreleased] /
  Fixed` documents the bug shape (publisher tag trusted blindly),
  the validation against the live protoc metadata, and the explicit
  fallback semantics.
