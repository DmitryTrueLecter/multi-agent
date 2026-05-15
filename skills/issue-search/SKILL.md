---
name: issue-search
description: Search issues using tracker-agnostic named parameters. Reads project/team key from .claude/config.yml. Invocation: /issue-search [status:<s>] [label:<l>] [type:<task|group>] [parent:<KEY>].
tools: mcp__atlassian__jira_search, mcp__linear__list_issues, mcp__linear__get_issue
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

## Steps

1. Read `.claude/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Read `tasks.project_key` from config.
2. Translate parameters to JQL:
   - `status:<s>` → `status = "<s>"`
   - `label:<l>` → `labels = "<l>"`
   - `type:group` → `issuetype = Epic`
   - `type:task` → `issuetype = Task`
   - `parent:<KEY>` → `parent = "<KEY>"`
   - Prepend `project = <project_key> AND` unless `parent:` is the only parameter.
   - Combine conditions with `AND`.
3. Call `mcp__atlassian__jira_search(jql=<assembled-query>)`.
4. Return list of issues: `key`, `summary` (as `title`), `status`, `labels`, `parent` (if present).

---

## linear

1. Read `tasks.team_key` and `tasks.project` from config.
2. Build `mcp__linear__list_issues` parameters:
   - Always pass `team=<team_key>` and `project=<project>`.
   - `status:<s>` → `state="<s>"`
   - `label:<l>` → `label="<l>"`
   - `type:` → ignored (Linear has no issue types; state+label is sufficient to identify queues)
   - `parent:<KEY>` → first call `mcp__linear__get_issue(id=<KEY>)` to get the UUID, then pass `parentId=<uuid>`
3. Call `mcp__linear__list_issues(...)`.
4. Return list of issues: `identifier` (as `key`), `title`, `state.name` (as `status`), `labels`, `parent` (if present).
