---
name: issue-claim
description: Atomically claim an issue by transitioning it to In Progress. Returns the full issue data on success (same shape as /dma:task-read), or a failure signal if another runner already claimed it. Caller decides what to do on failure. Invocation: /dma:issue-claim <ISSUE-KEY>.
tools: mcp__atlassian__jira_transition_issue, mcp__atlassian__jira_get_issue, mcp__linear__save_issue, mcp__linear__get_issue, mcp__linear__list_comments
---

# issue-claim

Claim an issue by transitioning it to the `in_progress` status, then return its full data.

## Usage

`/dma:issue-claim <ISSUE-KEY>`

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Read `tasks.jira.transitions.in_progress` from config — the numeric transition id. If missing or `0`: stop and report — run `/dma:sentinel-bootstrap-jira` to populate the map.
2. `mcp__atlassian__jira_transition_issue(issue_key=<ISSUE-KEY>, transition_id=<id>)`.
3. **If rejected** (Jira returns an error — the issue's current status does not expose this transition, meaning another runner claimed it first or the queue filter and actual status drifted): return failure to the caller. Do NOT retry.
4. **If success**: call `mcp__atlassian__jira_get_issue(issue_key=<ISSUE-KEY>)` and return the normalized data (same shape as `/dma:task-read` output).

---

## linear

1. Call `mcp__linear__save_issue(id=<ISSUE-KEY>, state="In Progress")`.
2. Call `mcp__linear__get_issue(id=<ISSUE-KEY>)` to verify the claim.
3. **If `state.name` ≠ `"In Progress"`** — another runner claimed it first: return failure to the caller.
4. **If `state.name == "In Progress"`**: also call `mcp__linear__list_comments(issueId=<ISSUE-KEY>, orderBy="createdAt")`, then return normalized data (same shape as `/dma:task-read` output).
