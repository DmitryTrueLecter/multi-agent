#!/usr/bin/env python3
"""PreToolUse hook for Read: auto-approve reads of project `.claude/*` files.

Every agent bootstrap reads its config by ABSOLUTE path: the prompt carries
`<abs-project-root>` and the agent prefixes it onto every `.claude/*` Read
(agents/dev.md, qa.md, reviewer.md, devops.md, sentinel.md — "the Read tool requires
absolute paths"). A relative allow rule (Read(.claude/**)) does not reliably match an
absolute-path tool call — relative patterns are anchored to the project root, and
agents running in a git worktree have a non-root cwd — so the read raises an
interactive prompt that a background subagent cannot answer. Claude Code has no
portable absolute-path glob, so each new machine / user / checkout accretes a
machine-specific Read(//abs/path/**) rule in settings.local.json; a fresh root just
starts the cycle over.

This hook matches by path *content* instead of by anchor: any Read whose target
resolves under a `.claude/` directory is approved. Portable across machines,
projects, and worktrees — mirrors write_guard.py. Everything else defers to the
normal permission flow (exit 0, no decision) — this hook only widens, never blocks.

Per Claude Code docs, an "allow" decision still respects deny and ask rules, so the
settings.json `Read(**/.env)` deny still wins. As defence in depth this hook also
declines to approve a dotenv basename, leaving such reads to the deny/ask flow.

Exit codes:
  0 - emit "allow" JSON for .claude reads; otherwise no decision (defer)
"""

from __future__ import annotations

import json
import posixpath
import sys


def is_claude_read(path: str) -> bool:
    norm = posixpath.normpath(path.replace("\\", "/"))
    parts = norm.split("/")
    if parts and parts[-1].startswith(".env"):
        return False
    return ".claude" in parts


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if path and is_claude_read(path):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "permissionDecisionReason": ".claude config read (portable path-content match)",
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
