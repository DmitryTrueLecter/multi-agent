---
name: issue-search
description: Search issues using tracker-agnostic named parameters. Reads project/team key from .claude/config.yml. Invocation: /issue-search [status:<s>] [label:<l>] [type:<task|group>] [parent:<KEY>].
tools: mcp__atlassian__jira_search
---

# issue-search

Search for issues using named filter parameters. The skill translates them to the tracker's native query format.

## Usage

`/issue-search [status:<status>] [label:<label>] [type:<task|group>] [parent:<KEY>]`

| Parameter | Description | Example |
|-----------|-------------|---------|
| `status:<s>` | Filter by workflow status (exact name) | `status:"On Hold"` |
| `label:<l>` | Filter by a single label | `label:agent:team-lead` |
| `type:<t>` | `task` = regular task, `group` = epic/feature-group | `type:group` |
| `parent:<KEY>` | Filter children of a parent issue | `parent:PROJ-50` |

All parameters are optional and combinable. If no parameters are given, returns all open issues.

## Steps

1. Read `<project-root>/.claude/config.yml` → `tasks.project_key`.
2. Translate the named parameters to a JQL query:
   - `status:<s>` → `status = "<s>"`
   - `label:<l>` → `labels = "<l>"`
   - `type:group` → `issuetype = Epic`
   - `type:task` → `issuetype = Task`
   - `parent:<KEY>` → `parent = "<KEY>"`
   - Always prepend `project = <project_key>` unless `parent:` is the only parameter (parent search is already project-scoped).
   - Combine multiple conditions with `AND`.
3. Call `mcp__atlassian__jira_search` with the assembled JQL.
4. Return the list of matching issues to the caller. For each: `key`, `summary`, `status`, `labels`, `parent` (if present).
