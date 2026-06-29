---
name: issue-comment
description: Add a standalone comment to an issue without changing its status or labels. Use for progress updates and error notifications that are not part of a handoff. Invocation: /dma:issue-comment <ISSUE-KEY> <comment-body>.
tools: mcp__atlassian__jira_add_comment, mcp__linear__save_comment
---

# issue-comment

Add a comment to an issue without changing its status or labels.

## Usage

`/dma:issue-comment <ISSUE-KEY> <comment-body>`

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Call `mcp__atlassian__jira_add_comment(issue_key=<ISSUE-KEY>, body=<comment-body>)`.

---

## linear

1. Call `mcp__linear__save_comment(issueId=<ISSUE-KEY>, body=<comment-body>)`.
