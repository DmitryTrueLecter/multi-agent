#!/usr/bin/env python3
"""PreToolUse hook: auto-approve the tracker/VCS MCP calls the agents rely on.

Claude Code has no include mechanism for `permissions.allow`, and a plugin
cannot ship a permissions allowlist. But a plugin CAN ship hooks, and a hook's
`permissionDecision: allow` is honored. So instead of an allowlist in every
project's settings.json, this hook approves the exact set of MCP tools the
agents use — the same curated set listed in `permissions/atlassian.json` and
`permissions/linear.json` beside the plugin.

Only the listed tools are approved (e.g. `jira_get_issue`, `jira_transition_issue`),
never the whole server — a destructive tool not on the list still defers to the
normal permission flow. Non-MCP calls and unlisted MCP calls exit 0 with no
decision (this hook only widens, never blocks).

Exit codes:
  0 - emit "allow" JSON for a listed MCP tool; otherwise no decision (defer)
"""

from __future__ import annotations

import json
import os
import sys

# permissions/ sits beside hooks/ under the plugin root; resolve from this
# script's own location so it works regardless of how the plugin was loaded.
PERM_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "permissions"
)
ALLOW_FILES = ("atlassian.json", "linear.json")


def allowed_tools() -> set[str]:
    tools: set[str] = set()
    for name in ALLOW_FILES:
        try:
            with open(os.path.join(PERM_DIR, name)) as f:
                tools.update(json.load(f).get("permissions", {}).get("allow", []))
        except (FileNotFoundError, ValueError):
            continue
    return tools


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = payload.get("tool_name") or ""
    if not tool.startswith("mcp__"):
        sys.exit(0)

    if tool in allowed_tools():
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "permissionDecisionReason": "dma: curated tracker/VCS MCP call",
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
