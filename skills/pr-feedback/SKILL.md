---
name: pr-feedback
description: Fallback for a non-Jira tracker. On Jira the pre-flight is `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` — use this skill only when that command exits 2 (provider unsupported). Reconciles PR merge/decline decisions from the VCS platform into the issue tracker. Invocation: /dma:pr-feedback.
tools: mcp__linear__list_issues, mcp__linear__get_issue, mcp__linear__save_issue, mcp__linear__save_comment
---

# pr-feedback

> **Jira projects do not use this skill.** The pre-flight is `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile`; this file is the path for a tracker that command does not support (it exits `2`).

Sync PR merge/decline decisions from the VCS platform into the issue tracker. Pre-flight step that runs before every agent dispatch.

Status references in this skill are semantic keys (e.g. `awaiting_merge`, `done`, `to_do`). The actual tracker display name comes from `config.yml.tasks.workflow.statuses[<key>]` at call time.

## Usage

`/dma:pr-feedback`

## Steps

Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider` and `tasks.workflow.statuses` (semantic-key → display-name map; resolve every `statuses.<key>` reference below through it). This file covers `linear`; on `jira` use the CLI named above.

Tasks awaiting merge sit in `statuses.awaiting_merge` with no `agent:` label.

**Setup:**
- Read `tasks.team_key`, `tasks.project`, and `vcs.branch_prefix` from config.
- Read `workspace.remote` (default `origin`). Derive GitHub coordinates from the git remote URL (subshell):
  ```
  ( cd <workspace-path> && git remote get-url <remote> )
  ```
  Strip `.git`, parse `<owner>/<repo>`. Required for `gh api repos/<owner>/<repo>/commits/...` in step 4.
- A PR is a managed task PR iff its head branch starts with `<branch_prefix>`.

**Steps:**

1. Find all issues currently in `statuses.awaiting_merge`:
   ```
   mcp__linear__list_issues(team=<team_key>, project=<project>, state=<statuses.awaiting_merge>)
   ```

2. For each issue, derive the expected branch: `<branch_prefix><issue.identifier>`. Check its PR status (subshell) — newest first, and act only on the newest one; an older decided PR has been superseded by it:
   ```
   gh pr list --head <branch> --state all --json state,url,body,comments,mergeCommit,updatedAt --limit 20
   ```
   No PR, or the newest is still `OPEN` → the user has not decided yet; move on.

3. For each issue where PR state is **`CLOSED`** (declined):
   - Gather rejection text from PR body + comments. Ask user if empty.
   - `mcp__linear__get_issue` to get current labels.
   - `mcp__linear__save_issue(id=<KEY>, labels=[...existing + agent:dev], state=<statuses.to_do>)`.
   - `mcp__linear__save_comment(issueId=<KEY>, body="🤖 user (decline) via PR <PR_URL>:\n\n<rejection text>")`.

4. For each issue where PR state is **`MERGED`**:
   - `mcp__linear__get_issue` to get current labels, parent, and comments.
   - **Verify merged tip against approved tip.**
     - From the `gh pr list` JSON payload (step 2), take `mergeCommit.oid` → `<merge_sha>`.
     - `gh api repos/<owner>/<repo>/commits/<merge_sha>` → JSON with `.parents[]`. The source-side parent is `.parents[1].sha` → `<merged_tip>`. Conventional merge-commit order: `parents[0]` is the destination tip, `parents[1]` is what landed from the source branch.
     - Scan the issue's comments newest-first for the most recent line matching the regex `^Approved tip: ([0-9a-f]{40})$`. Capture group → `<approved_tip>`.
     - If no `Approved tip` line is found (legacy handoff predating the check): continue with reconciliation, but append `; no approved-tip recorded on this task` to the merge comment in the next substep.
     - If `<merged_tip> != <approved_tip>` (**stale merge**): do NOT transition to `statuses.done`. Instead:
       - `mcp__linear__save_issue(id=<KEY>, labels=[...existing + stale-merge])`. State stays `statuses.awaiting_merge`.
       - `mcp__linear__save_comment(issueId=<KEY>, body="🤖 user (merge with stale tip) via PR <PR_URL>: merged <merged_tip>, but approved tip was <approved_tip>. Commits between the two were orphaned and need human review before this task is marked done.")`.
       - Skip the remaining substeps for this PR.
   - `mcp__linear__save_issue(id=<KEY>, state=<statuses.done>)`.
   - `mcp__linear__save_comment(issueId=<KEY>, body="🤖 user (merge) via PR <PR_URL>: merged at <merged_tip>.")`.
   - **Group close-out:** if issue has a parent:
     - `mcp__linear__list_issues(parentId=<parent.id>)`. Filter to entries whose state name is not `statuses.done`.
     - If empty (all siblings done): `mcp__linear__save_issue(id=<parent.id>, labels=[...existing + agent:team-lead], state=<statuses.code_review>)`; add comment on parent.

5. On any single issue failure: log it and continue.
