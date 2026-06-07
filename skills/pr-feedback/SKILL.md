---
name: pr-feedback
description: Reconcile PR merge/decline decisions from the VCS platform into the issue tracker. Run as the first step of every /dma:run invocation. Invocation: /dma:pr-feedback.
tools: mcp__atlassian__bitbucket_list_pull_requests, mcp__atlassian__bitbucket_get_pull_request, mcp__atlassian__bitbucket_get_commit, mcp__atlassian__bitbucket_list_pull_request_comments, mcp__atlassian__jira_get_issue, mcp__atlassian__jira_update_issue, mcp__atlassian__jira_transition_issue, mcp__atlassian__jira_add_comment, mcp__atlassian__jira_search, mcp__linear__list_issues, mcp__linear__get_issue, mcp__linear__save_issue, mcp__linear__save_comment
---

# pr-feedback

Sync PR merge/decline decisions from the VCS platform into the issue tracker. Pre-flight step that runs before every agent dispatch.

Status references in this skill are semantic keys (e.g. `awaiting_merge`, `done`, `to_do`). The actual tracker display name comes from `config.yml.tasks.workflow.statuses[<key>]` at call time.

## Usage

`/dma:pr-feedback`

## Steps

1. Read `${CLAUDE_PROJECT_DIR}/.claude/config.yml` → `tasks.provider`, `tasks.workflow.statuses` (semantic-key → display-name map; resolve every `statuses.<key>` reference below through this map), and — for the jira provider only — `tasks.jira.transitions` (semantic-key → numeric transition id map).
2. Follow the section for your provider.

---

## jira

Tasks awaiting merge sit in `statuses.awaiting_merge` with no `agent:` label — the status column is the signal.

**Setup:**
- Read `tasks.project_key` and `vcs.branch_prefix` from config.
- Read `workspace.remote` (default `origin`). Derive Bitbucket coordinates from git remote URL (subshell):
  ```
  ( cd <workspace-path> && git remote get-url <remote> )
  ```
  Strip `.git`, read `<bitbucket-workspace>` and `<repo-slug>`.
- A PR is a managed task PR iff `source.branch.name` starts with `<branch_prefix><project_key>-`.

**Steps:**

1. `mcp__atlassian__bitbucket_list_pull_requests(workspace=X, repo_slug=Y, state=DECLINED)` → declined list.
2. `mcp__atlassian__bitbucket_list_pull_requests(workspace=X, repo_slug=Y, state=MERGED)` → merged list.
3. Filter both to managed task PRs.

4. For each **DECLINED** PR:
   - `<KEY>` = branch name with `<branch_prefix>` stripped.
   - `mcp__atlassian__jira_get_issue(issue_key=<KEY>)`. If the issue's status name is not `statuses.awaiting_merge` → skip (already reconciled).
   - Gather rejection text: `bitbucket_get_pull_request` description + `bitbucket_list_pull_request_comments` (inline prefixed `[file:line]`, cap ~3000 chars). Ask user if empty.
   - `mcp__atlassian__jira_update_issue`: labels → existing plus `agent:dev`.
   - Read `tasks.jira.transitions.to_do` from config. If missing or `0`: log and skip this PR — run `/dma:sentinel-bootstrap-jira` to populate the map; next pre-flight will retry.
   - `mcp__atlassian__jira_transition_issue(issue_key=<KEY>, transition_id=<id>)`. If Jira rejects: log and skip this PR; next pre-flight will retry.
   - `mcp__atlassian__jira_add_comment`: `🤖 user (decline) via PR <PR_URL>:\n\n<rejection text>`.

5. For each **MERGED** PR:
   - `<KEY>` = branch name with `<branch_prefix>` stripped.
   - `mcp__atlassian__jira_get_issue(issue_key=<KEY>, comment_limit=50)`. If the issue's status name is not `statuses.awaiting_merge` → skip.
   - **Verify merged tip against approved tip.**
     - From the PR object (already in hand from step 2, or refetch via `bitbucket_get_pull_request`), read `merge_commit.hash` → `<merge_sha>`.
     - `mcp__atlassian__bitbucket_get_commit(workspace=X, repo_slug=Y, commit=<merge_sha>)`. The source-side parent is `parents[1].hash` → `<merged_tip>`. Conventional merge-commit order: `parents[0]` is the destination tip, `parents[1]` is what landed from the source branch.
     - Scan the issue's comments newest-first for the most recent line matching the regex `^Approved tip: ([0-9a-f]{40})$`. Capture group → `<approved_tip>`.
     - If no `Approved tip` line is found (legacy handoff predating the check): continue with reconciliation, but append `; no approved-tip recorded on this task` to the merge comment in the next substep.
     - If `<merged_tip> != <approved_tip>` (**stale merge**): do NOT transition to `statuses.done`. Instead:
       - `mcp__atlassian__jira_update_issue`: add label `stale-merge`. Status stays `statuses.awaiting_merge`.
       - `mcp__atlassian__jira_add_comment`: `🤖 user (merge with stale tip) via PR <PR_URL>: merged <merged_tip>, but approved tip was <approved_tip>. Commits between the two were orphaned and need human review before this task is marked done.`.
       - Skip the remaining substeps for this PR.
   - Read `tasks.jira.transitions.done` from config. If missing or `0`: log and skip — run `/dma:sentinel-bootstrap-jira` to populate the map; next pre-flight will retry.
   - `mcp__atlassian__jira_transition_issue(issue_key=<KEY>, transition_id=<id>)`. If Jira rejects: log and skip; next pre-flight retries.
   - `mcp__atlassian__jira_add_comment`: `🤖 user (merge) via PR <PR_URL>: merged into <destination_branch> at <merged_tip>.`.
   - **Group close-out:** if the task has a parent with `type="group"`:
     - `mcp__atlassian__jira_search(jql='parent = <parent.key> AND status != "<statuses.done>"')`.
     - If empty (all siblings done):
       1. Read `tasks.jira.transitions.code_review` from config. If missing or `0`: log and skip the close-out — parent label and status are left untouched, run `/dma:sentinel-bootstrap-jira` and the next pre-flight will retry.
       2. `mcp__atlassian__jira_update_issue` — add `agent:team-lead` to the parent's labels.
       3. `mcp__atlassian__jira_transition_issue(issue_key=<parent.key>, transition_id=<id>)`. If Jira rejects: log and surface to the user — the parent is now in its previous status with `agent:team-lead` already attached (a partial-promote state). The next pre-flight will not auto-retry this branch, because the merged-PR loop only visits children in `awaiting_merge` and the current child has already moved to `done`.
       4. `mcp__atlassian__jira_add_comment` on the parent.

6. On any single PR failure: log it and continue — the task stays in `statuses.awaiting_merge`, next pre-flight will retry.

---

## linear

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

2. For each issue, derive the expected branch: `<branch_prefix><issue.identifier>`. Check its PR status (subshell):
   ```
   gh pr list --head <branch> --state all --json state,url,body,comments,mergeCommit --limit 1
   ```

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
