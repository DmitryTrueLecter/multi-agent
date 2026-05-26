---
description: "Run agent: /run | /run <ISSUE-KEY> | /run pipeline | /run all | /run dev | /run <area/role>"
---

Launch a subagent to work on a Jira task.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key`, `tasks.workflow.statuses` (semantic key → tracker display name), and known areas (scan `.claude/areas/` subdirectory names). Resolve every `<statuses.X>` reference below through that map. The task/PR operations use skills — no direct tracker or VCS platform MCP calls in this command.

**Usage patterns:**

| Command | What it does |
|---------|-------------|
| `/run` | Auto-find highest priority task, run one step |
| `/run <ISSUE-KEY>` | Run the responsible agent for this issue (role from label) |
| `/run pipeline` | Find highest priority task, run full cycle (dev → qa → reviewer → done) |
| `/run pipeline <ISSUE-KEY>` | Run full cycle for a specific task |
| `/run all` | Run tasks until the board is clear (each task = full pipeline) |
| `/run dev` | First available `to_do` task for **any** area's dev |
| `/run qa` | First available `qa` task for **any** area's qa |
| `/run reviewer` | First available `code_review` task for **any** area's reviewer |
| `/run devops` | First available `to_do` task labelled `agent:devops` |
| `/run sentinel` | First available `to_do` task labelled `agent:sentinel` |
| `/run <area>/dev` | First available `to_do` task for that area's dev |
| `/run <area>/<role> <ISSUE-KEY>` | Run a specific role on a specific issue (override role) |
| `/run <KEY-1> <KEY-2>` | Two separate parallel agents (roles from labels) |

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

**Claim model.** Pickup = `mcp__atlassian__jira_transition_issue` → status name `statuses.in_progress`. This is the atomic claim — Jira rejects the second runner because the workflow disallows transition from `in_progress` to `in_progress`. Every queue JQL filters by pre-claim status (`to_do` / `qa` / `code_review` / `on_hold`), so a claimed task disappears from every queue automatically.

## PR feedback reconciliation (pre-flight, runs first in every mode)

Reviewer-approved tasks sit in `statuses.awaiting_merge` until the user merges or declines the PR in the VCS platform. Before searching for the next task to run, this pre-flight syncs those user decisions into the issue tracker.

**When to run.** As the very first step of every `/run` invocation — auto-mode, pipeline mode, all mode, single-issue mode, role-only shortcut. On `/run all`, re-runs before each iteration's task pickup.

Run `/pr-feedback` — the skill handles all PR list queries, issue tracker label/status updates, epic close-out promotion, and error recovery. It returns once all pending decisions are synced.

## Stuck task pre-flight (runs after PR feedback reconciliation, before queue search)

A task in `<statuses.in_progress>` with an `agent:<role>` label is either being worked on right now (this session or another) or was abandoned mid-flight by an externally-terminated subagent (usage limit, sandbox kill, OOM). The tracker alone cannot tell the two apart, and this session's `TaskList` only sees its own subagents. This pre-flight surfaces ambiguous tasks and asks the user — it never rolls back automatically.

**When to run.** Once per `/run` invocation, immediately after `/pr-feedback`, before the first queue search. Runs in every mode (`/run`, `/run pipeline`, `/run all`, `/run <KEY>`, role-only shortcut). On `/run all`, does **not** re-run before each iteration — within a single invocation, the only new in-progress tasks are ones this session just spawned.

1. **List in-progress tasks** across roles:
   - `/issue-search status:<statuses.in_progress> label:agent:dev`
   - `/issue-search status:<statuses.in_progress> label:agent:qa`
   - `/issue-search status:<statuses.in_progress> label:agent:reviewer`
   - `/issue-search status:<statuses.in_progress> label:agent:team-lead`
   - `/issue-search status:<statuses.in_progress> label:agent:devops`

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
   - **Leave alone** — no tracker change; skip this task for the current `/run` invocation. Use when the task is likely running in another session.

6. **Recency hint.** Tasks claimed within the last few minutes are almost certainly running in another session; tasks claimed hours or days ago are almost certainly stuck. Show the duration so the user has the signal — do not act on it automatically.

## Worktree bootstrap (called by step 7)

Every agent that operates on a specific branch's state — dev, qa, reviewer, devops, sentinel Mode: task, team-lead at epic close-out — runs inside a persistent git worktree under `.worktrees/<KEY>`. This isolates the working tree per task / epic so parallel agents on different keys do not collide.

**When called.** Step 7 invokes this procedure once per agent the current `/run` invocation is about to spawn. For task-scoped agents the key is the task `ISSUE-KEY`; for team-lead epic close-out the key is the `EPIC-KEY` and the procedure runs once per area-repo touched by the epic (see "Multi-repo team-lead epic close-out" below).

**Inputs.** `<abs-project-root>` (orchestrator's cwd), `<workspace.path>` resolved per the agent's role (per step 7), the issue/epic key.

### Steps

1. Resolve the repo that owns the workspace: `<abs-repo-root>` = `(cd <workspace.path> && git rev-parse --show-toplevel)`. In a monorepo this equals `<abs-project-root>`. In a multi-repo project this equals the area-repo (e.g. `<abs-project-root>/trackronos-backend`).
2. Set `<abs-worktree-path>` = `<abs-repo-root>/.worktrees/<KEY>`.
3. If `<abs-worktree-path>` does not exist, create it:
   ```
   git -C <abs-repo-root> worktree add --detach <abs-worktree-path> HEAD
   ```
   On git failure (typical cause: branch already checked out in another worktree), stop and report — the user closes the conflicting worktree first.
4. If `<abs-worktree-path>/.claude/` exists after the add (parent-repo case — monorepo, or any worktree whose checkout includes `.claude/`), replicate the gitignored pieces:
   - Discover the plugin parent name dynamically — projects pin to upstream repo names, the canonical `.multi-agent` is one valid value among many. Read the target of any working entry symlink: `<plugin-parent-name>` = `dirname $(readlink <abs-project-root>/.claude/agents)`. If `agents` is not a symlink (no plugin mount in this project), skip step 4 entirely.
   - Resolve the absolute plugin path: `<abs-plugin-root>` = `readlink -f <abs-project-root>/.claude/<plugin-parent-name>`.
   - `ln -snf <abs-plugin-root> <abs-worktree-path>/.claude/<plugin-parent-name>` — restores the gitignored parent symlink so the worktree's committed entry symlinks (`.claude/agents`, `.claude/skills`, etc.) resolve.
   - `ln -snf <abs-project-root>/.claude/sentinel-inbox <abs-worktree-path>/.claude/sentinel-inbox` — shares the inbox across worktrees.
5. Return `<abs-worktree-path>` to step 7 as the resolved workspace.

### Multi-repo team-lead epic close-out

When step 7 prepares a `team-lead` epic close-out spawn, the worktree is created in **every area-repo touched by the epic's children**, not just one.

1. Collect the set of areas touched by the epic — call `/issue-search parent:<EPIC-KEY>` and union the `area:<area>` labels of the children.
2. For each area in that set, resolve `<workspace.path>` from `<area>/area.yml` and run "Steps" above with `<EPIC-KEY>` as the key. Each iteration produces one worktree under that area-repo's `.worktrees/<EPIC-KEY>/`. Team-lead checks out branch `<vcs.branch_prefix><EPIC-KEY>` inside each per its agent prompt.
3. Pass the full list to team-lead as `Workspaces: <area1>=<abs-worktree-path-1>;<area2>=<abs-worktree-path-2>;…` (see step 9 spawn shape).

### Cleanup

The bootstrap creates the worktree; `/handoff <KEY> done` removes it (see `skills/handoff/SKILL.md`). `/run` does not clean up on its own. Orphaned worktrees (task closed via UI, `/pr-feedback` skipped, etc.) surface in `/sentinel healthcheck` (HC-WT-001).

## Auto-mode (`/run` without arguments)

Search for the first available issue in priority order. Stop at the first match:

0. **Run pre-flights** — `/pr-feedback` (see "PR feedback reconciliation" above), then stuck-task scan (see "Stuck task pre-flight" above).
1. **On hold** — `/issue-search status:<statuses.on_hold> label:agent:team-lead`. Launch `team-lead` agent. (Tasks in `awaiting_merge` and `awaiting_ops` are skipped here — `awaiting_merge` is handled by `/pr-feedback`, `awaiting_ops` is closed manually by the user.)
2. **To Do (team-lead coordination)** — `/issue-search status:<statuses.to_do> label:agent:team-lead` (filter out tasks whose blockers are not all `done`). Launch `team-lead` agent. Short lifecycle: `to_do` → team-lead acts → `done`, no dev/qa/reviewer cycle. Typical source: sentinel triage routing a finding that needs architect consultation followed by `Mode: structure` applies, or area scaffolding.
3. **To Do (sentinel)** — `/issue-search status:<statuses.to_do> label:agent:sentinel` (filter out tasks whose blockers are not all `done`). Launch `sentinel` agent in task-mode. Short lifecycle: `to_do` → sentinel works the area branch and opens a PR → `awaiting_merge`, no dev/qa/reviewer cycle. Typical source: prompt-deliverable Task created by team-lead per `agents/team-lead.md → ## Consulting sentinel → Task`.
4. **Code Review (group)** — `/issue-search type:group status:<statuses.code_review> label:agent:team-lead`. Launch `team-lead` agent for group close-out.
5. **Code Review (Task)** — `/issue-search type:task status:<statuses.code_review> label:agent:reviewer`. Also accept `agent:reviewer` in `<statuses.to_do>` (a reviewer task the stuck-task pre-flight rolled back) — `agent:<role>` marks the owner, so a `to_do` task is dispatched to its agent just as `dev`/`devops`/`team-lead`/`sentinel` tasks are. Launch `reviewer` agent on the first match.
6. **QA** — `/issue-search status:<statuses.qa> label:agent:qa`. Also accept `agent:qa` in `<statuses.to_do>` (a qa task the stuck-task pre-flight rolled back). Launch `qa` agent on the first match.
7. **To Do (dev)** — `/issue-search status:<statuses.to_do> label:agent:dev` (filter out tasks whose blockers are not all `done`). Launch `dev` agent.
8. **To Do (devops)** — `/issue-search status:<statuses.to_do> label:agent:devops` (filter out tasks whose blockers are not all `done`). Launch `devops` agent.

