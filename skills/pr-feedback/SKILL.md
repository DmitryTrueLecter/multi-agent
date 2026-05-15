---
name: pr-feedback
description: Reconcile PR merge/decline decisions from the VCS platform into the issue tracker. Run as the first step of every /run invocation — processes any pending user merge/decline decisions before picking up new work. Invocation: /pr-feedback [workspace-path:<path>].
tools: mcp__atlassian__bitbucket_list_pull_requests, mcp__atlassian__bitbucket_get_pull_request, mcp__atlassian__bitbucket_list_pull_request_comments, mcp__atlassian__jira_get_issue, mcp__atlassian__jira_update_issue, mcp__atlassian__jira_transition_issue, mcp__atlassian__jira_add_comment, mcp__atlassian__jira_search
---

# pr-feedback

Sync PR merge/decline decisions from the VCS platform into the issue tracker. This is the pre-flight step that runs before every agent dispatch — it closes the loop on tasks the user reviewed in the PR UI.

## Usage

`/pr-feedback [workspace-path:<path>]`

## State model

Jira is the source of truth — no local state file. A task is "unprocessed" iff its labels still include `awaiting-merge`. Reconciliation's effect is to remove that label (plus `agent:user`) — so the next pre-flight that sees the same DECLINED/MERGED PR will skip it because the corresponding Jira task no longer has `awaiting-merge`. This is idempotent.

## Interactivity rule

VCS platform review text is the primary guidance — read it and use it verbatim in the Jira comment. Ask the user only when the text is empty or genuinely ambiguous (cannot determine what to fix). One `AskUserQuestion` per PR with options `Provide reason` / `Skip`; `Skip` leaves `awaiting-merge` for the next pre-flight.

## Setup

1. Read `.claude/config.yml` for `vcs.branch_prefix` (default `ai/`) and `tasks.project_key` (e.g. `AITSAI`).
2. Determine the workspace path (from `workspace-path:` argument or cwd) and the remote name from `config.yml` → `workspace.remote` (default `origin`).
3. Derive the VCS platform repo coordinates from the git remote URL once (subshell — cwd does not leak):
   ```
   ( cd <workspace-path> && git remote get-url <remote> )
   # → git@bitbucket.org:<bitbucket-workspace>/<repo>.git
   #   or https://bitbucket.org/<bitbucket-workspace>/<repo>.git
   ```
   Strip `.git`, read the two trailing segments: `<bitbucket-workspace>` and `<repo-slug>`.
4. A PR is a "managed task PR" iff its `source.branch.name` starts with `<branch_prefix><project_key>-`.

## Steps

1. List PRs (two MCP calls):
   - `mcp__atlassian__bitbucket_list_pull_requests` with `workspace=<bitbucket-workspace>`, `repo_slug=<repo-slug>`, `state=DECLINED` → declined list.
   - `mcp__atlassian__bitbucket_list_pull_requests` with `workspace=<bitbucket-workspace>`, `repo_slug=<repo-slug>`, `state=MERGED` → merged list.

2. Filter each list to managed task PRs (branch-prefix match from Setup step 4).

3. For each remaining **DECLINED** PR:
   1. `<KEY>` = `source.branch.name` with the `<branch_prefix>` stripped.
   2. Read the Jira issue via `mcp__atlassian__jira_get_issue`. Capture current labels.
   3. **Skip filter:** if labels do **not** contain `awaiting-merge`, this PR has already been reconciled — skip. Do not touch Jira.
   4. Gather rejection text from the platform. Combine:
      - `mcp__atlassian__bitbucket_get_pull_request` → `description` and any reason field.
      - `mcp__atlassian__bitbucket_list_pull_request_comments` → every comment (top-level + inline + replies). Prefix inline comments with `[<file>:<line>]`. Chronological, cap ~3000 chars.

      Use as rejection text per the Interactivity rule above.
   5. `mcp__atlassian__jira_update_issue` to set the labels list to: existing labels minus `agent:user` and `awaiting-merge`, plus `agent:dev`. Preserve every other label (especially `area:<area>`).
   6. `mcp__atlassian__jira_transition_issue` → `To Do`.
   7. `mcp__atlassian__jira_add_comment`:
      ```
      🤖 user (decline) via PR <PR_URL>:

      <rejection text>
      ```

4. For each remaining **MERGED** PR:
   1. `<KEY>` = `source.branch.name` with the `<branch_prefix>` stripped.
   2. Read the Jira issue via `mcp__atlassian__jira_get_issue`. Capture current labels and the `parent` field.
   3. **Skip filter:** if labels do **not** contain `awaiting-merge`, skip — already reconciled.
   4. `mcp__atlassian__jira_update_issue` to set labels: existing minus `agent:user` and `awaiting-merge`. Preserve everything else.
   5. `mcp__atlassian__jira_transition_issue` → `Done`.
   6. `mcp__atlassian__jira_add_comment`:
      ```
      🤖 user (merge) via PR <PR_URL>: merged into <destination_branch>.
      ```
   7. **Epic close-out.** If the task has a `parent` and `parent.fields.issuetype.name == "Epic"`:
      - JQL search via `mcp__atlassian__jira_search`: `parent = <parent.key> AND status != Done`.
      - If the result is empty (zero non-Done siblings) — promote the Epic for team-lead sign-off:
        - `mcp__atlassian__jira_get_issue` the Epic. `mcp__atlassian__jira_update_issue` to add `agent:team-lead` to its labels (preserve existing).
        - `mcp__atlassian__jira_transition_issue` on the Epic → `Code Review`.
        - `mcp__atlassian__jira_add_comment` on the Epic: `🤖 user (epic-close) via PR: all child tasks are Done — Epic ready for team-lead final review and closure.`
      - If any sibling is still open, do nothing with the Epic.

5. After processing all DECLINED and MERGED PRs, return to the caller (which continues with its active mode).

## Error handling

If any single PR fails reconciliation (Jira rejects a transition, MCP error, etc.), log the failure with the PR id and ISSUE-KEY and continue with the next PR — the task still has `awaiting-merge`, so the next pre-flight will retry. Do not abort the whole pre-flight; one stuck PR must not stop the rest.
