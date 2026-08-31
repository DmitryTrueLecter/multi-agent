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

1. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`, `tasks.workflow.statuses` (semantic-key → display-name map; resolve every `statuses.<key>` reference below through this map), and — for the jira provider only — `tasks.jira.transitions` (semantic-key → numeric transition id map).
2. Follow the section for your provider.

---

## jira

Tasks awaiting merge sit in `statuses.awaiting_merge` with no `agent:` label — the status column is the signal.

**Driven from the tracker, not from the pull-request history.** The only tasks whose state can change are the ones in `awaiting_merge`; find those first, then look up the pull request for each. Walking every merged PR instead costs a tracker round-trip per PR ever merged, and re-applies a task's stale `DECLINED` pull request every time that task comes back to `awaiting_merge` on a later attempt.

**Setup:**
- Read `tasks.project_key` and `vcs.branch_prefix` from config.
- Read `workspace.remote` (default `origin`). Derive Bitbucket coordinates from the git remote URL (subshell):
  ```
  ( cd <workspace-path> && git remote get-url <remote> )
  ```
  Strip `.git`, read `<bitbucket-workspace>` and `<repo-slug>`.

**Steps:**

1. Find the tasks that can change:
   `mcp__atlassian__jira_search(jql='project = <project_key> AND status = "<statuses.awaiting_merge>"')`.

2. For each task `<KEY>`, list the pull requests opened from its branch `<branch_prefix><KEY>`, newest first — every state, not just the decided ones:
   `mcp__atlassian__bitbucket_list_pull_requests(workspace=X, repo_slug=Y, q='source.branch.name="<branch_prefix><KEY>"', state=[OPEN, MERGED, DECLINED, SUPERSEDED], sort='-updated_on')`.
   - No pull request → the reviewer has not opened one yet; report and move on.
   - Newest is **not** `MERGED` or `DECLINED` → the user has not decided yet; move on. (Taking any older decided PR here would re-apply a decision the newer PR has already superseded.)

3. `mcp__atlassian__jira_get_issue(issue_key=<KEY>, comment_limit=50)`. If the status is no longer `statuses.awaiting_merge`, skip — the JQL index lags a transition made moments ago.

4. If the newest PR is **DECLINED**:
   - Gather rejection text: the PR description plus `bitbucket_list_pull_request_comments` (inline prefixed `[file:line]`, cap ~3000 chars). If it is empty, report it and leave the task untouched — ask the user rather than bouncing a task back with no reason.
   - `mcp__atlassian__jira_update_issue`: labels → existing plus `agent:dev`.
   - Read `tasks.jira.transitions.to_do` from config. If missing or `0`: log and skip this task — run `/dma:sentinel-bootstrap-jira`; the next pre-flight retries.
   - `mcp__atlassian__jira_transition_issue(issue_key=<KEY>, transition_id=<id>)`. If Jira rejects: log and skip.
   - `mcp__atlassian__jira_add_comment`: `🤖 user (decline) via PR <PR_URL>:\n\n<rejection text>`.

5. If the newest PR is **MERGED**:
   - **Verify the merged tip against the approved tip.**
     - Read `merge_commit.hash` → `<merge_sha>`; `mcp__atlassian__bitbucket_get_commit(commit=<merge_sha>)`; the source-side parent is `parents[1].hash` → `<merged_tip>`. Conventional merge-commit order: `parents[0]` is the destination tip, `parents[1]` is what landed from the source branch.
     - Scan the issue's comments newest-first for the most recent line matching `^Approved tip: ([0-9a-f]{40})$`. Capture group → `<approved_tip>`.
     - No `Approved tip` line (legacy handoff): continue, but append `; no approved-tip recorded on this task` to the merge comment.
     - No merge commit, or fewer than two parents (squash / fast-forward): the merged tip cannot be established — continue, but append `; merged tip could not be determined (no merge commit — squash or fast-forward)`.
     - `<merged_tip> != <approved_tip>` (**stale merge**): do NOT transition to `statuses.done`. Add label `stale-merge` (status stays `awaiting_merge`), comment `🤖 user (merge with stale tip) via PR <PR_URL>: merged <merged_tip>, but approved tip was <approved_tip>. Commits between the two were orphaned and need human review before this task is marked done.`, and skip the rest for this task.
   - Read `tasks.jira.transitions.done`. If missing or `0`: log and skip; the next pre-flight retries.
   - `mcp__atlassian__jira_transition_issue(issue_key=<KEY>, transition_id=<id>)`. If Jira rejects: log and skip.
   - `mcp__atlassian__jira_add_comment`: `🤖 user (merge) via PR <PR_URL>: merged into <destination_branch> at <merged_tip>.`
   - **Group close-out:** if the task has a parent with `type="group"`:
     - `mcp__atlassian__jira_search(jql='parent = <parent.key> AND key != <KEY> AND status != "<statuses.done>"')`. The `key != <KEY>` clause matters: the child was transitioned a moment ago and the index can still report it as open, which would silently skip the close-out — and nothing retries it, because the next pre-flight no longer sees the child in `awaiting_merge`.
     - If empty (all siblings done):
       1. Read `tasks.jira.transitions.code_review`. If missing or `0`: log and skip the close-out.
       2. `mcp__atlassian__jira_update_issue` — add `agent:team-lead` to the parent's labels.
       3. `mcp__atlassian__jira_transition_issue(issue_key=<parent.key>, transition_id=<id>)`. If Jira rejects: log and surface to the user — the parent now carries `agent:team-lead` in its previous status (a partial promote), and nothing auto-retries it.
       4. `mcp__atlassian__jira_add_comment` on the parent.

6. On any single task failure: log it and continue — the task stays in `statuses.awaiting_merge`, the next pre-flight retries.

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