If nothing found at any level, report that the board is clear.

## Pipeline mode (`/run pipeline [ISSUE-KEY]`)

Run a single task through the **full lifecycle** until `done` (or until it gets stuck on `on_hold`).

**Devops tasks are not eligible for pipeline mode** — they have no qa/reviewer cycle, and `awaiting_ops` requires human action that the agent loop cannot drive. Use `/run <DEVOPS-KEY>` (single step) instead. If a key labelled `agent:devops` is passed to pipeline mode, stop and report: "devops tasks run as a single step — use /run <KEY> instead."

0. **Run pre-flights** before the first stage — `/pr-feedback` (see "PR feedback reconciliation" above) and stuck-task scan (see "Stuck task pre-flight" above).

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

## All mode (`/run all`)

Run tasks until the board is clear.

1. **Run pre-flights** — `/pr-feedback` (see "PR feedback reconciliation" above) runs before each iteration; the stuck-task scan (see "Stuck task pre-flight" above) runs only on the first iteration.
2. Use auto-mode priority to find a task.
3. Run it through the **full pipeline** (same as pipeline mode).
4. After the task reaches `done` (or `on_hold`), go back to step 1 (reconciliation runs again before the next iteration).
5. Stop when no tasks are found at any priority level.
6. Report a summary of what was completed.

