---
description: "Run agent: /dma:run | /dma:run <ISSUE-KEY> | /dma:run pipeline | /dma:run all | /dma:run dev | /dma:run <area/role>"
---

Launch a subagent to work on a tracker task.

**Setup:** Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` to get `tasks.project_key`, `tasks.workflow.statuses` (semantic key → tracker display name), and known areas (scan `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/` subdirectory names). Resolve every `<statuses.X>` reference below through that map. Tracker and VCS operations go through the plugin CLI `${CLAUDE_PLUGIN_ROOT}/bin/dma` (always the full path, it is not on `PATH`). Exit `2` means the project's tracker or VCS host has no backend in the CLI — stop and tell the user; there is no fallback. No direct tracker or VCS MCP calls in this command.

**Usage patterns:**

| Command | What it does |
|---------|-------------|
| `/dma:run` | Auto-find highest priority task, run one step |
| `/dma:run <ISSUE-KEY>` | Run the responsible agent for this issue (role from label) |
| `/dma:run pipeline` | Find highest priority task, run full cycle (dev → qa → reviewer → done) |
| `/dma:run pipeline <ISSUE-KEY>` | Run full cycle for a specific task |
| `/dma:run all` | Run tasks until the board is clear (each task = full pipeline) |
| `/dma:run dev` | First available `to_do` task for **any** area's dev |
| `/dma:run qa` | First available `qa` task for **any** area's qa |
| `/dma:run reviewer` | First available `code_review` task for **any** area's reviewer |
| `/dma:run devops` | First available `to_do` task labelled `agent:devops` |
| `/dma:run sentinel` | First available `to_do` task labelled `agent:sentinel` |
| `/dma:run <area>/dev` | First available `to_do` task for that area's dev |
| `/dma:run <area>/<role> <ISSUE-KEY>` | Run a specific role on a specific issue (override role) |
| `/dma:run <KEY-1> <KEY-2>` | Two separate parallel agents (roles from labels) |

**Role → queue mapping** (each role picks from one queue and claims by transitioning to `in_progress`):

| Role | Picks from status | Issue type |
|------|------------------|------------|
| `team-lead` | `to_do` | Task (coordination — sentinel-routed, scaffolding) |
| `team-lead` | `on_hold` | Task (decision needed) |
| `team-lead` | `code_review` | Epic (final epic close-out) |
| `sentinel` | `to_do` | Task (prompt-deliverable in area scope) |
| `reviewer` | `code_review` | Task |
| `qa` | `qa` | Task |
| `dev` | `to_do` | Task |
| `devops` | `to_do` | Task |

The `agent:` label disambiguates queues that share a status: `code_review` splits into `agent:reviewer` (Task) vs `agent:team-lead` (Epic); `to_do` splits into `agent:team-lead` (coordination), `agent:sentinel` (prompt-deliverable), `agent:dev` (application), and `agent:devops` (infra).

**Claim model.** Pickup = `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim <KEY>`, which transitions the task to `statuses.in_progress`. That transition is the atomic claim — the tracker rejects the second runner because the workflow disallows `in_progress` → `in_progress`, and the command exits `3` (`CLAIM_FAILED`) without retrying. Every queue JQL filters by pre-claim status (`to_do` / `qa` / `code_review` / `on_hold`), so a claimed task disappears from every queue automatically.

## PR feedback reconciliation (pre-flight, runs first in every mode)

Reviewer-approved tasks sit in `statuses.awaiting_merge` until the user merges or declines the PR in the VCS platform. Before searching for the next task to run, this pre-flight syncs those user decisions into the issue tracker.

**When to run.** As the very first step of every `/dma:run` invocation — auto-mode, pipeline mode, all mode, single-issue mode, role-only shortcut. On `/dma:run all`, re-runs before each iteration's task pickup.

Run `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` — one Bash call. It finds the tasks sitting in `<statuses.awaiting_merge>`, matches each to the newest pull request on its branch, and applies the decision (declined → `agent:dev` + `to_do`; merged → `done`, with the stale-tip guard and group close-out). It reads `config.yml` and the credentials itself. Exit `2` means the project's tracker or VCS host has no backend (the message names it) — stop and tell the user; there is no other path, and skipping the pre-flight would leave merged work unreconciled. any other non-zero exit: stop and report the stderr. Single-PR failures are logged and skipped, and the next pre-flight retries them.

## Stuck task pre-flight (runs after PR feedback reconciliation, before queue search)

A task in `<statuses.in_progress>` with an `agent:<role>` label is either being worked on right now (this session or another) or was abandoned mid-flight by an externally-terminated subagent (usage limit, sandbox kill, OOM). The tracker alone cannot tell the two apart, and this session's `TaskList` only sees its own subagents. This pre-flight surfaces ambiguous tasks and asks the user — it never rolls back automatically.

**When to run.** Once per `/dma:run` invocation, immediately after the PR-feedback pre-flight, before the first queue search. Runs in every mode (`/dma:run`, `/dma:run pipeline`, `/dma:run all`, `/dma:run <KEY>`, role-only shortcut). On `/dma:run all`, does **not** re-run before each iteration — within a single invocation, the only new in-progress tasks are ones this session just spawned.

1. **List in-progress tasks** — one call, the `agent:<role>` label is in the output:
   ```
   ${CLAUDE_PLUGIN_ROOT}/bin/dma board list --status <statuses.in_progress>
   ```

2. **Cross-reference with this session's live subagents** via `TaskList`. Every spawn prompt from "Steps" contains the issue key (`Issue: <KEY>`, `Coordination task: <KEY>`, `On Hold task: <KEY>`, `Group close-out: <KEY>`). A task is **active in this session** when some live `TaskList` entry's prompt mentions its key.

3. **Ambiguous tasks** are the in-progress tasks with no matching live subagent in this session. They are either running in another session or truly stuck after external termination.

4. **If no ambiguous tasks**, continue silently to queue search.

5. **If there are ambiguous tasks**, report them and wait for a per-task decision:
   ```
   ⚠ In-progress tasks with no live subagent in this session:
     - <KEY-1> (agent:<role>, area:<area>, claimed <duration> ago) — branch <branch>: <clean | N uncommitted files, M unpushed commits>
     - <KEY-2> ...
   For each, choose: roll back to <statuses.to_do> / leave alone.
   ```

   - **Roll back** — transition the task to `<statuses.to_do>`, keep the `agent:<role>` label, post a comment `🤖 team-lead: stuck-task recovery — external termination suspected, returned to queue.` The task re-enters normal queue pickup on the next iteration. If the branch shows uncommitted files or unpushed commits, repeat the warning with the file list and re-confirm before transitioning — the work survives in the branch, and the next dev that picks the task up decides what to do with it.
   - **Leave alone** — no tracker change; skip this task for the current `/dma:run` invocation. Use when the task is likely running in another session.

6. **Recency hint.** Tasks claimed within the last few minutes are almost certainly running in another session; tasks claimed hours or days ago are almost certainly stuck. Show the duration so the user has the signal — do not act on it automatically.

## Work area (called by step 7)

Every agent that operates on a specific branch's state — dev, qa, reviewer, devops, sentinel Mode: task, team-lead at epic close-out — works in a git worktree of its own under `.worktrees/<KEY>`, checked out on the task branch. That isolates the working tree per task / epic so parallel agents on different keys do not collide.

**When called.** Step 7 prepares the area once per agent about to be spawned, **before** the spawn: the spawn prompt has to carry the path. For task-scoped agents the key is the task `ISSUE-KEY`; for team-lead epic close-out it is the `EPIC-KEY`, once per area-repo touched by the epic (see below).

```
${CLAUDE_PLUGIN_ROOT}/bin/dma workspace prepare <ISSUE-KEY>
```

One argument. The command reads the issue once and takes the rest from it: the `area:` label gives the checkout to work from, `parent` gives the base branch (an epic branch when the parent is a group), and the `agent:` label gives the role — dev, devops and sentinel may cut the task branch; for qa and reviewer a branch dev never pushed stops here instead of handing them an empty one.

One call, one outcome: the worktree is created (or reused as it stands — no reinstalling dependencies on a re-claim), the project's `worktree.link_paths` are linked and `worktree.setup_commands` run on a fresh one, the epic branch is synced when the task is fresh and epic-parented, and the task branch is cut or checked out. The last line is `workspace: <abs-path>` — pass it to the agent as `Workspace:`.

Non-zero exit — nothing is ready, so **do not spawn**. Every case below also **records the block on the task**, so the board shows why it stalled instead of leaving it `in_progress` with nobody working on it:

| Exit | Meaning | What to do |
|------|---------|-----------|
| `10` | the epic branch is not on the remote | create it — `${CLAUDE_PLUGIN_ROOT}/bin/dma branch create-epic <EPIC-KEY> --area <area>` — then re-run the prepare. If it cannot be created, park the task: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead "Epic branch missing on remote. Expected: <vcs.branch_prefix><EPIC-KEY>. <output>"` |
| `11` | `ARCH-EPIC-SYNC` conflict; the merge is aborted, nothing was pushed | the epic branch and `<dev_branch>` have diverged and resolving it is not this task's job: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead "ARCH-EPIC-SYNC drift detected. <output>"`, then schedule a merge-resolution task |
| `13` | the task branch or its base is missing on the remote | `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead "ref absent in workspace: <output>"` — the same route the agents used to take, because the cause may be a missing base branch rather than a dev who forgot to push |
| `1` | git refused, or a `setup_commands` step failed | the output names it. A setup failure leaves the worktree unprovisioned and the next prepare finishes it, so fix the cause (network, missing binary) and re-run; a git refusal usually means the branch is checked out in another worktree and the user closes it |

