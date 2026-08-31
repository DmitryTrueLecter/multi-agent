---
name: issue-search
description: Fallback for a non-Jira tracker. On Jira use `${CLAUDE_PLUGIN_ROOT}/bin/dma board list [--status S] [--label L] [--parent KEY] [--type task|group]` — this skill is for when that command exits 2 (provider unsupported). Searches issues with tracker-agnostic named parameters. Invocation: /dma:issue-search [status:<s>] [label:<l>] [type:<task|group>] [parent:<KEY>].
tools: mcp__linear__list_issues, mcp__linear__get_issue
---

# issue-search

> **Jira projects do not use this skill.** Use `${CLAUDE_PLUGIN_ROOT}/bin/dma board list [--status S] [--label L] [--parent KEY] [--type task|group]`; this file is the path for a tracker that command does not support (it exits `2`).

Search for issues using named filter parameters. The skill translates them to the tracker's native query format.

## Usage

`/dma:issue-search [status:<status>] [label:<label>] [type:<task|group>] [parent:<KEY>]`

| Parameter | Description | Example |
|-----------|-------------|---------|
| `status:<s>` | Filter by workflow status (exact name) | `status:"On Hold"` |
| `label:<l>` | Filter by a single label | `label:agent:team-lead` |
| `type:<t>` | `task` = regular task, `group` = epic/feature-group | `type:group` |
| `parent:<KEY>` | Filter children of a parent issue | `parent:PROJ-50` |

## Steps

Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`. This file covers `linear`; on `jira` use the CLI named above.

1. Read `tasks.team_key` and `tasks.project` from config.
2. Build `mcp__linear__list_issues` parameters:
   - Always pass `team=<team_key>` and `project=<project>`.
   - `status:<s>` → `state="<s>"`
   - `label:<l>` → `label="<l>"`
   - `type:` → ignored (Linear has no issue types; state+label is sufficient to identify queues)
   - `parent:<KEY>` → first call `mcp__linear__get_issue(id=<KEY>)` to get the UUID, then pass `parentId=<uuid>`
3. Call `mcp__linear__list_issues(...)`.
4. Return list of issues: `identifier` (as `key`), `title`, `state.name` (as `status`), `labels`, `parent` (if present).
