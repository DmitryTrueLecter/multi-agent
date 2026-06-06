#!/usr/bin/env python3
"""PreToolUse hook for Write: auto-approve sentinel-inbox flag writes.

The sentinel-flag skill writes flags by ABSOLUTE path
(<abs-project-root>/.claude/sentinel-inbox/<file>). A relative allow rule
(Write(.claude/sentinel-inbox/**)) does not reliably match an absolute-path tool
call — relative patterns are anchored to the project root, and agents running in a
git worktree have a non-root cwd — so the write raises an interactive prompt that a
background subagent cannot answer. Claude Code has no portable absolute-path glob,
and the skill must keep the absolute path (a relative path would misfile flags into
a worktree's own .claude/sentinel-inbox/ where sentinel never looks).

This hook matches by path *content* instead of by anchor: any Write whose target
resolves under a `.claude/sentinel-inbox/` directory is approved. Portable across
machines, projects, and worktrees. Everything else defers to the normal permission
flow (exit 0, no decision) — this hook only widens, never blocks.

Per Claude Code docs, an "allow" decision still respects deny and ask rules.

Exit codes:
  0 - emit "allow" JSON for sentinel-inbox writes; otherwise no decision (defer)
"""

from __future__ import annotations

import json
import posixpath
import sys


def is_sentinel_inbox(path: str) -> bool:
    norm = posixpath.normpath(path.replace("\\", "/"))
    parts = norm.split("/")
    return any(
        parts[i] == ".claude" and parts[i + 1] == "sentinel-inbox"
        for i in range(len(parts) - 1)
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if path and is_sentinel_inbox(path):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "permissionDecisionReason": "sentinel-inbox flag write (portable path-content match)",
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
