#!/usr/bin/env python3
"""Regression tests for write_guard.py (the PreToolUse Write hook).

The hook auto-approves writes under any `.claude/sentinel-inbox/` directory so the
sentinel-flag skill (which writes by absolute path) never raises a prompt a
background subagent cannot answer. It must approve inbox writes regardless of
absolute prefix / worktree / project, and defer everything else.

Run:
    python3 test_write_guard.py          # exits 0 if all pass, 1 otherwise

Extend: one real misfire -> one permanent case.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "write_guard.py")

ALLOW = "allow"
DEFER = "defer"  # exit 0, no decision -> normal permission flow

# (name, file_path, expected)
CASES = [
    ("absolute path in main repo",
     "/home/claude/apps/books/.claude/sentinel-inbox/2026-06-06T17-05-54Z-team-lead-PATTERN-REPEAT.md", ALLOW),
    ("relative path", ".claude/sentinel-inbox/flag.md", ALLOW),
    ("dot-relative path", "./.claude/sentinel-inbox/flag.md", ALLOW),
    ("worktree path (non-root cwd)",
     "/home/claude/apps/books/.worktrees/DMI-71/.claude/sentinel-inbox/flag.md", ALLOW),
    ("a different project root",
     "/srv/other-project/.claude/sentinel-inbox/flag.md", ALLOW),
    ("nested under archive",
     "/home/claude/apps/books/.claude/sentinel-inbox/archive/old.md", ALLOW),
    # must NOT be widened:
    ("source file (defer)", "/home/claude/apps/books/apps/api/main.py", DEFER),
    ("other .claude file (defer)", "/home/claude/apps/books/.claude/config.yml", DEFER),
    ("sentinel procedures dir, not inbox (defer)",
     "/home/claude/apps/books/.claude/sentinel/README.md", DEFER),
    ("lookalike sibling dir (defer)",
     "/home/claude/apps/books/.claude/sentinel-inbox-evil/x.md", DEFER),
    ("inbox substring but wrong parent (defer)",
     "/home/claude/apps/books/notclaude/sentinel-inbox/x.md", DEFER),
    ("empty path (defer)", "", DEFER),
]


def run_hook(file_path: str) -> str:
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps({"tool_input": {"file_path": file_path, "content": "x"}}),
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
