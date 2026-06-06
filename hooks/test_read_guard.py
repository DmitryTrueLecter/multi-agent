#!/usr/bin/env python3
"""Regression tests for read_guard.py (the PreToolUse Read hook).

The hook auto-approves reads of any `.claude/*` file so the agent bootstrap (which
reads config by absolute path) never raises a prompt a background subagent cannot
answer. It must approve `.claude` reads regardless of absolute prefix / worktree /
project, and defer everything else.

Run:
    python3 test_read_guard.py          # exits 0 if all pass, 1 otherwise

Extend: one real misfire -> one permanent case.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_guard.py")

ALLOW = "allow"
DEFER = "defer"  # exit 0, no decision -> normal permission flow

# (name, file_path, expected)
CASES = [
    ("absolute config in main repo",
     "/home/claude/apps/books/.claude/config.yml", ALLOW),
    ("relative config", ".claude/config.yml", ALLOW),
    ("dot-relative config", "./.claude/config.yml", ALLOW),
    ("area overlay", "/home/claude/apps/books/.claude/areas/api/dev.yml", ALLOW),
    ("sentinel procedures dir", "/home/claude/apps/books/.claude/sentinel/full-audit.md", ALLOW),
    ("worktree path (non-root cwd)",
     "/home/claude/apps/books/.worktrees/DMI-71/.claude/config.yml", ALLOW),
    ("a foreign macOS project root",
     "/Users/someone/projects/other-app/.claude/config.yml", ALLOW),
    ("arbitrary other project root",
     "/srv/other-project/.claude/arch.yml", ALLOW),
    # must NOT be widened:
    ("source file (defer)", "/home/claude/apps/books/apps/api/main.py", DEFER),
    ("dotenv inside .claude (defer to deny)",
     "/home/claude/apps/books/.claude/.env", DEFER),
    ("project .env (defer to deny)", "/home/claude/apps/books/.env", DEFER),
    ("lookalike sibling dir (defer)",
     "/home/claude/apps/books/.claude-evil/config.yml", DEFER),
    (".claude substring but wrong segment (defer)",
     "/home/claude/apps/books/notdotclaude/config.yml", DEFER),
    ("empty path (defer)", "", DEFER),
]


def run_hook(file_path: str) -> str:
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps({"tool_input": {"file_path": file_path}}),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return f"other(exit={proc.returncode})"
    out = proc.stdout.strip()
    if not out:
        return DEFER
    try:
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"]
    except Exception:
        return f"other(bad-json:{out!r})"


def main() -> int:
    failures = []
    for name, path, expected in CASES:
        got = run_hook(path)
        if got != expected:
            failures.append((name, expected, got))

    if failures:
        print(f"FAIL: {len(failures)} of {len(CASES)} case(s) failed:")
        for name, expected, got in failures:
            print(f"  {name}: expected={expected} got={got}")
        return 1
    print(f"OK: all {len(CASES)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
