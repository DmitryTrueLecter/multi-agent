---
name: task-read
description: Fetch a task's full data — description, status, labels, parent, and all comments — in one call. Returns normalized output for agent consumption. Use at the start of any agent workflow instead of calling tracker tools directly. Invocation: `/dma:task-read <ISSUE-KEY>`.
tools: mcp__atlassian__jira_get_issue, mcp__linear__get_issue, mcp__linear__list_comments
---

# task-read

Fetch a task's complete data from the issue tracker and surface it to the calling agent in one step.

## Usage

`/dma:task-read <ISSUE-KEY>`

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Call `mcp__atlassian__jira_get_issue(issue_key=<ISSUE-KEY>, fields="summary,status,labels,parent,description,comment")`. Name `parent` explicitly in the field list — `fields="*all"` omits it, so relying on `*all` makes step 2 report `parent: null` even for an Epic-parented task and misdirects downstream base-branch selection.
2. Return to the calling agent:
   - **key** — `fields.key`
   - **title** — `fields.summary`
   - **status** — `fields.status.name`
   - **labels** — `fields.labels`
   - **parent** — if `fields.parent` exists: `{ key: fields.parent.key, title: fields.parent.fields.summary, type: "group" if fields.parent.fields.issuetype.name == "Epic" else "task" }`. Null if no parent.
   - **description** — `fields.description`
   - **comments** — `fields.comment.comments` ordered newest-first: `{ author: displayName, created, body }`

---

## linear

1. Call `mcp__linear__get_issue(id=<ISSUE-KEY>)`.
2. Call `mcp__linear__list_comments(issueId=<ISSUE-KEY>, orderBy="createdAt")`.
3. Return to the calling agent:
   - **key** — `identifier`
   - **title** — `title`
   - **status** — `state.name`
   - **labels** — `labels` array
   - **parent** — if `parent` exists: `{ key: parent.identifier, title: parent.title, type: "group" }`. Null if no parent. (All Linear parents are feature-groups — always `"group"`.)
   - **description** — `description`
   - **comments** — from `list_comments`, ordered newest-first: `{ author: user.name, created: createdAt, body }`