**Guard**: after **3 consecutive `on_hold` results**, stop and report — the board likely needs human attention.

## Stop semantics

Subagents launched by `/run` always run in **background mode** (see step 8 in "Steps"), so this main session is responsive to user messages while a subagent works. The user can interrupt the loop at any time.

**Stop intent.** A user message containing `stop`, `остановись`, `abort`, `cancel`, `отмена`, or equivalent phrasing means "kill the current subagent and exit the loop". Be conservative: a permission approval (`yes`, `ok`), a follow-up question, or any other message is **not** stop intent — only act on explicit signals.

**On stop:**

1. Call `TaskStop` with `task_id` set to the `agentId` you captured when spawning the current background subagent.
2. Do **not** spawn the next subagent. Exit pipeline / all-mode cleanly.
3. Report to the user: `Stopped <ISSUE-KEY> mid-flight. Completed in this run: <list of issues that reached done or terminal state>.`

**Fallback** if `TaskStop` fails or returns an error: do not spawn the next agent, let the current one finish on its own, then exit the loop. Tell the user explicitly: "TaskStop failed — waiting for current subagent to complete, then will exit. New subagents will not be started."

**Kill latency.** `TaskStop` interrupts the subagent at its next decision point — between tool calls, not in the middle of one. If the subagent is currently inside a long-running Bash command (e.g. a slow test suite), it finishes that command first and exits afterwards. In typical multi-agent flows (many short tracker / git / file operations) the kill takes seconds.

## Steps (for single-step modes)