### Multi-repo team-lead epic close-out

When step 7 prepares a `team-lead` epic close-out spawn, the worktree is created in **every area-repo touched by the epic's children**, not just one.

1. Collect the set of areas touched by the epic — call `${CLAUDE_PLUGIN_ROOT}/bin/dma board list --parent <EPIC-KEY>` and union the `area:<area>` labels of the children.
2. For each area in that set, run `${CLAUDE_PLUGIN_ROOT}/bin/dma workspace prepare <EPIC-KEY> --area <area>` — the epic itself carries no `area:` label, so name the area explicitly here. Each iteration produces one worktree under that area-repo's `.worktrees/<EPIC-KEY>/`. Team-lead checks out branch `<vcs.branch_prefix><EPIC-KEY>` inside each per its agent prompt.
3. Pass the full list to team-lead as `Workspaces: <area1>=<abs-worktree-path-1>;<area2>=<abs-worktree-path-2>;…` (see step 9 spawn shape).

### Cleanup

`${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> done` gives the work area back (it looks in every area's checkout). `/dma:run` does not clean up on its own. Orphaned work areas (task closed via UI, the PR-feedback pre-flight skipped, etc.) surface in `/dma:sentinel healthcheck` (HC-WT-001).

## Auto-mode (`/dma:run` without arguments)

0. **Run pre-flights** — `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` (see "PR feedback reconciliation" above), then the stuck-task scan (see "Stuck task pre-flight" above).
1. **Claim the highest-priority task**:
   ```
   ${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim --any
   ```
   The command walks the queues in the priority order of the **Role → queue mapping** table, skips tasks whose blockers are not all `done`, claims the first it can, and prints `role:`, `area:` and the full issue. Exit `4` means nothing is claimable — it prints why (empty queues, or which tasks were skipped as blocked, or that another runner won every race). Report that and stop.
2. Continue from step 7 of "Steps" below with the `role`, `area` and key the command printed.

## Pipeline mode (`/dma:run pipeline [ISSUE-KEY]`)

Run a single task through the **full lifecycle** until `done` (or until it gets stuck on `on_hold`).

**Devops tasks are not eligible for pipeline mode** — they have no qa/reviewer cycle, and `awaiting_ops` requires human action that the agent loop cannot drive. Use `/dma:run <DEVOPS-KEY>` (single step) instead. If a key labelled `agent:devops` is passed to pipeline mode, stop and report: "devops tasks run as a single step — use /dma:run <KEY> instead."

0. **Run pre-flights** before the first stage — `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` (see "PR feedback reconciliation" above) and stuck-task scan (see "Stuck task pre-flight" above).

1. **Find the task:**
   - If `ISSUE-KEY` given: use it.
   - If no key: use auto-mode priority to find one task.

2. **Execute stages sequentially:**
   - If task is in `to_do` with `agent:team-lead`: run `team-lead` (single step) — coordination task, no pipeline beyond it.
   - If task is in `to_do` with `agent:dev`: run `dev` → then `qa` → then `reviewer`.
   - If task is in `qa`: run `qa` → then `reviewer`.
   - If task is in `code_review`: run `reviewer`.
   - If task is in `on_hold`: run `team-lead`, then restart from whatever status it lands in.

3. **Between stages**, re-read the issue to check its current status:
   - If the task was sent back (e.g. qa → dev), **re-run** from the new status.
   - If the task moved to `on_hold`, report to user and stop.
   - If the task reached `done`, report success.

4. **Guard against infinite loops**: track how many times the task has bounced back. After **3 bounces** (e.g. qa rejects → dev fixes → qa rejects again → ...), stop and report to user.

## All mode (`/dma:run all`)

Run tasks until the board is clear.

1. **Run pre-flights** — `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` (see "PR feedback reconciliation" above) runs before each iteration; the stuck-task scan (see "Stuck task pre-flight" above) runs only on the first iteration.
2. Use auto-mode priority to find a task.
3. Run it through the **full pipeline** (same as pipeline mode).
4. After the task reaches `done` (or `on_hold`), go back to step 1 (reconciliation runs again before the next iteration).
5. Stop when no tasks are found at any priority level.
6. Report a summary of what was completed.

**Guard**: after **3 consecutive `on_hold` results**, stop and report — the board likely needs human attention.

## Stop semantics

Subagents launched by `/dma:run` always run in **background mode** (see step 8 in "Steps"), so this main session is responsive to user messages while a subagent works. The user can interrupt the loop at any time.

**Stop intent.** A user message containing `stop`, `abort`, `cancel`, or equivalent phrasing means "kill the current subagent and exit the loop". Be conservative: a permission approval (`yes`, `ok`), a follow-up question, or any other message is **not** stop intent — only act on explicit signals.

**On stop:**

1. Call `TaskStop` with `task_id` set to the `agentId` you captured when spawning the current background subagent.
2. Do **not** spawn the next subagent. Exit pipeline / all-mode cleanly.
3. Report to the user: `Stopped <ISSUE-KEY> mid-flight. Completed in this run: <list of issues that reached done or terminal state>.`

**Fallback** if `TaskStop` fails or returns an error: do not spawn the next agent, let the current one finish on its own, then exit the loop. Tell the user explicitly: "TaskStop failed — waiting for current subagent to complete, then will exit. New subagents will not be started."

**Kill latency.** `TaskStop` interrupts the subagent at its next decision point — between tool calls, not in the middle of one. If the subagent is currently inside a long-running Bash command (e.g. a slow test suite), it finishes that command first and exits afterwards. In typical multi-agent flows (many short tracker / git / file operations) the kill takes seconds.

## Steps (for single-step modes)

0. **Run pre-flights** before parsing arguments — `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` (see "PR feedback reconciliation" above) and stuck-task scan (see "Stuck task pre-flight" above). Both apply even on `/dma:run <ISSUE-KEY>`, so a queued user-decline and any half-claimed in-progress task surface before this manual run picks anything up.

1. Parse `$ARGUMENTS`:
   - If empty: auto-mode (see above).
   - If `pipeline` [+ optional key]: pipeline mode.
   - If `all`: all mode.
   - If argument matches an issue key pattern (e.g. `<ISSUE-KEY>`): issue-key mode — resolve role from `agent:` label, area from `area:` label.
   - If `dev`, `qa`, or `reviewer`: role-only shortcut.
   - Multiple issue keys: launch parallel agents.

2. Find target task(s):
   - If issue keys given: use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>` on each — determine role from `agent:` label and area from `area:` label.
     - `agent:dev` → role is `dev`.
     - `agent:qa` → role is `qa`.
     - `agent:reviewer` → role is `reviewer`.
     - `agent:team-lead` → role is `team-lead`.
     - `agent:sentinel` → role is `sentinel`.
     - `agent:devops` → role is `devops`.
   - If role-only (`dev`, `qa`, `reviewer`, `devops`, `sentinel`, `team-lead`, or `<area>/<role>`): `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim --role <role>`. It resolves the queue from the **Role → queue mapping** table, skips blocked tasks and claims the first available one — steps 5 and 6 below are already done; continue from step 7.
   - Take the **first** result only (unless multiple keys given).

3. If no tasks found, report why and stop.

4. Determine area from `area:` label on the issue (e.g. `area:ai` → area is `ai`).

5. Verify blocked-by issues are all `done` — the `blocked by:` line of the `issue read` output lists each blocker with its status. If any is unfinished, report and stop. (Queue addressing in step 2 has already applied this filter.)

6. **Claim the task**: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim <KEY>` (for every role). On exit `3` (another runner claimed it first), drop this task and pick the next one. If the queue is now empty, report "board contended, nothing else to take" and stop. On success, the command prints the full task data — no separate read needed.

7. **Prepare the work area** (dev / qa / reviewer / devops / sentinel Mode: task / team-lead epic close-out).
   ```
   ${CLAUDE_PLUGIN_ROOT}/bin/dma workspace prepare <ISSUE-KEY>
   ```
   It prints `workspace: <abs-path>` — pass that as `Workspace:` to the agent. The agent arrives in a prepared worktree, already on `<vcs.branch_prefix><ISSUE-KEY>`; it does no branch setup of its own. On a non-zero exit do not spawn — see the table in **Work area** above. For team-lead epic close-out, repeat per area with `--area <area>` and pass the list as `Workspaces:`.

8. **Cwd contract.** Don't let cwd drift between `Agent(...)` spawns. Use a subshell for anything that needs another directory: `( cd <path> && <cmd> )`. Never bare `cd`.

9. Launch **one Agent tool per task** in **background mode** (see "Stop semantics" below). Report `▶ <role> on <ISSUE-KEY> (<area>)`. Use `run_in_background=true`. Capture `agentId` for `TaskStop`.

    The spawn prompt is closed: exactly the fields shown below, nothing appended — no "verification focus", no commands to run, no per-task hints. Everything the agent needs is in the issue, the area config, and its charter; a runtime gate belongs to `area.yml.test_command` (dev runs it, team-lead re-runs it at close-out), never to a prompt line — QA in particular is static-only and treats such a line as a scope leak.

    - `dev`/`qa`/`reviewer`:
      ```
      Agent(
        subagent_type="dma:<role>",
        prompt="Project: ${CLAUDE_PROJECT_DIR}. Area: <area>. Workspace: <abs-workspace-path>. Issue: <ISSUE-KEY>.",
        run_in_background=true,
      )
      ```
    - `team-lead` on Task in `to_do` (coordination):
      ```
      Agent(subagent_type="dma:team-lead", prompt="Coordination task: <ISSUE-KEY>.", run_in_background=true)
      ```
    - `team-lead` on Task in `on_hold`:
      ```
      Agent(subagent_type="dma:team-lead", prompt="On Hold task: <ISSUE-KEY>.", run_in_background=true)
      ```
    - `team-lead` on group issue in `code_review`:
      ```
      Agent(
        subagent_type="dma:team-lead",
        prompt="Project: ${CLAUDE_PROJECT_DIR}. Group close-out: <ISSUE-KEY>. Workspaces: <area1>=<abs-worktree-path-1>;<area2>=<abs-worktree-path-2>.",
        run_in_background=true,
      )
      ```
      Workspaces resolved by "Work area" → "Multi-repo team-lead epic close-out". One worktree per area-repo touched by the epic.
    - `sentinel` on Task in `to_do` (prompt-deliverable):
      ```
      Agent(
        subagent_type="dma:sentinel",
        prompt="Project: ${CLAUDE_PROJECT_DIR}. Workspace: <abs-workspace-path>. Mode: task. Issue: <ISSUE-KEY>.",
        run_in_background=true,
      )
      ```
    - `devops`:
      ```
      Agent(
        subagent_type="dma:devops",
        prompt="Project: ${CLAUDE_PROJECT_DIR}. Workspace: <abs-workspace-path>. Issue: <ISSUE-KEY>.",
        run_in_background=true,
      )
      ```
      Note: no `Area:` parameter — devops is project-scoped. Workspace resolves from `config.yml.workspace` (no area override).

10. **End your turn after the spawn** — do **not** poll, do **not** sleep. The harness will notify you automatically when the background subagent completes. When the notification arrives, classify the final result before reporting:

    - **Clean completion** — final result describes a handoff, a stop reason, or a normal terminal state. Report `✓ <ISSUE-KEY> done — <one-sentence summary>` or `✗ <ISSUE-KEY> blocked — <reason>` and continue per the active mode (next stage in pipeline mode, next task in all mode, or stop in single-step modes).
    - **External termination** — final result matches one of: `session limit`, `usage limit`, `rate limit`, `killed`, `aborted`, `OOM`, or other phrasing indicating the subagent did not exit on its own decision. Report `⏸ <ISSUE-KEY> interrupted (external — <quote the trigger phrase>)` and **stop the loop** — do not advance the pipeline, do not pick the next task in all-mode. Make no tracker changes: the task stays in `<statuses.in_progress>` with `agent:<role>` and will be surfaced by the stuck-task pre-flight on the next `/dma:run` invocation.
