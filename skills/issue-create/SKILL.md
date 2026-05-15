---
name: issue-create
description: Create a new issue in the issue tracker — type, summary, description, labels, parent/epic link, and dependency links. Reads project/team key from .claude/config.yml. Invocation: /issue-create <type> <summary> [parent:<KEY>] [labels:<l1>,<l2>] [blocks:<KEY1>,<KEY2>] [description:<text>].
tools: mcp__atlassian__jira_create_issue, mcp__atlassian__jira_create_issue_link, mcp__atlassian__jira_link_to_epic, mcp__linear__save_issue
---

# issue-create

Create an issue in the issue tracker with all required fields and optional links.

## Usage

`/issue-create <type> <summary> [options]`

| Argument | Required | Description |
|----------|----------|-------------|
| `<type>` | yes | `task` or `group` (`group` = Epic/feature-group) |
| `<summary>` | yes | Concise issue title |
| `parent:<KEY>` | optional | Parent group key — links the new task to this group |
| `labels:<l1>,<l2>` | optional | Comma-separated labels (e.g. `area:api,agent:dev`) |
| `blocks:<KEY1>,<KEY2>` | optional | Issues this new issue blocks |
| `description:<text>` | optional | Issue description (Markdown) |

## Steps

1. Read `.claude/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

1. Read `tasks.project_key` from config.
2. Map `type`: `group` → `issue_type="Epic"`, `task` → `issue_type="Task"`.
3. Call `mcp__atlassian__jira_create_issue`:
   - `project_key`: from config
   - `summary`: from `<summary>`
   - `issue_type`: mapped above
   - `description`: from `description:` if provided
   - `additional_fields`: `{"labels": [<labels>]}` if labels given; also `{"parent": "<parent-KEY>"}` if `parent:` given and type is `task`
4. Capture the new issue key.
5. If `parent:<KEY>` given and type is `task`, also call `mcp__atlassian__jira_link_to_epic(issue_key=<new-key>, epic_key=<parent-KEY>)`.
6. If `blocks:<KEY1>,<KEY2>` given, for each key call `mcp__atlassian__jira_create_issue_link(link_type="Blocks", inward_issue_key=<new-key>, outward_issue_key=<blocked-key>)`.
7. Return the created issue key.

---

## linear

1. Read `tasks.team_key` from config.
2. Call `mcp__linear__save_issue` (omit `id` to create):
   - `team`: `<team_key>`
   - `title`: from `<summary>`
   - `description`: from `description:` if provided
   - `labels`: `[<labels>]` if given
   - `state`: `"Todo"` if type is `task`; omit for `group` (parent issues have no initial state)
   - `parentId`: `"<parent-KEY>"` if `parent:` given and type is `task`
   - `blockedBy`: `["<KEY1>","<KEY2>"]` if `blocks:` given
3. Return the created issue identifier.
