---
description: "Show task board status: in progress, blocked, next up"
---

Show the current state of the task board.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key`.

Make the following `/issue-search` calls and present a summary:

1. **Overview** — run these 5 queries in parallel and combine:
   - `/issue-search status:"In Progress"`
   - `/issue-search status:"On Hold"`
   - `/issue-search status:QA`
   - `/issue-search status:"Code Review"`
   - `/issue-search status:"To Do"`

   Report total counts per status. Filter to issues that have at least one `agent:` label (ignore non-agent issues).

2. **On hold** — from the `On Hold` results: list tasks with `agent:team-lead` or `agent:user` labels (key, summary, area/agent labels) — these need attention first!

3. **In progress** — from the `In Progress` results: group by `agent:` label (shows who is doing what right now).

4. **QA** and **Code Review** — list from respective result sets (key, summary, area/agent labels).

5. **Next up** — from the `To Do` results: list tasks with `agent:dev` label whose blocking links are all Done (ready to launch).

6. **Recently completed** — `/issue-search status:Done` — show last 3-5 tasks (sort by last-updated descending).

Keep it concise. This is a status check, not a full board dump.
