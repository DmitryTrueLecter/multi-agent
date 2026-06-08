---
name: issue-update-labels
description: Update labels on an issue without changing its status. Accepts add/remove lists; preserves all other labels. Use for label-only changes not covered by /dma:handoff. Invocation: /dma:issue-update-labels <ISSUE-KEY> [add:<l1>,<l2>] [remove:<l1>,<l2>].
tools: mcp__atlassian__jira_get_issue, mcp__atlassian__jira_update_issue, mcp__linear__get_issue, mcp__linear__save_issue
---

# issue-update-labels

Update labels on an issue without touching its status.

## Usage

`/dma:issue-update-labels <ISSUE-KEY> [add:<l1>,<l2>] [remove:<l1>,<l2>]`

At least one of `add:` or `remove:` must be provided.

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Call `mcp__atlassian__jira_get_issue(issue_key=<ISSUE-KEY>)` to get current labels.
2. Build new label list: start from current, remove each label in `remove:` set, add each in `add:` set.
3. Call `mcp__atlassian__jira_update_issue(issue_key=<ISSUE-KEY>, fields={"labels": [<new list>]})`.
4. Confirm what changed.

---

## linear

1. Call `mcp__linear__get_issue(id=<ISSUE-KEY>)` to get current labels.
2. Build new label list: start from current, remove each label in `remove:` set, add each in `add:` set.
3. Call `mcp__linear__save_issue(id=<ISSUE-KEY>, labels=[<new list>])`.
4. Confirm what changed.
