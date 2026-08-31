---
name: issue-comment
description: Fallback for a non-Jira tracker. On Jira use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <KEY> <body>` — this skill is for when that command exits 2 (provider unsupported). Adds a standalone comment without changing status or labels. Invocation: /dma:issue-comment <ISSUE-KEY> <comment-body>.
tools: mcp__linear__save_comment
---

# issue-comment

> **Jira projects do not use this skill.** Use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <ISSUE-KEY> <body>`; this file is the path for a tracker that command does not support (it exits `2`).

Add a comment to an issue without changing its status or labels.

## Usage

`/dma:issue-comment <ISSUE-KEY> <comment-body>`

## Steps

Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`. This file covers `linear`; on `jira` use the CLI named above.

1. Call `mcp__linear__save_comment(issueId=<ISSUE-KEY>, body=<comment-body>)`.
