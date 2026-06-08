---
name: handoff
description: Hand off a task between roles in the multi-agent system — swap the `agent:<role>` label, transition status, and add a `🤖 <from-role> (<area>):` comment in one step. Use whenever an agent finishes its part of a task and is ready to pass it to the next role. Invocation: `/dma:handoff <ISSUE-KEY> [to-role] [comment]`.
tools: mcp__atlassian__jira_get_issue, mcp__atlassian__jira_update_issue, mcp__atlassian__jira_transition_issue, mcp__atlassian__jira_add_comment, mcp__linear__get_issue, mcp__linear__save_issue, mcp__linear__save_comment
---

# Handoff

Hand off a task between roles in one step: swap the `agent:<role>` label, transition the status, and add a comment with the standard `🤖 <from-role> (<area>):` prefix.

Status names in this skill are referenced by semantic key (e.g. `code_review`, `awaiting_merge`). The actual tracker display name comes from `config.yml.tasks.workflow.statuses[<key>]` at call time. Never hardcode a tracker-specific name here.

## Usage

`/dma:handoff <ISSUE-KEY> [to-role] [comment]`

| Form | What it does |
|------|--------------|
| `/dma:handoff <KEY>` | Default forward: `dev → qa`, `qa → reviewer`, `reviewer → awaiting_merge`, `devops → awaiting_ops` |
| `/dma:handoff <KEY> <to-role>` | Explicit target: `dev`, `qa`, `reviewer`, `devops`, `team-lead`, `awaiting_merge`, `awaiting_ops`, `done` |
| `/dma:handoff <KEY> <to-role> <comment>` | Same, with a custom comment body |

## Target → status key / label changes

| Target | Status key | Label changes |
|--------|-----------|----------------|
| `qa` | `qa` | remove `agent:<from>`, add `agent:qa` |
| `reviewer` | `code_review` | remove `agent:<from>`, add `agent:reviewer` |
| `dev` | `to_do` | remove `agent:<from>`, add `agent:dev` |
| `devops` | `to_do` | remove `agent:<from>`, add `agent:devops` |
| `team-lead` | `on_hold` | remove `agent:<from>`, add `agent:team-lead` and `needs-decision` |
| `awaiting_merge` | `awaiting_merge` | remove `agent:<from>` |
| `awaiting_ops` | `awaiting_ops` | remove `agent:<from>` |
| `done` | `done` | remove `agent:<from>` |

Why these rules:
- **`area:<area>` is never touched.** It's the permanent area-ownership label, not a queue marker.
- **`done`, `awaiting_merge`, and `awaiting_ops` drop `agent:<from>` and add no new `agent:` label.** None of those statuses has an agent owner: `done` is terminal, `awaiting_merge` waits on a human merge, `awaiting_ops` waits on the human executing a devops runbook. The status column is the routing signal; `/dma:pr-feedback` reconciles `awaiting_merge` into `done` (merged) or `to_do` + `agent:dev` (declined); `awaiting_ops` is closed by the user manually via `/dma:handoff <KEY> done`.
- **For `team-lead`, the extra `needs-decision` label is mandatory.** The team-lead's `on_hold` queue filters on it — without it the task gets lost.

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/config.yml` → `tasks.provider`, `tasks.workflow.statuses` (semantic-key → display-name map), and `tasks.jira.transitions` (semantic-key → numeric transition id map; jira provider only).
2. Parse arguments into `<KEY>`, optional `<to-role>`, optional `<comment>`.
3. Read the issue (see provider section below) to get current `agent:<role>` and `area:<area>` labels.
4. If `<to-role>` is omitted, derive the default forward target:
   - `agent:dev` → `qa`
   - `agent:qa` → `reviewer`
   - `agent:reviewer` → `awaiting_merge`
   - `agent:devops` → `awaiting_ops`
   - any other → stop, ask for explicit target.
5. Validate target is one of `dev`, `qa`, `reviewer`, `devops`, `team-lead`, `awaiting_merge`, `awaiting_ops`, `done`. Otherwise stop.
6. Build new label list: existing labels minus `agent:<from>` (and `needs-decision` if present), plus new `agent:<to>` label (and `needs-decision` if target is `team-lead`). For `done` and `awaiting_merge`, only remove `agent:<from>` — neither target adds an `agent:` label.
7. Resolve the actual status display name: `<status name> = config.yml.tasks.workflow.statuses[<status key from the table above>]`.
8. Apply label + status transition + comment per provider section below.
9. **If target is `done`:** clean up worktrees for this issue — call "## Worktree cleanup" below.
10. Confirm to user: from-role → to-role, old → new status display name, extra label changes.

---

## jira

Step 8 implementation:
1. `mcp__atlassian__jira_update_issue(issue_key=<KEY>, fields={"labels": [<new label list>]})` — full label list replacement.
2. Read `tasks.jira.transitions.<status key from step 7's source table>` from config — the numeric transition id for the target status. If missing or `0`: stop and report — run `/dma:sentinel-bootstrap-jira` to populate the map.
3. `mcp__atlassian__jira_transition_issue(issue_key=<KEY>, transition_id=<id>)`. If Jira rejects the transition, stop and report — do not retry. The most common cause is that the Jira workflow does not expose a transition from the current status to the target; that requires a Jira workflow change, not a skill change.
4. `mcp__atlassian__jira_add_comment(issue_key=<KEY>, body="🤖 <from-role> (<area>): handoff → <to-role>\n\n<comment body or 'Manual handoff via /dma:handoff.'>")`.

---

## linear

Step 3: call `mcp__linear__get_issue(id=<KEY>)` to get labels and state.

Step 8 implementation (labels + state in one call, then comment):
1. `mcp__linear__save_issue(id=<KEY>, labels=[<new label list>], state=<status name from step 7>)`. If Linear rejects, stop and report.
2. `mcp__linear__save_comment(issueId=<KEY>, body="🤖 <from-role> (<area>): handoff → <to-role>\n\n<comment body or 'Manual handoff via /dma:handoff.'>")`.

---

## Worktree cleanup (called by step 9 when target is `done`)

A handoff to `done` is the canonical signal that the task / epic is closed. Persistent worktrees created by `/dma:run` (see `commands/run.md → ## Worktree bootstrap`) are removed here. This is the only automated cleanup path; orphaned worktrees from other close-out routes surface in `/dma:sentinel healthcheck` (HC-WT-001).

### Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/config.yml` and `${CLAUDE_PROJECT_DIR}/.claude/areas/*/area.yml` to enumerate candidate repos whose `.worktrees/<KEY>/` might exist:
   - Project root (always): `${CLAUDE_PROJECT_DIR}`.
   - Per area: `<abs-area-repo>` = `(cd <area.yml.workspace.path> && git rev-parse --show-toplevel)`. Collect distinct values; in a monorepo all areas resolve to project root and the set collapses to `{${CLAUDE_PROJECT_DIR}}`.
2. For each candidate repo, build `<repo>/.worktrees/<KEY>`. If `test -d` succeeds, attempt removal:
   ```
   git -C <repo> worktree remove <repo>/.worktrees/<KEY>
   ```
3. **On failure** (typical cause: uncommitted changes in the worktree): report a warning per failing path but do NOT force-remove. The user investigates manually. The tracker mutations from step 8 already succeeded — the handoff is complete; only the disk-side cleanup is pending.
4. Continue to step 10 regardless of cleanup outcome. Cleanup failure never rolls back the tracker transition.
