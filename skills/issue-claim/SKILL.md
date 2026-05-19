---
name: issue-claim
description: Atomically claim an issue by transitioning it to In Progress. Returns the full issue data on success (same shape as /task-read), or a failure signal if another runner already claimed it. Caller decides what to do on failure. Invocation: /issue-claim <ISSUE-KEY>.
tools: mcp__atlassian__jira_get_transitions, mcp__atlassian__jira_transition_issue, mcp__atlassian__jira_get_issue, mcp__linear__save_issue, mcp__linear__get_issue, mcp__linear__list_comments
---

# issue-claim

Claim an issue by transitioning it to `In Progress`, then return its full data.

## Usage

`/issue-claim <ISSUE-KEY>`

## Steps

1. Read `.claude/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Resolve the transition id for `In Progress`:
   - `mcp__atlassian__jira_get_transitions(issue_key=<ISSUE-KEY>)` returns transitions available from the current status, each as `{id, name, to_status}`.
   - Match by `to_status == "In Progress"`, capture `id`. If no match: return failure to the caller — the issue is not in a status that exposes the `In Progress` transition (already claimed, or wrong queue).
2. `mcp__atlassian__jira_transition_issue(issue_key=<ISSUE-KEY>, transition_id=<id>)`.
3. **If rejected** (Jira returns an error — issue raced and left the expected status between steps 1 and 2): return failure to the caller. Do NOT retry.
4. **If success**: call `mcp__atlassian__jira_get_issue(issue_key=<ISSUE-KEY>)` and return the normalized data (same shape as `/task-read` output).

---

## linear

1. Call `mcp__linear__save_issue(id=<ISSUE-KEY>, state="In Progress")`.
2. Call `mcp__linear__get_issue(id=<ISSUE-KEY>)` to verify the claim.
3. **If `state.name` ≠ `"In Progress"`** — another runner claimed it first: return failure to the caller.
4. **If `state.name == "In Progress"`**: also call `mcp__linear__list_comments(issueId=<ISSUE-KEY>, orderBy="createdAt")`, then return normalized data (same shape as `/task-read` output).
