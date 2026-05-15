---
name: issue-claim
description: Atomically claim an issue for the current agent by transitioning it to In Progress. Returns success or failure — caller decides what to do on failure (e.g. skip and try next). On success, returns the claimed issue's current data (same output as /task-read). Invocation: /issue-claim <ISSUE-KEY>.
tools: mcp__atlassian__jira_transition_issue, mcp__atlassian__jira_get_issue
---

# issue-claim

Claim an issue by transitioning it to `In Progress`, then return its full data.

## Usage

`/issue-claim <ISSUE-KEY>`

## Steps

1. Call `mcp__atlassian__jira_transition_issue` with `issue_key = <ISSUE-KEY>` and `transition_name = "In Progress"`.
2. **If the transition is rejected** (Jira returns an error — the issue already left the expected source status, meaning another runner claimed it first): return a failure signal to the caller. Do NOT retry. The caller decides whether to skip and try another issue or stop.
3. **If the transition succeeds**: call `mcp__atlassian__jira_get_issue` to read the current issue state and return the same normalized output as `/task-read`:
   - **key** — issue key
   - **summary** — issue summary
   - **status** — current status (should be `In Progress`)
   - **labels** — full label list
   - **parent** — `{ key, summary, type }` where `type` is `"group"` if parent is an Epic, `"task"` otherwise; null if no parent
   - **description** — full description text
   - **comments** — all comments, newest-first
