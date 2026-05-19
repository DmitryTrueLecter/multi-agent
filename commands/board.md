---
description: "Show task board status: in progress, blocked, next up"
---

Show the current state of the task board.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key` and `tasks.workflow.statuses` (semantic key → tracker display name). Resolve every `<statuses.X>` reference below through that map.

Make the following `/issue-search` calls and present a summary:

1. **Overview** — run these 6 queries in parallel and combine:
   - `/issue-search status:<statuses.in_progress>`
   - `/issue-search status:<statuses.on_hold>`
   - `/issue-search status:<statuses.qa>`
   - `/issue-search status:<statuses.code_review>`
   - `/issue-search status:<statuses.to_do>`
   - `/issue-search status:<statuses.awaiting_merge>`

   Report total counts per status. Include `awaiting_merge` even though tasks there carry no `agent:` label — the status is the queue signal.

2. **On hold** — from the `on_hold` results: list tasks with `agent:team-lead` (key, summary, area/agent labels) — these need attention first!

3. **Awaiting merge** — from the `awaiting_merge` results: list every task (key, summary, area). The user merges or declines the PR; `/pr-feedback` reconciles the result on the next `/run`.

4. **In progress** — from the `in_progress` results: group by `agent:` label (shows who is doing what right now).

5. **QA** and **Code Review** — list from the `qa` and `code_review` result sets (key, summary, area/agent labels).

6. **Next up** — from the `to_do` results: list tasks with `agent:dev` label whose blocking links are all `done` (ready to launch).

7. **Recently completed** — `/issue-search status:<statuses.done>` — show last 3-5 tasks (sort by last-updated descending).

Keep it concise. This is a status check, not a full board dump.
