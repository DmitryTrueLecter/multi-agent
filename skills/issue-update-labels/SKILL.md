---
name: issue-update-labels
description: Update the labels on an issue without changing its status. Accepts explicit add/remove lists; always preserves unlisted labels. Use for label-only changes that are not part of a handoff (e.g. removing agent:team-lead from an Epic while keeping it in In Progress). Invocation: /issue-update-labels <ISSUE-KEY> [add:<l1>,<l2>] [remove:<l1>,<l2>].
tools: mcp__atlassian__jira_get_issue, mcp__atlassian__jira_update_issue
---

# issue-update-labels

Update labels on an issue without touching its status.

## Usage

`/issue-update-labels <ISSUE-KEY> [add:<l1>,<l2>] [remove:<l1>,<l2>]`

At least one of `add:` or `remove:` must be provided.

## Steps

1. Read the issue via `mcp__atlassian__jira_get_issue` to get the current full label list.
2. Build the new label list: start from the current list, remove each label in the `remove:` set (if present), add each label in the `add:` set (if not already present).
3. Call `mcp__atlassian__jira_update_issue` with the complete new label list (the MCP replaces the field as a whole).
4. Confirm to the caller what changed.
