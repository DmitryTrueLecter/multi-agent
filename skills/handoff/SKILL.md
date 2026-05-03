---
name: handoff
description: Hand off a Jira task between roles in the multi-agent system — swap the `agent:<role>` label, transition status, and add a `🤖 <from-role> (<area>):` comment in one step. Use whenever a dev/qa/reviewer/team-lead agent finishes its part of a task and is ready to pass it to the next role, or when manually re-routing a task between queues. Invocation: `/handoff <ISSUE-KEY> [to-role] [comment]`.
---

# Handoff

Hand off a Jira task between roles in one step: swap the `agent:<role>` label, transition the status, and add a comment with the standard `🤖 <from-role> (<area>):` prefix.

The status names below match `.claude/config.yml` → `tasks.workflow.statuses` for project AITSAI. If that workflow changes, update the table in this skill — the names are referenced literally by `mcp__atlassian__jira_transition_issue`.

## Usage

`/handoff <ISSUE-KEY> [to-role] [comment]`

| Form | What it does |
|------|--------------|
| `/handoff <KEY>` | Default forward: `dev → qa`, `qa → reviewer`, `reviewer → done` |
| `/handoff <KEY> <to-role>` | Explicit target: `dev`, `qa`, `reviewer`, `team-lead`, `done` |
| `/handoff <KEY> <to-role> <comment>` | Same, with a custom comment body |

## Target role → status / label changes

| Target | New status | Label changes |
|--------|------------|----------------|
| `qa` | `QA` | remove `agent:<from>`, add `agent:qa` |
| `reviewer` | `Code Review` | remove `agent:<from>`, add `agent:reviewer` |
| `dev` | `To Do` | remove `agent:<from>`, add `agent:dev` (rejection / re-queue) |
| `team-lead` | `On Hold` | remove `agent:<from>`, add `agent:team-lead` and `needs-decision` |
| `done` | `Done` | remove `agent:<from>` (no `agent:` label on Done — task is out of all queues) |

Why these rules:

- **`area:<area>` is never touched.** It's the permanent area-ownership label, not a queue marker. It outlives every handoff and is what scopes JQL queries per area.
- **For `done`, drop `agent:<from>`.** `agent:<role>` is a queue marker, not an audit marker — a Done task is out of every queue. Keeping `agent:reviewer` on Done would pollute JQL like `agent:reviewer AND status != Done` (open reviewer queue). The audit trail is preserved by the handoff comment (`🤖 <from> (<area>): handoff → done`) and the Jira changelog, both of which record who delivered the final approval.
- **For `team-lead`, the extra `needs-decision` label is mandatory.** The team-lead's "On Hold queue" JQL filters on it — without that label the task lands in On Hold with no routing hint and gets lost.
- **Default `reviewer → done` is intentional.** Review approval is the terminal Jira state in this workflow; merging the branch happens out-of-band (CI / manual git push), not as another transition.

## Steps

1. Parse arguments into `<KEY>`, optional `<to-role>`, optional `<comment>`.
2. Read the issue with `mcp__atlassian__jira_get_issue`. Extract:
   - **From role** — current `agent:<role>` label. If missing, stop and ask the user to specify it.
   - **Area** — current `area:<area>` label. If missing, stop and report.
3. If `<to-role>` is omitted, derive the default forward target:
   - `agent:dev` → `qa`
   - `agent:qa` → `reviewer`
   - `agent:reviewer` → `done`
   - any other from-role → stop, ask for an explicit target.
4. Validate the target is one of `dev`, `qa`, `reviewer`, `team-lead`, `done`. Otherwise stop.
5. Update labels via `mcp__atlassian__jira_update_issue`. Pass the **full** label list (existing labels minus `agent:<from>`, plus the new label(s)) — the mcp-atlassian update replaces the field as a whole.
6. Transition status via `mcp__atlassian__jira_transition_issue` to the target status from the table above. If Jira rejects the transition (workflow doesn't allow it from the current status), stop and report — do not retry with another path.
7. Add a comment via `mcp__atlassian__jira_add_comment`:

   ```
   🤖 <from-role> (<area>): handoff → <to-role>

   <comment body, or "Manual handoff via /handoff." if none was supplied>
   ```

8. Confirm to the user: from-role → to-role, old → new status, and any extra label changes (e.g. `needs-decision`).

## Examples

**Default forward (dev finished, hand to QA):**

```
/handoff AITSAI-123
```

- Current labels: `agent:dev`, `area:api`, `bug`
- New labels: `area:api`, `bug`, `agent:qa`
- Status: `In Progress` → `QA`
- Comment:

  ```
  🤖 dev (api): handoff → qa

  Manual handoff via /handoff.
  ```

**QA rejects with a note (back to dev):**

```
/handoff AITSAI-456 dev fixture missing the keys field — coverage gap
```

- Current labels: `agent:qa`, `area:api`
- New labels: `area:api`, `agent:dev`
- Status: `In Progress` → `To Do`
- Comment:

  ```
  🤖 qa (api): handoff → dev

  fixture missing the keys field — coverage gap
  ```

**Dev blocked, escalate to team-lead:**

```
/handoff AITSAI-789 team-lead need decision on whether embeddings live in libs.core or apps.ai_worker
```

- Current labels: `agent:dev`, `area:ai`
- New labels: `area:ai`, `agent:team-lead`, `needs-decision`
- Status: `In Progress` → `On Hold`
- Comment:

  ```
  🤖 dev (ai): handoff → team-lead

  need decision on whether embeddings live in libs.core or apps.ai_worker
  ```

## Notes

- This skill does **not** revert files. For a reviewer→dev rejection that should also revert the diff, use `/reject` instead — see `.claude/commands/reject.md` (slash command in the multi-agent submodule) to confirm scope before deciding which one to invoke.
- Use this only on tasks that are out of their queue (e.g. `In Progress` after an agent finished, or another queue status if you're manually re-routing). It does not claim a task — `/run` does that.
