---
name: handoff
description: Fallback for a non-Jira tracker. On Jira use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> [to-role] [comment]` — this skill is for when that command exits 2 (provider unsupported). Hands a task between roles: swaps the `agent:<role>` label, transitions status, adds a `🤖 <from-role> (<area>):` comment. Invocation: /dma:handoff <ISSUE-KEY> [to-role] [comment].
tools: mcp__linear__get_issue, mcp__linear__save_issue, mcp__linear__save_comment
---

# Handoff

> **Jira projects do not use this skill.** Use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> [to-role] [comment]`; this file is the path for a tracker that command does not support (it exits `2`).

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

1. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider` and `tasks.workflow.statuses` (semantic-key → display-name map). This file covers `linear`; on `jira` use the CLI named above.
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
8. Apply label + status transition + comment (see below).
9. **If target is `done`:** clean up worktrees for this issue — call "## Worktree cleanup" below.
10. Confirm to user: from-role → to-role, old → new status display name, extra label changes.

Step 3: call `mcp__linear__get_issue(id=<KEY>)` to get labels and state.

Step 8 (labels + state in one call, then comment):
1. `mcp__linear__save_issue(id=<KEY>, labels=[<new label list>], state=<status name from step 7>)`. If Linear rejects, stop and report.
2. `mcp__linear__save_comment(issueId=<KEY>, body="🤖 <from-role> (<area>): handoff → <to-role>\n\n<comment body or 'Manual handoff via /dma:handoff.'>")`.

---

## Worktree cleanup (called by step 9 when target is `done`)

A handoff to `done` closes the task, so its work area goes back:

```
${CLAUDE_PLUGIN_ROOT}/bin/dma workspace remove <KEY>
```

It looks in every checkout the project declares — the project root and each area's — because the worktree lives in the repo of whichever area owned the task. A worktree holding uncommitted changes is reported and left alone, never force-removed: the tracker mutations from step 8 have already succeeded, so the handoff is complete and only the disk-side cleanup is pending. Continue to step 10 whatever the outcome.