0. **Run pre-flights** before parsing arguments — `/pr-feedback` (see "PR feedback reconciliation" above) and stuck-task scan (see "Stuck task pre-flight" above). Both apply even on `/run <ISSUE-KEY>`, so a queued user-decline and any half-claimed in-progress task surface before this manual run picks anything up.

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
     - `agent:sentinel` → role is `sentinel`.
     - `agent:devops` → role is `devops`.
   - If role-only: use `/issue-search status:<statuses.[role-queue-key]> label:agent:<role>`, where the role-queue-key comes from the **Role → queue mapping** table above.
   - Take the **first** result only (unless multiple keys given).

3. If no tasks found, report why and stop.

4. Determine area from `area:` label on the issue (e.g. `area:ai` → area is `ai`).

5. Verify blocked-by issues are all `done` (for dev tasks, using data already returned in step 2). If not, report and stop.

6. **Claim the task**: `/issue-claim <KEY>` (for every role). On failure (another runner claimed it first), drop this task and pick the next one. If the queue is now empty, report "board contended, nothing else to take" and stop. On success, use the full task data returned by the skill — no separate `/task-read` needed.

7. **Resolve absolute paths and bootstrap the worktree** (dev / qa / reviewer / devops / sentinel Mode: task / team-lead epic close-out).
   - `<abs-project-root>` = `pwd` (your cwd).
   - `<workspace.path>` resolution per agent role:
     - dev / qa / reviewer / sentinel Mode: task: `area.yml.workspace.path` → `config.yml.workspace.path` → `.`.
     - devops: `config.yml.workspace.path` → `.` (no area override).
     - team-lead epic close-out: per-area; see "Multi-repo team-lead epic close-out" under "## Worktree bootstrap".
   - Run **Worktree bootstrap** (see section above) with `<workspace.path>` and the issue / epic key. The procedure returns `<abs-worktree-path>`. Pass that as `Workspace:` to the agent. For team-lead epic close-out, the procedure returns the multi-area list passed as `Workspaces:`.

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
    - `team-lead` on Task in `to_do` (coordination):
      ```
      Agent(subagent_type="team-lead", prompt="Coordination task: <ISSUE-KEY>.", run_in_background=true)
      ```
    - `team-lead` on Task in `on_hold`:
      ```
      Agent(subagent_type="team-lead", prompt="On Hold task: <ISSUE-KEY>.", run_in_background=true)
      ```
    - `team-lead` on group issue in `code_review`:
      ```
      Agent(
        subagent_type="team-lead",
        prompt="Project: <abs-project-root>. Group close-out: <ISSUE-KEY>. Workspaces: <area1>=<abs-worktree-path-1>;<area2>=<abs-worktree-path-2>.",
        run_in_background=true,
      )
      ```
      Workspaces resolved by "Worktree bootstrap" → "Multi-repo team-lead epic close-out". One worktree per area-repo touched by the epic.
    - `sentinel` on Task in `to_do` (prompt-deliverable):
      ```
      Agent(
        subagent_type="sentinel",
        prompt="Project: <abs-project-root>. Workspace: <abs-workspace-path>. Mode: task. Issue: <ISSUE-KEY>.",
        run_in_background=true,
      )
      ```
    - `devops`:
      ```
      Agent(
        subagent_type="devops",
        prompt="Project: <abs-project-root>. Workspace: <abs-workspace-path>. Issue: <ISSUE-KEY>.",
        run_in_background=true,
      )
      ```
      Note: no `Area:` parameter — devops is project-scoped. Workspace resolves from `config.yml.workspace` (no area override).

10. **End your turn after the spawn** — do **not** poll, do **not** sleep. The harness will notify you automatically when the background subagent completes. When the notification arrives, classify the final result before reporting:

    - **Clean completion** — final result describes a handoff, a stop reason, or a normal terminal state. Report `✓ <ISSUE-KEY> done — <one-sentence summary>` or `✗ <ISSUE-KEY> blocked — <reason>` and continue per the active mode (next stage in pipeline mode, next task in all mode, or stop in single-step modes).
    - **External termination** — final result matches one of: `session limit`, `usage limit`, `rate limit`, `killed`, `aborted`, `OOM`, or other phrasing indicating the subagent did not exit on its own decision. Report `⏸ <ISSUE-KEY> interrupted (external — <quote the trigger phrase>)` and **stop the loop** — do not advance the pipeline, do not pick the next task in all-mode. Make no tracker changes: the task stays in `<statuses.in_progress>` with `agent:<role>` and will be surfaced by the stuck-task pre-flight on the next `/run` invocation.
