---
name: sentinel-bootstrap-jira
description: One-time bootstrap. Discovers Jira transition IDs from the live workflow and prints a config block ready to paste into ${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml under tasks.jira.transitions. Run once per project, and again whenever the Jira workflow changes. Invocation: /dma:sentinel-bootstrap-jira.
tools: mcp__atlassian__jira_search, mcp__atlassian__jira_get_transitions, Edit
---

# sentinel-bootstrap-jira

Discover Jira transition IDs for the project's workflow and emit a `tasks.jira.transitions:` config block.

This is required because `mcp__atlassian__jira_transition_issue` takes a numeric `transition_id`, and the `mcp__atlassian__jira_get_transitions` response shape does not include a `to_status` field — so the id cannot be derived on the fly inside a skill. Bake the map into config once, then every claim and handoff is a single direct call.

## Usage

`/dma:sentinel-bootstrap-jira`

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`, `tasks.project_key`, `tasks.workflow.statuses` (semantic-key → display-name map). If `tasks.provider != "jira"`: stop and report — this skill is jira-only.

2. Fetch a sample issue from the project: `mcp__atlassian__jira_search(jql="project = <project_key>", limit=1, fields="summary,status")`. If no issues: stop and report — bootstrap needs at least one issue to query transitions against. Ask the user to create any issue first.

3. Call `mcp__atlassian__jira_get_transitions(issue_key=<sample issue key>)`. Returns a list of `{id, name}` entries — the transitions reachable from the sample issue's current status.

4. For each `(semantic_key, display_name)` pair in `tasks.workflow.statuses`:
   - Find the transition whose `name` equals `display_name` (case-sensitive). Jira workflows conventionally name the transition after its destination status; this is the match key.
   - On match: record `<semantic_key>: <id>`.
   - On no match: record `<semantic_key>: ?` and add the pair to the unresolved list.

5. Print results in this exact shape:

   ```
   ## tasks.jira.transitions (paste into ${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml)

   tasks:
     jira:
       transitions:
         to_do: <id or ?>
         in_progress: <id or ?>
         qa: <id or ?>
         code_review: <id or ?>
         on_hold: <id or ?>
         awaiting_merge: <id or ?>
         done: <id or ?>

   Sample issue: <KEY>, current status: <name>.
   Resolved: <N> / <total>.
   Unresolved keys: <list, or "none">.
   ```

6. If any key is unresolved, append a `## Unresolved` section listing every transition the sample issue actually exposed (id + name) and the display names from `workflow.statuses` that didn't match. Then state, in one sentence:
   - Some target statuses may not be reachable from the sample issue's current status. Re-run this skill from an issue in a different status (pass `--from <KEY>` once that flag exists, or move an issue manually and re-run).
   - Or the Jira workflow uses transition names that don't match the canonical display names. In that case, the user must edit the IDs by hand using the listed (id, name) pairs.

7. If every key resolved, ask the user — via `AskUserQuestion` or a direct chat prompt — whether to write the block to `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml`. On an explicit yes in the same turn: merge `tasks.jira.transitions` into the file without clobbering sibling keys, then report the written path. On no, or if any key is unresolved: print the block for the user to paste. Never write without same-turn consent.

## Notes

- A single sample issue may not expose every transition (workflows restrict transitions by source status). If you get unresolved keys, move a different issue into the relevant source status and re-run.
- Re-run whenever the Jira workflow changes: a status added, removed, or a transition id reassigned.
