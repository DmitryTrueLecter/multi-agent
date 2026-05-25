#!/usr/bin/env python3
"""PreToolUse hook for Skill — per-agent + per-skill ACL.

Restricts which skills each subagent can invoke via the Skill tool.
Main-session calls (no agent_type in payload) bypass the ACL.

Edit ALLOWED below to grant/revoke skills per role. Add a new entry when:
  - a new agent is added under .claude/agents/
  - a new skill is added under .claude/skills/ that some subagent should call

Exit codes:
  0 - allow
  2 - block (stderr is shown to the model)
"""

from __future__ import annotations

import json
import sys

# Key = agent name (matches `name:` in .claude/agents/<role>.md frontmatter,
# or built-in agent type). Value = set of allowed skill names, or "*" = all.
ALLOWED: dict[str, set[str] | str] = {
    # Project multi-agent roles
    "team-lead": "*",
    "dev":       {"handoff", "task-read", "issue-comment", "sentinel-flag"},
    "qa":        {"handoff", "task-read", "sentinel-flag"},
    "reviewer":  {"handoff", "task-read", "pr-open", "issue-comment", "sentinel-flag"},
    "devops":    {"handoff", "task-read", "pr-open", "issue-comment", "sentinel-flag"},
    "architect": {"sentinel-flag"},
    "sentinel":  {"task-read", "issue-search", "issue-create", "sentinel"},

    # Built-in research / utility agents — no ACL needed
    "general-purpose":    "*",
    "Explore":            "*",
    "Plan":               "*",
    "claude-code-guide":  "*",
    "statusline-setup":   "*",
}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") != "Skill":
        sys.exit(0)

    agent = payload.get("agent_type")
    if agent is None:
        sys.exit(0)

    skill = (payload.get("tool_input") or {}).get("skill") or ""

    allowed = ALLOWED.get(agent)
    if allowed == "*":
        sys.exit(0)
    if allowed is None:
        print(
            f"skill_acl: unknown agent '{agent}'. Add it to ALLOWED in "
            f".claude/hooks/skill_acl.py to grant skill access.",
            file=sys.stderr,
        )
        sys.exit(2)
    if skill in allowed:
        sys.exit(0)

    allowed_list = sorted(allowed) if allowed else "(none)"
    print(
        f"skill_acl: agent '{agent}' is not allowed to invoke skill '{skill}'. "
        f"Allowed for this agent: {allowed_list}. "
        f"Edit .claude/hooks/skill_acl.py to grant access.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
