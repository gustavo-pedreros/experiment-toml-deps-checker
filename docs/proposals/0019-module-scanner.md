# RFC-0019: High-Performance & Accurate Module Scanner

**Status:** Draft
**Created:** 2026-05-07
**Related JTBDs:** JTBD-3 (blast radius), JTBD-5 (report accuracy)
**Depends on:** none

## Problem

The current `GradleModuleScanner` is a synchronous, regex-based tool that has several limitations discovered in large projects (>100 modules):
1.  **Performance:** Reading hundreds of `build.gradle` files sequentially is a bottleneck.
2.  **Inaccuracy (camelCase):** It only detects `libs.foo.bar` (dotted) and misses `libs.fooBar` (camelCase), which is standard in Kotlin DSL (`.kts`).
3.  **Inaccuracy (Bundles):** Usage of `libs.bundles.myBundle` is not attributed back to the individual libraries that compose the bundle.

## Proposed solution

Overhaul the `GradleModuleScanner` to improve speed and accuracy.

### 1. Parallel I/O
Utilize `asyncio` or a thread pool to read and parse build files concurrently. For a project with 200 modules, this should significantly reduce the scanning overhead.

### 2. Dual-Accessor Mapping
The internal reverse lookup map will store both the dotted and camelCase forms of every library alias.
- `androidx-core-ktx` → `libs.androidx.core.ktx` AND `libs.androidxCoreKtx`.

### 3. Bundle Awareness
When the scanner encounters `libs.bundles.<name>`, it will look up the members of the bundle in the `Catalog` and increment the usage count for *all* member libraries.

## Implementation Plan

### Phase 1: Accessor Logic
- Update `_build_accessor_map` in `infrastructure/scanners/gradle_module_scanner.py` to include camelCase variants.

### Phase 2: Bundle Resolution
- Update the scanning loop to resolve bundle members when a bundle accessor is detected.

### Phase 3: Concurrency
- Refactor the `scan()` method to use `asyncio.gather` for file reading and regex matching.

## Alternatives considered

- **Full AST Parsing:** Rejected. Using a proper Gradle/Kotlin parser is too heavy and would introduce non-Python dependencies. Regex remains "good enough" if the mapping logic is improved.
