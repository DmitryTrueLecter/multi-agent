---
name: task-read
description: Fallback for a non-Jira tracker. On Jira use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>` — this skill is for when that command exits 2 (provider unsupported). Fetches a task's description, status, labels, parent and comments in one call. Invocation: /dma:task-read <ISSUE-KEY>.
tools: mcp__linear__get_issue, mcp__linear__list_comments
---

# task-read

> **Jira projects do not use this skill.** Use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <ISSUE-KEY>`; this file is the path for a tracker that command does not support (it exits `2`).

Fetch a task's complete data from the issue tracker and surface it to the calling agent in one step.

## Usage

`/dma:task-read <ISSUE-KEY>`

## Steps

Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`. This file covers `linear`; on `jira` use the CLI named above.

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
