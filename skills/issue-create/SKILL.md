---
name: issue-create
description: Create a new issue in the issue tracker — type, summary, description, labels, parent/epic link, and dependency links. Reads project/team key from .claude/config.yml. Invocation: /issue-create <type> <summary> [parent:<KEY>] [labels:<l1>,<l2>] [blocks:<KEY1>,<KEY2>] [description:<text>].
tools: mcp__atlassian__jira_create_issue, mcp__atlassian__jira_create_issue_link, mcp__atlassian__jira_link_to_epic, mcp__atlassian__jira_transition_issue, mcp__linear__save_issue
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
| `state:<key>` | optional | Semantic status key from `tasks.workflow.statuses`. Overrides the default, which is derived from any `agent:<role>` label (e.g. `agent:qa` → `qa`) or `to_do` otherwise. |

## Steps

1. Read `.claude/config.yml` → `tasks.provider` and `tasks.workflow.statuses`.
2. Resolve the initial state semantic key (precedence: explicit override → role-derived default → workflow default):
   - If the caller passed `state:<key>`, use `<key>`.
   - Else if labels contain an `agent:<role>` label, use that role's create-time queue status from `run.md`'s Role → queue mapping table: `agent:qa` → `qa`, `agent:reviewer` → `code_review`, `agent:team-lead` → `to_do` (coordination — new bucket from `run.md` auto-mode #2; the other two team-lead queues `on_hold` and `code_review` are transition targets, not create targets — request via explicit `state:`), `agent:dev` / `agent:devops` → `to_do`.
   - Else use `to_do`.
   - If the resolved key is missing from `tasks.workflow.statuses`, fail with `state key '<key>' not in tasks.workflow.statuses`. The corresponding display name is `tasks.workflow.statuses.<resolved-key>`.
3. Follow the section for your provider.

---

## jira

1. Read `tasks.project_key` from config. If the resolved state key from `## Steps` is not `to_do`, also read `tasks.jira.transitions`.
2. Map `type`: `group` → `issue_type="Epic"`, `task` → `issue_type="Task"`.
3. Call `mcp__atlassian__jira_create_issue`:
   - `project_key`: from config
   - `summary`: from `<summary>`
   - `issue_type`: mapped above
   - `description`: from `description:` if provided
   - `additional_fields`: `{"labels": [<labels>]}` if labels given; also `{"parent": "<parent-KEY>"}` if `parent:` given and type is `task`
4. Capture the new issue key.
5. If the resolved state key is not `to_do`, transition the new issue into it: read `tasks.jira.transitions.<resolved-key>` — the numeric transition id. If missing or `0`, fail with `jira transition id for '<resolved-key>' not configured; run /sentinel-bootstrap-jira` and return the new key for caller cleanup. Otherwise call `mcp__atlassian__jira_transition_issue(issue_key=<new-key>, transition_id=<id>)`. If Jira rejects the transition, fail with `jira refused transition '<resolved-key>' on <new-key>` and return the new key.
6. If `parent:<KEY>` given and type is `task`, also call `mcp__atlassian__jira_link_to_epic(issue_key=<new-key>, epic_key=<parent-KEY>)`.
7. If `blocks:<KEY1>,<KEY2>` given, for each key call `mcp__atlassian__jira_create_issue_link(link_type="Blocks", inward_issue_key=<new-key>, outward_issue_key=<blocked-key>)`.
8. Return the created issue key.

---

## linear

1. Read `tasks.team_key` from config.
2. Call `mcp__linear__save_issue` (omit `id` to create):
   - `team`: `<team_key>`
   - `title`: from `<summary>`
   - `description`: from `description:` if provided
   - `labels`: `[<labels>]` if given
   - `state`: the resolved state display name from `## Steps` — pass for both `task` and `group`
   - `parentId`: `"<parent-KEY>"` if `parent:` given and type is `task`
   - `blockedBy`: `["<KEY1>","<KEY2>"]` if `blocks:` given
3. Read the returned issue's status. If it does not match the resolved state display name, Linear silently fell back to the team's default workflow state — call `mcp__linear__save_issue(id=<new-key>, state=<resolved-state-name>)` once to correct it. If the status still does not match, fail with `linear refused state '<resolved>'; issue created in '<actual>'` and return the new key so the caller can clean up.
4. Return the created issue identifier.
