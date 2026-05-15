---
name: task-read
description: Fetch a task's full data — description, status, labels, parent, and all comments — in one call. Returns normalized output for agent consumption. Use at the start of any agent workflow instead of calling tracker tools directly. Invocation: `/task-read <ISSUE-KEY>`.
tools: mcp__atlassian__jira_get_issue
---

# task-read

Fetch a task's complete data from the issue tracker and surface it to the calling agent in one step.

## Usage

`/task-read <ISSUE-KEY>`

## Steps

1. Call `mcp__atlassian__jira_get_issue(issue_key=<ISSUE-KEY>)`.
2. Return the following to the calling agent:

   - **key** — issue key (e.g. `PROJ-123`)
   - **summary** — issue summary line
   - **status** — current workflow status name
   - **labels** — full label list as-is
   - **parent** — if the issue has a parent:
     `{ key: fields.parent.key, summary: fields.parent.fields.summary, type: "group" | "task" }`
     where `type` is `"group"` if `fields.parent.fields.issuetype.name == "Epic"`, otherwise `"task"`.
     Return `null` if no parent.
   - **description** — full description text
   - **comments** — all entries from `fields.comment.comments`, ordered newest-first. For each: `{ author: displayName, created, body }`.

Do not filter or truncate any field. The calling agent decides what is relevant.
