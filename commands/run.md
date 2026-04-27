---
description: "Run agent: /run | /run <ISSUE-KEY> | /run pipeline | /run all | /run dev | /run <area/role>"
---

Launch a subagent to work on a Jira task.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key`, `tasks.labels.managed`, and known areas (scan `.claude/areas/` subdirectory names).

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

**Claim model.** Pickup = `jira_transition_issue` → `In Progress`. This is the atomic claim — Jira rejects the second runner because the workflow disallows transition from `In Progress` to `In Progress`. Every queue JQL filters by pre-claim status (`To Do` / `QA` / `Code Review` / `On Hold`), so a claimed task disappears from every queue automatically.

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

5. Read the issue with `jira_get_issue` to see description and linked (blocking) issues.

6. Verify blocked-by issues are all Done (for dev tasks). If not, report and stop.

7. **Claim the task**: `jira_transition_issue` → `In Progress` (for every role, including `team-lead` on On Hold tasks and Epic close-out). If the transition is rejected (Jira returns an error because the issue already left the source status — another runner claimed it), drop this task and pick the next one from the queue. If the queue is now empty, report "board contended, nothing else to take" and stop.

8. Launch **one Agent tool per task**:
   - For `dev`/`qa`/`reviewer`:
     ```
     Agent(subagent_type="<role>", prompt="Your area: <area>. Your Jira issue: <ISSUE-KEY> — read your area config from .claude/areas/<area>/, then read the issue with jira_get_issue and do the work.")
     ```
   - For `team-lead` on a Task in `On Hold`:
     ```
     Agent(subagent_type="team-lead", prompt="Handle On Hold task: <ISSUE-KEY> — read it with jira_get_issue, investigate, and present your analysis.")
     ```
   - For `team-lead` on an Epic in `Code Review`:
     ```
     Agent(subagent_type="team-lead", prompt="Final review of Epic <ISSUE-KEY> — all child tasks are Done. Read the Epic and its children with jira_get_issue / jira_search, verify nothing is missing, and follow the 'Closing Epics' section of your role.")
     ```

9. After the agent returns, report to the user what was done and what's next.
