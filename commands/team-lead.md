---
description: "Team-lead actions: pass a spec path to decompose, or invoke without args for board status. Main session is already team-lead — this command is for explicit triggers."
---

The main session is already running under the team-lead role (set via `.claude/settings.json` → `agent: team-lead`), so the role definition is already in your system prompt. This command is just an explicit trigger to do one of:

**With `$ARGUMENTS` containing a path to a spec / task description:**
- Read the spec.
- Read relevant architecture docs referenced in it.
- Decompose into Jira issues following the rules in `.claude/agents/team-lead.md`.
- Present the plan to the user for approval.

**Without arguments:**
- Use `jira_search` to get the current state of the board (project key from `.claude/config.yml`).
- Report what's done, what's in progress, what's ready to run next.
