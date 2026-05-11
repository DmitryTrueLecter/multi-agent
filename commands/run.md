---
description: "Run agent: /run | /run <ISSUE-KEY> | /run pipeline | /run all | /run dev | /run <area/role>"
---

Launch a subagent to work on a Jira task.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key` and known areas (scan `.claude/areas/` subdirectory names).

**Usage patterns:**

| Command | What it does |
|---------|-------------|
| `/run` | Auto-find highest priority task, run one step |
| `/run <ISSUE-KEY>` | Run the responsible agent for this issue (role from label) |
| `/run pipeline` | Find highest priority task, run full cycle (dev → qa → reviewer → done) |
| `/run pipeline <ISSUE-KEY>` | Run full cycle for a specific task |
| `/run all` | Run tasks until the board is clear (each task = full pipeline) |
| `/run dev` | First available To Do task for **any** area's dev |
| `/run qa` | First available QA task for **any** area's qa |
| `/run reviewer` | First available Code Review task for **any** area's reviewer |
| `/run <area>/dev` | First available To Do task for that area's dev |
| `/run <area>/<role> <ISSUE-KEY>` | Run a specific role on a specific issue (override role) |
| `/run <KEY-1> <KEY-2>` | Two separate parallel agents (roles from labels) |

**Role → queue mapping** (each role picks from one queue and claims by transitioning to `In Progress`):

| Role | Picks from status | Issue type |
|------|------------------|------------|
| `team-lead` | `On Hold` | Task (decision needed) |
| `team-lead` | `Code Review` | Epic (final epic close-out) |
| `reviewer` | `Code Review` | Task |
| `qa` | `QA` | Task |
| `dev` | `To Do` | Task |

The `agent:` label disambiguates `Code Review`: `agent:reviewer` → reviewer (Task), `agent:team-lead` → team-lead (Epic close-out).

**Claim model.** Pickup = `mcp__atlassian__jira_transition_issue` → `In Progress`. This is the atomic claim — Jira rejects the second runner because the workflow disallows transition from `In Progress` to `In Progress`. Every queue JQL filters by pre-claim status (`To Do` / `QA` / `Code Review` / `On Hold`), so a claimed task disappears from every queue automatically.

## PR feedback reconciliation (pre-flight, runs first in every mode)

Reviewer-approved tasks sit in `On Hold` + `agent:user` + `awaiting-merge` until the user merges or declines the Bitbucket PR in the UI. Before searching for the next task to run, this pre-flight syncs those user decisions into Jira.

**When to run.** As the very first step of every `/run` invocation — auto-mode, pipeline mode, all mode, single-issue mode, role-only shortcut. Cheap if nothing changed (two Bitbucket list calls). On `/run all`, re-runs before each iteration's task pickup.

**State model — Jira is the source of truth, no local state file.** A task is "unprocessed" iff its Jira labels still include `awaiting-merge`. Reconciliation's effect on every task is to remove that label (plus `agent:user`) — so the next pre-flight tick that sees the same DECLINED/MERGED PR will skip it because the corresponding Jira task no longer has `awaiting-merge`. This is idempotent by construction, needs no `processed-prs.json` (PR ids aren't unique across repos anyway), and works whether you run one repo or ten.

**Setup.**
- Bitbucket coordinates: derive from `git remote get-url <workspace.remote>` (default `origin`) once per session — strip the trailing `.git`, take the last two path segments as `<bitbucket-workspace>` / `<bitbucket-repo>` (`repo_slug`).
- Read `.claude/config.yml` for `vcs.branch_prefix` (default `ai/`) and `tasks.project_key` (e.g. `AITSAI`). Treat any PR whose `source.branch.name` starts with `<branch_prefix><project_key>-` as a managed task PR.

**Steps.**

1. List PRs (two MCP calls):
   - `mcp__atlassian__bitbucket_list_pull_requests` with `state=DECLINED` → declined list.
   - `mcp__atlassian__bitbucket_list_pull_requests` with `state=MERGED` → merged list.

2. Filter each list to managed task PRs (branch-prefix match).

3. For each remaining **DECLINED** PR:
   1. `<KEY>` = `source.branch.name` with the `<branch_prefix>` stripped.
   2. Read the Jira issue via `mcp__atlassian__jira_get_issue`. Capture current labels.
   3. **Skip filter:** if labels do **not** contain `awaiting-merge`, this PR has already been reconciled (or the task was in a different state when declined) — skip it. Do not touch Jira.
   4. Otherwise, read PR top-level comments via `mcp__atlassian__bitbucket_list_pull_request_comments`. Build a rejection text by concatenating comment bodies in chronological order (cap at ~2000 chars). If the user left no comments, use the literal string `(no decline reason provided in Bitbucket)`.
   5. `mcp__atlassian__jira_update_issue` to set the labels list to: existing labels minus `agent:user` and `awaiting-merge`, plus `agent:dev`. Preserve every other label (especially `area:<area>`).
   6. `mcp__atlassian__jira_transition_issue` → `To Do`.
   7. `mcp__atlassian__jira_add_comment`:
      ```
      🤖 user (decline) via Bitbucket PR <PR_URL>:

      <rejection text>
      ```

4. For each remaining **MERGED** PR:
   1. `<KEY>` = `source.branch.name` with the `<branch_prefix>` stripped.
   2. Read the Jira issue. Capture current labels and the `parent` field.
   3. **Skip filter:** if labels do **not** contain `awaiting-merge`, skip — already reconciled (or never went through the new flow).
   4. `mcp__atlassian__jira_update_issue` to set labels: existing minus `agent:user` and `awaiting-merge`. Preserve everything else.
   5. `mcp__atlassian__jira_transition_issue` → `Done`.
   6. `mcp__atlassian__jira_add_comment`:
      ```
      🤖 user (merge) via Bitbucket PR <PR_URL>: merged into <destination_branch>.
      ```
   7. **Epic close-out.** If the task has a `parent` and `parent.fields.issuetype.name == "Epic"`:
      - JQL search via `mcp__atlassian__jira_search`: `parent = <parent.key> AND status != Done`.
      - If the result is empty (zero non-Done siblings) — promote the Epic for team-lead sign-off:
        - Read the Epic. `mcp__atlassian__jira_update_issue` to add `agent:team-lead` to its labels (preserve existing).
        - `mcp__atlassian__jira_transition_issue` on the Epic → `Code Review`.
        - `mcp__atlassian__jira_add_comment` on the Epic: `🤖 user (epic-close) via Bitbucket: all child tasks are Done — Epic ready for team-lead final review and closure.`
      - If any sibling is still open, do nothing with the Epic.

5. After processing all DECLINED and MERGED PRs, continue with the active mode.

If any single PR fails reconciliation (Jira rejects a transition, MCP error, etc.), log the failure with the PR id and ISSUE-KEY and continue with the next PR — the task still has `awaiting-merge`, so the next pre-flight will retry. Do not abort the whole pre-flight; one stuck PR must not stop the rest.

## Auto-mode (`/run` without arguments)

Search for the first available issue in priority order. Stop at the first match:

0. **Run PR feedback reconciliation** (see above) — process any user merge/decline decisions in Bitbucket before scanning queues.
1. **On Hold** — Tasks with `agent:team-lead` label. Launch `team-lead` agent. (Tasks with `agent:user` + `awaiting-merge` are intentionally skipped — they are handled by reconciliation, not by an agent run.)
2. **Code Review (Epic)** — Epics with `agent:team-lead` label. Launch `team-lead` agent for epic close-out.
3. **Code Review (Task)** — Tasks with `agent:reviewer` label. Launch `reviewer` agent.
4. **QA** — Tasks with `agent:qa` label. Launch `qa` agent.
5. **To Do** — Tasks with `agent:dev` label (whose blockers are all Done). Launch `dev` agent.

If nothing found at any level, report that the board is clear.

## Pipeline mode (`/run pipeline [ISSUE-KEY]`)

Run a single task through the **full lifecycle** until Done (or until it gets stuck on On Hold).

0. **Run PR feedback reconciliation** (see above) before the first stage.

1. **Find the task:**
   - If `ISSUE-KEY` given: use it.
   - If no key: use auto-mode priority to find one task.

2. **Execute stages sequentially:**
   - If task is in `To Do`: run `dev` → then `qa` → then `reviewer`.
   - If task is in `QA`: run `qa` → then `reviewer`.
   - If task is in `Code Review`: run `reviewer`.
   - If task is in `On Hold`: run `team-lead`, then restart from whatever status it lands in.

3. **Between stages**, re-read the issue to check its current status:
   - If the task was sent back (e.g. qa → dev), **re-run** from the new status.
   - If the task moved to `On Hold`, report to user and stop.
   - If the task reached `Done`, report success.

4. **Guard against infinite loops**: track how many times the task has bounced back. After **3 bounces** (e.g. qa rejects → dev fixes → qa rejects again → ...), stop and report to user.

## All mode (`/run all`)

Run tasks until the board is clear.

1. **Run PR feedback reconciliation** (see above) — sync user merge/decline decisions from Bitbucket into Jira before picking up work.
2. Use auto-mode priority to find a task.
3. Run it through the **full pipeline** (same as pipeline mode).
4. After the task reaches Done (or On Hold), go back to step 1 (reconciliation runs again before the next iteration).
5. Stop when no tasks are found at any priority level.
6. Report a summary of what was completed.

**Guard**: after **3 consecutive On Hold** results, stop and report — the board likely needs human attention.

## Stop semantics

Subagents launched by `/run` always run in **background mode** (see step 8 in "Steps"), so this main session is responsive to user messages while a subagent works. The user can interrupt the loop at any time.

**Stop intent.** A user message containing `stop`, `остановись`, `abort`, `cancel`, `отмена`, or equivalent phrasing means "kill the current subagent and exit the loop". Be conservative: a permission approval (`yes`, `ok`), a follow-up question, or any other message is **not** stop intent — only act on explicit signals.

**On stop:**

1. Call `TaskStop` with `task_id` set to the `agentId` you captured when spawning the current background subagent.
2. Do **not** spawn the next subagent. Exit pipeline / all-mode cleanly.
3. Report to the user: `Stopped <ISSUE-KEY> mid-flight. Completed in this run: <list of issues that reached Done or terminal state>.`

**Fallback** if `TaskStop` fails or returns an error: do not spawn the next agent, let the current one finish on its own, then exit the loop. Tell the user explicitly: "TaskStop failed — waiting for current subagent to complete, then will exit. New subagents will not be started."

**Kill latency.** `TaskStop` interrupts the subagent at its next decision point — between tool calls, not in the middle of one. If the subagent is currently inside a long-running Bash command (e.g. a slow test suite), it finishes that command first and exits afterwards. In typical multi-agent flows (many short Jira / git / file operations) the kill takes seconds.

## Steps (for single-step modes)

0. **Run PR feedback reconciliation** (see above) before parsing arguments — applies even when the user invokes `/run <ISSUE-KEY>` directly, so a queued user-decline is processed before this manual run picks anything up.

1. Parse `$ARGUMENTS`:
   - If empty: auto-mode (see above).
   - If `pipeline` [+ optional key]: pipeline mode.
   - If `all`: all mode.
   - If argument matches an issue key pattern (e.g. `<ISSUE-KEY>`): issue-key mode — resolve role from `agent:` label, area from `area:` label.
   - If `dev`, `qa`, or `reviewer`: role-only shortcut.
   - Multiple issue keys: launch parallel agents.

2. Find target task(s):
   - If issue keys given: read each issue, determine role from `agent:` label and area from `area:` label.
     - `agent:dev` → role is `dev`.
     - `agent:qa` → role is `qa`.
     - `agent:reviewer` → role is `reviewer`.
     - `agent:team-lead` → role is `team-lead`.
   - If role-only: search for tasks with `agent:<role>` label in the corresponding status.
   - Take the **first** result only (unless multiple keys given).

3. If no tasks found, report why and stop.

4. Determine area from `area:` label on the issue (e.g. `area:ai` → area is `ai`).

5. Read the issue with `mcp__atlassian__jira_get_issue` to see description and linked (blocking) issues.

6. Verify blocked-by issues are all Done (for dev tasks). If not, report and stop.

7. **Claim the task**: `mcp__atlassian__jira_transition_issue` → `In Progress` (for every role, including `team-lead` on On Hold tasks and Epic close-out). If the transition is rejected (Jira returns an error because the issue already left the source status — another runner claimed it), drop this task and pick the next one from the queue. If the queue is now empty, report "board contended, nothing else to take" and stop.

8. **Resolve absolute paths** (dev/qa/reviewer only). `<abs-project-root>` = `pwd` (your cwd). `<abs-workspace-path>` = `(cd <workspace.path> && pwd)` where `workspace.path` is `area.yml.workspace.path` → `config.yml.workspace.path` → `.`. Pass both in the prompt.

9. **Cwd contract.** Don't let cwd drift between `Agent(...)` spawns. For workspace ops, use a subshell: `(cd <workspace.path> && <cmd>)`. Never bare `cd <ws> && <cmd>`.

10. Launch **one Agent tool per task** in **background mode** (see "Stop semantics" below). Report `▶ <role> on <ISSUE-KEY> (<area>)`. Use `run_in_background=true`. Capture `agentId` for `TaskStop`.

    - `dev`/`qa`/`reviewer`:
      ```
      Agent(
        subagent_type="<role>",
        prompt="Project: <abs-project-root>. Area: <area>. Workspace: <abs-workspace-path>. Issue: <ISSUE-KEY>.",
        run_in_background=true,
      )
      ```
    - `team-lead` on Task in `On Hold`:
      ```
      Agent(subagent_type="team-lead", prompt="On Hold task: <ISSUE-KEY>.", run_in_background=true)
      ```
    - `team-lead` on Epic in `Code Review`:
      ```
      Agent(subagent_type="team-lead", prompt="Epic close-out: <ISSUE-KEY>.", run_in_background=true)
      ```

11. **End your turn after the spawn** — do **not** poll, do **not** sleep. The harness will notify you automatically when the background subagent completes. When the notification arrives:
    - Process the subagent's final result.
    - Report a one-line status to the user: `✓ <ISSUE-KEY> done — <one-sentence summary>` or `✗ <ISSUE-KEY> blocked — <reason>`.
    - Continue per the active mode: next stage in pipeline mode, next task in all mode, or stop in single-step modes.
