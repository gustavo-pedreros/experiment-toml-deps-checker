# gradle-deps-monitor — User Guide

`gradle-deps-monitor` is a freeze-time, due-diligence CLI for Android
projects that use Gradle's `libs.versions.toml`. It reads the version
catalog, talks to Maven / GHSA / OSS Index, and writes five output
files plus a Rich console summary in around 5–10 seconds for a
typical 200-library catalog.

This guide is the **operator manual**: how to install, configure, run,
read the output, and wire the tool into CI. It complements the
[README](../../README.md) (one-screen overview) and the
[RFCs](../proposals/) (per-feature design rationale).

## Table of contents

1. **[Getting started](getting-started.md)** — install, run, read
   the first report.
2. *Configuration* — `gradle-deps-monitor.toml`, environment
   variables, cache controls. *(Coming next — RFC-0021 Phase 2.)*
3. *Feature deep-dives* — Risk Score, Module Usage, BoM resolution,
   License audit, CVE scanning. *(Coming next.)*
4. *CI integration* — GitHub Actions and Bitrise recipes, plus the
   exit-code contract from RFC-0018. *(Coming next.)*
5. *Troubleshooting* — what each warning means and what to do about
   it. *(Coming next.)*

## Quick links

- **Install:** `pip install gradle-deps-monitor`
- **First run:** `gradle-deps-monitor check /path/to/gradle`
- **All flags:** `gradle-deps-monitor check --help`
- **Architecture:** [`docs/diagrams/`](../diagrams/)
- **Roadmap:** [`docs/roadmap.md`](../roadmap.md)
