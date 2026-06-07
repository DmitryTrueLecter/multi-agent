---
description: "Team-lead actions: pass a spec path to decompose, or invoke without args for board status. The main session runs as team-lead via `claude --agent dma:team-lead`; this command is for explicit triggers."
---

The main session runs as team-lead when launched with `claude --agent dma:team-lead`, so the role definition is already in your system prompt. This command is an explicit trigger to do one of:

**With `$ARGUMENTS` containing a path to a spec / task description:**
- Read the spec.
- Read relevant architecture docs referenced in it.
- Decompose into Jira issues following the rules in `${CLAUDE_PLUGIN_ROOT}/agents/team-lead.md`.
- Present the plan to the user for approval.

**Without arguments:**
- Use `mcp__atlassian__jira_search` to get the current state of the board (project key from `${CLAUDE_PROJECT_DIR}/.claude/config.yml`).
- Report what's done, what's in progress, what's ready to run next.
