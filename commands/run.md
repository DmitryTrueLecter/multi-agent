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

## Auto-mode (`/run` without arguments)

Search for the first available issue in priority order. Stop at the first match:

1. **On Hold** — Tasks with `agent:team-lead` label. Launch `team-lead` agent.
2. **Code Review (Epic)** — Epics with `agent:team-lead` label. Launch `team-lead` agent for epic close-out.
3. **Code Review (Task)** — Tasks with `agent:reviewer` label. Launch `reviewer` agent.
4. **QA** — Tasks with `agent:qa` label. Launch `qa` agent.
5. **To Do** — Tasks with `agent:dev` label (whose blockers are all Done). Launch `dev` agent.

If nothing found at any level, report that the board is clear.

## Pipeline mode (`/run pipeline [ISSUE-KEY]`)

Run a single task through the **full lifecycle** until Done (or until it gets stuck on On Hold).

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

1. Use auto-mode priority to find a task.
2. Run it through the **full pipeline** (same as pipeline mode).
3. After the task reaches Done (or On Hold), go back to step 1.
4. Stop when no tasks are found at any priority level.
5. Report a summary of what was completed.

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

8. **Resolve the absolute workspace path** (dev/qa/reviewer only — team-lead operates at repo root). Read `area.yml.workspace.path` → fall back to `config.yml.workspace.path` → default `.`. If relative, join with `$CLAUDE_PROJECT_DIR`. Pass the result as `<abs-workspace-path>` in the prompt below.

9. **Main-session cwd contract.** Before every `Agent(...)` spawn, your cwd MUST equal `$CLAUDE_PROJECT_DIR`. For any workspace-touching Bash, use a subshell: `(cd <workspace.path> && <cmd>)` — never bare `cd <workspace.path> && <cmd>`, which leaks cwd.

10. Launch **one Agent tool per task**, in **background mode**, so this main session stays responsive to the user (see "Stop semantics" below).
    - Before spawning, report a one-line status to the user: `▶ <role> on <ISSUE-KEY> (<area>)`.
    - Use `run_in_background=true`. **Capture the `agentId` returned by the spawn** — you need it to call `TaskStop` if the user asks to stop.
    - For `dev`/`qa`/`reviewer`:
      ```
      Agent(
        subagent_type="<role>",
        prompt="Your area: <area>. Your workspace (absolute): <abs-workspace-path>. Your Jira issue: <ISSUE-KEY>. Before any other tool call, run `cd <abs-workspace-path>` — your inherited cwd is NOT guaranteed to be set. Then read your area config from .claude/areas/<area>/, read the issue with mcp__atlassian__jira_get_issue, and do the work.",
        run_in_background=true,
      )
      ```
    - For `team-lead` on a Task in `On Hold`:
      ```
      Agent(
        subagent_type="team-lead",
        prompt="Handle On Hold task: <ISSUE-KEY> — read it with mcp__atlassian__jira_get_issue, investigate, and present your analysis.",
        run_in_background=true,
      )
      ```
    - For `team-lead` on an Epic in `Code Review`:
      ```
      Agent(
        subagent_type="team-lead",
        prompt="Final review of Epic <ISSUE-KEY> — all child tasks are Done. Read the Epic and its children with mcp__atlassian__jira_get_issue / mcp__atlassian__jira_search, verify nothing is missing, and follow the 'Closing Epics' section of your role.",
        run_in_background=true,
      )
      ```

11. **End your turn after the spawn** — do **not** poll, do **not** sleep. The harness will notify you automatically when the background subagent completes. When the notification arrives:
    - Process the subagent's final result.
    - Report a one-line status to the user: `✓ <ISSUE-KEY> done — <one-sentence summary>` or `✗ <ISSUE-KEY> blocked — <reason>`.
    - Continue per the active mode: next stage in pipeline mode, next task in all mode, or stop in single-step modes.
