---
name: issue-claim
description: Fallback for a non-Jira tracker. On Jira use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim <KEY>` — this skill is for when that command exits 2 (provider unsupported). Atomically claims an issue by transitioning it to In Progress. Invocation: /dma:issue-claim <ISSUE-KEY>.
tools: mcp__linear__save_issue, mcp__linear__get_issue, mcp__linear__list_comments
---

# issue-claim

> **Jira projects do not use this skill.** Use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim <ISSUE-KEY>`; this file is the path for a tracker that command does not support (it exits `2`).

Claim an issue by transitioning it to the `in_progress` status, then return its full data.

## Usage

`/dma:issue-claim <ISSUE-KEY>`

## Steps

Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`. This file covers `linear`; on `jira` use the CLI named above.

1. Call `mcp__linear__save_issue(id=<ISSUE-KEY>, state="In Progress")`.
2. Call `mcp__linear__get_issue(id=<ISSUE-KEY>)` to verify the claim.
3. **If `state.name` ≠ `"In Progress"`** — another runner claimed it first: return failure to the caller.
4. **If `state.name == "In Progress"`**: also call `mcp__linear__list_comments(issueId=<ISSUE-KEY>, orderBy="createdAt")`, then return normalized data (same shape as `/dma:task-read` output).
