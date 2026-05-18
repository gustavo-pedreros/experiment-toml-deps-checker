# CI integration

`gradle-deps-monitor` is designed to be a single CLI invocation
inside a CI pipeline. Two integration shapes cover almost every
team:

1. **Informational** — run on every PR, upload the reports as
   artifacts, never break the build. Best for teams introducing the
   tool gradually.
2. **Gatekeeper** — same as above plus `--fail-on-errors` so the PR
   check goes red on critical findings. Best for teams that already
   have an established freeze cadence and want hard enforcement.

## Exit-code contract (RFC-0018 v1)

The CLI follows `sysexits.h`-style codes:

| Code | Meaning | When to surface as a failed CI check |
|---|---|---|
| `0` | Success — no policy violations | Never. |
| `1` | Policy violation (`--fail-on-errors` triggered) | Always, when you want gating. |
| `2` | Usage error — bad flag value, e.g. `--warn-on bogus-category` | Always — fix the workflow. |
| `3` | Config / parse error — `libs.versions.toml` missing, unreadable, or malformed | Always — fix the catalog. |

Most CI systems treat any non-zero exit as a failed step. The
distinction between `1`, `2`, and `3` matters only for downstream
scripts that branch on it.

## GitHub Actions

A minimal workflow that runs on every PR and uploads the five
output files as artifacts. The `GITHUB_TOKEN` env var unlocks the
CVE scanner and lifts the changelog-scraper rate limit to
5 000 req/h.

```yaml
name: Dependency freeze
on:
  pull_request:
    paths:
      - 'gradle/libs.versions.toml'
      - 'gradle-deps-monitor.toml'
  workflow_dispatch:

jobs:
  freeze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install gradle-deps-monitor
        run: pip install gradle-deps-monitor

      - name: Run freeze check (gatekeeper mode)
        env:
          # Zero scopes required. ${{ secrets.GITHUB_TOKEN }} works too.
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gradle-deps-monitor check ./gradle \
            --out reports/ \
            --module-usage \
            --risk-score \
            --fail-on-errors \
            --warn-on high-vulnerability,deprecated,breaking

      - name: Upload freeze reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: freeze-reports
          path: reports/
```

### Workflow annotations

The CLI auto-detects `GITHUB_ACTIONS=true` (which the runner sets
for you) and emits one `::error file=…::…` or `::warning file=…::…`
line per finding. GitHub renders those inline in the PR file diff
next to `gradle/libs.versions.toml`, so reviewers see violations
without opening the artifact.

Example output the workflow surfaces:

```
::error file=gradle/libs.versions.toml::[security] retrofit2 — Critical CVE GHSA-aaaa-bbbb-cccc: …
::warning file=gradle/libs.versions.toml::[breaking] kotlin-stdlib — Likely-breaking upgrade 1.9.0 → 2.0.0
```

Special characters (`%`, CR, LF, `:`) are escaped per the
workflow-commands spec, so multi-line CVE summaries don't break the
parser.

### PR comment with the diff

If you produce one freeze per `main` push and one per PR, you can
post a Markdown diff as a PR comment:

```yaml
      - name: Download base freeze
        uses: dawidd6/action-download-artifact@v6
        with:
          workflow: dependency-freeze.yml
          branch: main
          name: freeze-reports
          path: base-reports/

      - name: Diff against base
        run: |
          gradle-deps-monitor diff \
            reports/freeze.json \
            --prev base-reports/freeze.json \
            --out diff-reports/

      - name: Comment PR with diff
        uses: peter-evans/create-or-update-comment@v4
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body-path: diff-reports/freeze-diff.md
          edit-mode: replace
```

## Bitrise

Bitrise doesn't have native workflow annotations, but the exit-code
contract and the Slack output cover the same use cases.

```yaml
- script@1:
    inputs:
    - content: |
        #!/usr/bin/env bash
        set -e
        pip install gradle-deps-monitor
        gradle-deps-monitor check ./gradle \
          --out $BITRISE_DEPLOY_DIR/freeze-reports \
          --module-usage \
          --fail-on-errors

- slack@4:
    is_always_run: true
    inputs:
    - webhook_url: $SLACK_WEBHOOK
    - text_on_error: "Freeze gate failed. See $BITRISE_BUILD_URL"
    - text: "Freeze report ready."
    # Or use the Block Kit file directly:
    - blocks: $BITRISE_DEPLOY_DIR/freeze-reports/freeze-slack.json
```

The `is_always_run: true` flag posts the Slack message even when
the `script` step failed with exit code `1` — the build still shows
red in Bitrise, the message gets to your team's channel.

## Other CI providers

The pattern is identical everywhere: install, set
`GITHUB_TOKEN`, run `gradle-deps-monitor check`, upload `reports/`
as artifacts, optionally consume the Slack JSON. The
`GITHUB_ACTIONS=true` annotations are GitHub-only; other providers
read the standard exit code and the per-file output.

## Performance tips for CI

- **Restore the cache between runs.** The `~/.cache/gradle-deps-monitor`
  directory makes warm runs roughly 2–3× faster than cold ones.
  GitHub Actions example:
  ```yaml
  - uses: actions/cache@v4
    with:
      path: ~/.cache/gradle-deps-monitor
      key: gradle-deps-monitor-${{ runner.os }}-${{ hashFiles('gradle/libs.versions.toml') }}
      restore-keys: |
        gradle-deps-monitor-${{ runner.os }}-
  ```
- **Use a separate cache key per branch** if your team has many
  long-lived branches; otherwise the catalog hash already partitions
  cleanly.
- **`--no-cache` once a day** in a scheduled workflow gives you a
  daily fresh-CVE baseline without slowing every PR run.
