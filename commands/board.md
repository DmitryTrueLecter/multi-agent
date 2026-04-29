---
description: "Show task board status: in progress, blocked, next up"
---

Show the current state of the Jira task board.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key`.

Use `jira_search` with JQL `project = <project_key> AND labels in ("agent:dev", "agent:qa", "agent:reviewer", "agent:team-lead") AND status != Done ORDER BY status, rank` and present a summary:

1. **Overview**: how many tasks total / done / in progress / QA / code review / on hold / to do.
2. **Decision needed (On Hold + `needs-decision`)**: tasks with status "On Hold" AND label `needs-decision` (key, summary, area, parent if any) — these need team-lead attention first.
3. **Awaiting children (On Hold, no `needs-decision`)**: tasks with status "On Hold" AND label `agent:team-lead` AND no `needs-decision` — parent tasks waiting for their children to finish. Not directly actionable, but useful for visibility.
4. **In progress**: tasks with status "In Progress", grouped by `agent:` label (shows who is doing what right now: dev, qa, reviewer, or team-lead).
5. **QA**: tasks with status "QA".
6. **Code Review**: tasks with status "Code Review" (key, summary, area).
7. **Team-lead continuation (To Do + `agent:team-lead`)**: parent tasks whose children are all Done and are waiting for team-lead to continue them.
8. **Next up (To Do + `agent:dev`)**: tasks that are "To Do" with `agent:dev` whose blocking links are all Done (ready to launch).
9. **Recently completed**: last 3-5 tasks with status "Done" (use separate JQL: `project = <project_key> AND status = Done ORDER BY updated DESC`).

Keep it concise. This is a status check, not a full board dump.
