---
description: "Show task board status: in progress, blocked, next up"
---

Show the current state of the Jira task board.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key`.

Use `jira_search` with JQL `project = <project_key> AND labels in ("agent:dev", "agent:qa", "agent:reviewer", "agent:team-lead") AND status != Done ORDER BY status, rank` and present a summary:

1. **Overview**: how many tasks total / done / in progress / QA / code review / on hold / to do
2. **On hold**: list tasks with status "On Hold" (key, summary, area/agent labels) — these need attention first!
3. **In progress**: list tasks with status "In Progress", grouped by `agent:` label (shows who is doing what right now: dev, qa, reviewer, or team-lead)
4. **QA**: list tasks with status "QA" (key, summary, area/agent labels)
5. **Code Review**: list tasks with status "Code Review" (key, summary, area/agent labels)
6. **Next up**: list tasks that are "To Do" whose blocking links are all Done (ready to launch)
7. **Recently completed**: last 3-5 tasks with status "Done" (use separate JQL: `project = <project_key> AND status = Done ORDER BY updated DESC`)

Keep it concise. This is a status check, not a full board dump.
