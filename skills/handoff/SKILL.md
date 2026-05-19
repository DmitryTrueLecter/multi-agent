---
name: handoff
description: Hand off a task between roles in the multi-agent system — swap the `agent:<role>` label, transition status, and add a `🤖 <from-role> (<area>):` comment in one step. Use whenever an agent finishes its part of a task and is ready to pass it to the next role. Invocation: `/handoff <ISSUE-KEY> [to-role] [comment]`.
---

# Handoff

Hand off a task between roles in one step: swap the `agent:<role>` label, transition the status, and add a comment with the standard `🤖 <from-role> (<area>):` prefix.

Status names in this skill are referenced by semantic key (e.g. `code_review`, `awaiting_merge`). The actual tracker display name comes from `config.yml.tasks.workflow.statuses[<key>]` at call time. Never hardcode a tracker-specific name here.

## Usage

`/handoff <ISSUE-KEY> [to-role] [comment]`

| Form | What it does |
|------|--------------|
| `/handoff <KEY>` | Default forward: `dev → qa`, `qa → reviewer`, `reviewer → awaiting_merge` |
| `/handoff <KEY> <to-role>` | Explicit target: `dev`, `qa`, `reviewer`, `team-lead`, `awaiting_merge`, `done` |
| `/handoff <KEY> <to-role> <comment>` | Same, with a custom comment body |

## Target → status key / label changes

| Target | Status key | Label changes |
|--------|-----------|----------------|
| `qa` | `qa` | remove `agent:<from>`, add `agent:qa` |
| `reviewer` | `code_review` | remove `agent:<from>`, add `agent:reviewer` |
| `dev` | `to_do` | remove `agent:<from>`, add `agent:dev` |
| `team-lead` | `on_hold` | remove `agent:<from>`, add `agent:team-lead` and `needs-decision` |
| `awaiting_merge` | `awaiting_merge` | remove `agent:<from>` |
| `done` | `done` | remove `agent:<from>` |

Why these rules:
- **`area:<area>` is never touched.** It's the permanent area-ownership label, not a queue marker.
- **`done` and `awaiting_merge` drop `agent:<from>` and add no new `agent:` label.** Neither status has an agent owner: `done` is terminal, `awaiting_merge` waits on a human merge. The status column is the routing signal; `/pr-feedback` reconciles `awaiting_merge` into `done` (merged) or `to_do` + `agent:dev` (declined).
- **For `team-lead`, the extra `needs-decision` label is mandatory.** The team-lead's `on_hold` queue filters on it — without it the task gets lost.

## Steps

1. Read `.claude/config.yml` → `tasks.provider` and `tasks.workflow.statuses` (the semantic-key → display-name map).
2. Parse arguments into `<KEY>`, optional `<to-role>`, optional `<comment>`.
3. Read the issue (see provider section below) to get current `agent:<role>` and `area:<area>` labels.
4. If `<to-role>` is omitted, derive the default forward target:
   - `agent:dev` → `qa`
   - `agent:qa` → `reviewer`
   - `agent:reviewer` → `awaiting_merge`
   - any other → stop, ask for explicit target.
5. Validate target is one of `dev`, `qa`, `reviewer`, `team-lead`, `awaiting_merge`, `done`. Otherwise stop.
6. Build new label list: existing labels minus `agent:<from>` (and `needs-decision` if present), plus new `agent:<to>` label (and `needs-decision` if target is `team-lead`). For `done` and `awaiting_merge`, only remove `agent:<from>` — neither target adds an `agent:` label.
7. Resolve the actual status display name: `<status name> = config.yml.tasks.workflow.statuses[<status key from the table above>]`.
8. Apply label + status transition + comment per provider section below.
9. Confirm to user: from-role → to-role, old → new status display name, extra label changes.

---

## jira

Step 8 implementation:
1. `mcp__atlassian__jira_update_issue(issue_key=<KEY>, fields={"labels": [<new label list>]})` — full label list replacement.
2. Resolve the transition id from the target status name:
   - `mcp__atlassian__jira_get_transitions(issue_key=<KEY>)` returns transitions available from the current status, each as `{id, name, to_status}`. `id` is a numeric string (e.g. `"11"`); `to_status` is the name of the destination status; `name` is the transition's own label and is not used here.
   - Match by `to_status == <status name from step 7>` (case-sensitive). Capture `id` → `<transition id>`.
   - If no transition matches: stop and report. The Jira workflow does not expose a transition from the current status to the target — a project-level workflow change is required, the skill cannot proceed.
3. `mcp__atlassian__jira_transition_issue(issue_key=<KEY>, transition_id=<transition id>)` — pass the id as the string returned in step 2. If Jira rejects the transition, stop and report — do not retry.
4. `mcp__atlassian__jira_add_comment(issue_key=<KEY>, body="🤖 <from-role> (<area>): handoff → <to-role>\n\n<comment body or 'Manual handoff via /handoff.'>")`.

---

## linear

Step 3: call `mcp__linear__get_issue(id=<KEY>)` to get labels and state.

Step 8 implementation (labels + state in one call, then comment):
1. `mcp__linear__save_issue(id=<KEY>, labels=[<new label list>], state=<status name from step 7>)`. If Linear rejects, stop and report.
2. `mcp__linear__save_comment(issueId=<KEY>, body="🤖 <from-role> (<area>): handoff → <to-role>\n\n<comment body or 'Manual handoff via /handoff.'>")`.
