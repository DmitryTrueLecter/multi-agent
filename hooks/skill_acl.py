#!/usr/bin/env python3
"""PreToolUse hook for Skill — per-agent + per-skill ACL.

Restricts which skills each subagent can invoke via the Skill tool.
Main-session calls (no agent_type in payload) bypass the ACL.

Shipped inside the `dma` plugin, every plugin-contributed agent and skill is
namespaced (`dma:dev`, `dma:handoff`). This hook strips the `dma:` prefix from
both the agent_type and the skill name before matching, so the ALLOWED table
below stays written in bare names. Built-in agents (general-purpose, Explore, …)
arrive un-namespaced and match unchanged. Renaming the plugin = edit PLUGIN only.

Edit ALLOWED below to grant/revoke skills per role. Add a new entry when:
  - a new agent is added under agents/ in the plugin
  - a new skill is added under skills/ that some subagent should call

Exit codes:
  0 - allow
  2 - block (stderr is shown to the model)
"""

from __future__ import annotations

import json
import sys

# Namespace prefix this plugin's components carry in tool payloads.
PLUGIN = "dma"


def strip_ns(name: str) -> str:
    """Drop this plugin's `dma:` namespace prefix; leave other names untouched."""
    prefix = PLUGIN + ":"
    return name[len(prefix):] if name.startswith(prefix) else name


# Key = bare agent name (the `name:` in agents/<role>.md frontmatter, minus the
# plugin namespace; or a built-in agent type). Value = set of allowed bare skill
# names, or "*" = all.
ALLOWED: dict[str, set[str] | str] = {
    # Project multi-agent roles
    "team-lead": "*",
    "dev":       {"handoff", "task-read", "issue-comment", "sentinel-flag"},
    "qa":        {"handoff", "task-read", "sentinel-flag"},
    "reviewer":  {"handoff", "task-read", "pr-open", "issue-comment", "sentinel-flag"},
    "devops":    {"handoff", "task-read", "pr-open", "issue-comment", "sentinel-flag"},
    "architect": {"sentinel-flag"},
    "sentinel":  {"task-read", "issue-search", "issue-create", "issue-comment",
                  "handoff", "pr-open", "sentinel-flag", "sentinel"},

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

    agent_raw = payload.get("agent_type")
    if agent_raw is None:
        sys.exit(0)

    agent = strip_ns(agent_raw)
    skill = strip_ns((payload.get("tool_input") or {}).get("skill") or "")

    allowed = ALLOWED.get(agent)
    if allowed == "*":
        sys.exit(0)
    if allowed is None:
        print(
            f"skill_acl: unknown agent '{agent_raw}'. Add '{agent}' to ALLOWED in "
            f"the dma plugin's hooks/skill_acl.py to grant skill access.",
            file=sys.stderr,
        )
        sys.exit(2)
    if skill in allowed:
        sys.exit(0)

    allowed_list = sorted(allowed) if allowed else "(none)"
    print(
        f"skill_acl: agent '{agent_raw}' is not allowed to invoke skill '{skill}'. "
        f"Allowed for this agent: {allowed_list}. "
        f"Edit the dma plugin's hooks/skill_acl.py to grant access.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
