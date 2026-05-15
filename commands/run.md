---
description: "Run agent: /run | /run <ISSUE-KEY> | /run pipeline | /run all | /run dev | /run <area/role>"
---

Launch a subagent to work on a Jira task.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key` and known areas (scan `.claude/areas/` subdirectory names). The task/PR operations use skills — no direct tracker or VCS platform MCP calls in this command.

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

Reviewer-approved tasks sit in `On Hold` + `agent:user` + `awaiting-merge` until the user merges or declines the PR in the VCS platform. Before searching for the next task to run, this pre-flight syncs those user decisions into the issue tracker.

**When to run.** As the very first step of every `/run` invocation — auto-mode, pipeline mode, all mode, single-issue mode, role-only shortcut. On `/run all`, re-runs before each iteration's task pickup.

Run `/pr-feedback` — the skill handles all PR list queries, issue tracker label/status updates, epic close-out promotion, and error recovery. It returns once all pending decisions are synced.

## Auto-mode (`/run` without arguments)

Search for the first available issue in priority order. Stop at the first match:

0. **Run PR feedback reconciliation** (see above) — run `/pr-feedback`.
1. **On Hold** — `/issue-search status:"On Hold" label:agent:team-lead`. Launch `team-lead` agent. (Tasks with `agent:user` + `awaiting-merge` are skipped — handled by `/pr-feedback`, not by an agent run.)
2. **Code Review (group)** — `/issue-search type:group status:"Code Review" label:agent:team-lead`. Launch `team-lead` agent for group close-out.
3. **Code Review (Task)** — `/issue-search type:task status:"Code Review" label:agent:reviewer`. Launch `reviewer` agent.
4. **QA** — `/issue-search status:QA label:agent:qa`. Launch `qa` agent.
5. **To Do** — `/issue-search status:"To Do" label:agent:dev` (filter out tasks whose blockers are not all Done). Launch `dev` agent.

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

1. **Run PR feedback reconciliation** (see above) — run `/pr-feedback`.
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

**Kill latency.** `TaskStop` interrupts the subagent at its next decision point — between tool calls, not in the middle of one. If the subagent is currently inside a long-running Bash command (e.g. a slow test suite), it finishes that command first and exits afterwards. In typical multi-agent flows (many short tracker / git / file operations) the kill takes seconds.

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
   - If issue keys given: use `/task-read <KEY>` on each — determine role from `agent:` label and area from `area:` label.
     - `agent:dev` → role is `dev`.
     - `agent:qa` → role is `qa`.
     - `agent:reviewer` → role is `reviewer`.
     - `agent:team-lead` → role is `team-lead`.
   - If role-only: use `/issue-search status:<queue-status> label:agent:<role>`.
   - Take the **first** result only (unless multiple keys given).

3. If no tasks found, report why and stop.

4. Determine area from `area:` label on the issue (e.g. `area:ai` → area is `ai`).

5. Verify blocked-by issues are all Done (for dev tasks, using data already returned in step 2). If not, report and stop.

6. **Claim the task**: `/issue-claim <KEY>` (for every role). On failure (another runner claimed it first), drop this task and pick the next one. If the queue is now empty, report "board contended, nothing else to take" and stop. On success, use the full task data returned by the skill — no separate `/task-read` needed.

7. **Resolve absolute paths** (dev/qa/reviewer only). `<abs-project-root>` = `pwd` (your cwd). `<abs-workspace-path>` = `(cd <workspace.path> && pwd)` where `workspace.path` is `area.yml.workspace.path` → `config.yml.workspace.path` → `.`. Pass both in the prompt.

8. **Cwd contract.** Don't let cwd drift between `Agent(...)` spawns. For workspace ops, use a subshell: `(cd <workspace.path> && <cmd>)`. Never bare `cd <ws> && <cmd>`.

9. Launch **one Agent tool per task** in **background mode** (see "Stop semantics" below). Report `▶ <role> on <ISSUE-KEY> (<area>)`. Use `run_in_background=true`. Capture `agentId` for `TaskStop`.

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
    - `team-lead` on group issue in `Code Review`:
      ```
      Agent(subagent_type="team-lead", prompt="Group close-out: <ISSUE-KEY>.", run_in_background=true)
      ```

10. **End your turn after the spawn** — do **not** poll, do **not** sleep. The harness will notify you automatically when the background subagent completes. When the notification arrives:
    - Process the subagent's final result.
    - Report a one-line status to the user: `✓ <ISSUE-KEY> done — <one-sentence summary>` or `✗ <ISSUE-KEY> blocked — <reason>`.
    - Continue per the active mode: next stage in pipeline mode, next task in all mode, or stop in single-step modes.
