---
name: issue-comment
description: Add a standalone comment to an issue without changing its status or labels. Use for progress updates and mid-workflow notifications that are not part of a handoff. Invocation: /issue-comment <ISSUE-KEY> <comment-body>.
tools: mcp__atlassian__jira_add_comment
---

# issue-comment

Add a comment to an issue without changing its status or labels.

## Usage

`/issue-comment <ISSUE-KEY> <comment-body>`

## Steps

1. Call `mcp__atlassian__jira_add_comment` with `issue_key = <ISSUE-KEY>` and `body = <comment-body>`.
2. Confirm to the caller that the comment was posted.
