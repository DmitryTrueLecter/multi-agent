#!/usr/bin/env python3
"""PreToolUse hook for Write — block creation of markdown files.

Refuses any Write call where the target file path ends with `.md`
(case-insensitive). Applies to all agents (main + subagents), since
PreToolUse fires regardless of who invokes the tool.

Exit codes:
  0 - allow
  2 - block (stderr is shown to the model)
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") != "Write":
        sys.exit(0)

    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path.lower().endswith(".md"):
        sys.exit(0)

    print(
        f"no_md_writes: refusing to create markdown file '{file_path}'. "
        f"Edit .claude/hooks/no_md_writes.py to relax this rule.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
