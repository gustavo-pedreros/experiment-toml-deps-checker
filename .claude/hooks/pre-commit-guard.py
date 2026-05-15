#!/usr/bin/env python3
"""PreToolUse hook for the Bash tool.

Intercepts `git commit ...` calls Claude Code is about to run and blocks
them unless the test-runner subagent has just been dispatched (signalled
by `SKIP_TEST_RUNNER=1` in the environment).

Reads the Claude Code hook payload from stdin (JSON), inspects
`tool_input.command`, and emits a guidance message on stderr + exit code
2 (block) when the command is a commit without the escape valve set.
"""

from __future__ import annotations

import json
import os
import re
import sys

_GUIDANCE = """\
[pre-commit-guard] Blocking `git commit`.

Before committing, dispatch the `test-runner` subagent to run the
full CI suite (ruff, mypy, lint-imports, pytest):

    Agent(
        subagent_type="test-runner",
        description="Pre-commit CI suite",
        prompt="Run the full CI suite on the current working tree and "
               "report each stage's pass/fail.",
    )

Then, depending on the report:

  * All 5 stages passed -> retry the commit with the escape valve:

        SKIP_TEST_RUNNER=1 git commit ...

  * Any stage failed -> surface the failures to the user. Do NOT
    auto-fix unless explicitly asked, and do NOT retry the commit
    until the user has decided how to proceed.

Bypass the guard manually (use sparingly, e.g. docs-only commits):

    SKIP_TEST_RUNNER=1 git commit -m "docs: ..."
"""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        # If we cannot understand the hook payload, fail open so we never
        # block legitimate work because of a hook bug. The harness logs
        # stderr; that's enough for debugging.
        print("[pre-commit-guard] could not parse hook payload", file=sys.stderr)
        return 0

    command = payload.get("tool_input", {}).get("command", "")

    # Match `git commit` as a whole word. This catches `git commit -m`,
    # `git commit --amend`, etc., and explicitly excludes plumbing
    # subcommands like `git commit-tree`.
    if not re.search(r"(^|[^A-Za-z0-9_-])git\s+commit(\s|$)", command):
        return 0

    # Manual escape valve. Detected two ways:
    #   1. As an inline prefix in the command string (the documented
    #      usage: `SKIP_TEST_RUNNER=1 git commit ...`). This is what
    #      Claude / a human actually types. The hook runs as a separate
    #      process and does NOT inherit the inline env-var binding, so
    #      we have to look for the literal prefix in the command itself.
    #   2. As an env var on the hook process. Only fires if the
    #      variable is exported in the harness's own environment, which
    #      is rare but supported for completeness.
    if re.search(r"\bSKIP_TEST_RUNNER=1\b", command):
        return 0
    if os.environ.get("SKIP_TEST_RUNNER") == "1":
        return 0

    print(_GUIDANCE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
