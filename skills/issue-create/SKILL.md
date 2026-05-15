---
name: issue-create
description: Create a new issue in the issue tracker — type, summary, description, labels, parent/epic link, and dependency links. Reads project_key from .claude/config.yml. Invocation: /issue-create <type> <summary> [parent:<KEY>] [labels:<l1>,<l2>] [blocks:<KEY1>,<KEY2>] [description:<text>].
tools: mcp__atlassian__jira_create_issue, mcp__atlassian__jira_create_issue_link, mcp__atlassian__jira_link_to_epic
---

# issue-create

Create an issue in the issue tracker with all required fields and optional links.

## Usage

`/issue-create <type> <summary> [options]`

| Argument | Required | Description |
|----------|----------|-------------|
| `<type>` | yes | `Task` or `Epic` |
| `<summary>` | yes | Concise issue title |
| `parent:<KEY>` | optional | Parent Epic key — links the new Task to this Epic |
| `labels:<l1>,<l2>` | optional | Comma-separated labels (e.g. `area:api,agent:dev`) |
| `blocks:<KEY1>,<KEY2>` | optional | Comma-separated keys of issues this new issue blocks |
| `description:<text>` | optional | Issue description (Markdown) |

## Steps

1. Read `<project-root>/.claude/config.yml` → `tasks.project_key`.
2. Call `mcp__atlassian__jira_create_issue` with:
   - `project_key`: from config
   - `summary`: from `<summary>` argument
   - `issue_type`: from `<type>` argument (`Task` or `Epic`)
   - `description`: from `description:` argument, if provided
   - `additional_fields`: build the object from optional arguments:
     - `"labels"`: `[<labels>]` if `labels:` provided
     - `"parent"`: `"<parent-KEY>"` if `parent:` provided and type is `Task`
3. Capture the new issue's key from the response (e.g. `PROJ-42`).
4. If `parent:<KEY>` is provided and type is `Task`, additionally call `mcp__atlassian__jira_link_to_epic` with the new issue key and the parent Epic key to ensure the Epic association is registered.
5. If `blocks:<KEY1>,<KEY2>` is provided, for each key in the list call `mcp__atlassian__jira_create_issue_link` with:
   - `link_type`: `"Blocks"`
   - `inward_issue_key`: the new issue key (the blocker)
   - `outward_issue_key`: the blocked issue key
6. Return the created issue key to the caller.
