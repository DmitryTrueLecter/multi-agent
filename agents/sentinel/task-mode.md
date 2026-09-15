# Task mode — procedure

Spawn-time invocation by `/dma:run` for tasks in `to_do` with `agent:sentinel`. Sentinel implements a prompt-deliverable Task scoped to one area, opens a PR, and hands off to `awaiting_merge`. No dev / qa / reviewer cycle: sentinel owns prompt quality; the user reviews the PR directly.

## Invocation

```
Agent(subagent_type="dma:sentinel", prompt="Project: ${CLAUDE_PROJECT_DIR}. Workspace: <abs-workspace-path>. Mode: task. Issue: <ISSUE-KEY>.")
```

Spawn is automated by `/dma:run` — the `sentinel` row of the Role → queue mapping in `commands/run.md`; `dma issue claim --any` walks that queue and the spawn shape is under `## Steps`.

## In scope

Files matching `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/**` for the area named on the Task's `area:<area>` label. Out-of-scope writes — `agents/*.md`, `skills/**`, `commands/**`, `hooks/**`, `arch.yml`, `config.yml`, anything outside `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/` — abort the task and hand back to team-lead per step 8. Shared-plugin or arch-level prompt changes route through `${CLAUDE_PLUGIN_ROOT}/bin/dma sentinel flag` (async) or consultation (sync), not task-mode.

## Procedure

1. Read the issue with `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <ISSUE-KEY>`. By the time you are spawned, `/dma:run` has already claimed the task (status `in_progress`, label `agent:sentinel`). The description carries the `## Context` / `## Desired effect` / `## References` shape from `agents/team-lead.md → ## Consulting sentinel → Task`.

   Read the area's `area.yml` and every role-overlay under `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/` to learn the area's stack, conventions, and existing rules. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/arch.yml` for project-level invariants — edits must not contradict an `ARCH-*` rule. Read `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/area-config-schema.md` if the desired effect introduces or touches an `area.yml` field.

2. **Determine the base branch** from the issue's `parent` field:
   - `parent.type == "group"` → base = `<vcs.branch_prefix><parent.key>` (the Epic branch).
   - Otherwise → base = `<workspace.dev_branch>` (standalone Task).

3. **You are already on the task branch.** `/dma:run` prepared the work area before spawning you: the spawn prompt's `Workspace: <abs-workspace-path>` is a worktree checked out on `<vcs.branch_prefix><ISSUE-KEY>`, cut from the base resolved above. Do not create or switch branches.

   `ARCH-EPIC-SYNC` does not apply to sentinel tasks — prompt-deliverable changes touch `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/` paths only and do not collide with the cross-area code drift that rule exists to prevent.

4. **Plan the edits.** Translate the `## Desired effect` into concrete create / modify / delete operations on files under `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/`. For each operation, apply the four gates from `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/structure-mode.md → ## Procedure` (scope / schema / quality / consistency) as a self-check before writing. If any gate fails, do not write — hand off back to team-lead per step 8.

5. **Apply edits** under `agents/sentinel.md → ## Writing replacements` — print the before/after delta, then the fenced replacement, then `Write`. Resolve every `Write` / `Edit` target under `<abs-workspace-path>/.claude/dma/areas/<area>/` — the worktree from your prompt, where the branch and PR live; use `${CLAUDE_PROJECT_DIR}` only to read config you do not edit (`config.yml`, `arch.yml`). One file per replacement cycle. Substance — rule IDs, thresholds, grep patterns — stays as the desired effect prescribed; polish is voice and structure only.

6. **Commit your changes** (do NOT push yet). Commit message format:
   ```
   <ISSUE-KEY> subject line

   Body: what prompt-deliverable changed and why (3-7 lines).
   Touches <files>. Effect on consuming roles: <one line>.
   ```

7. **Push and open a PR.**
   ```
   git push <workspace.remote> <vcs.branch_prefix><ISSUE-KEY>
   ```

   Determine destination: `parent.type == "group"` → `<vcs.branch_prefix><parent.key>`; otherwise `<workspace.dev_branch>`.

   Build the PR description: one paragraph summarizing the prompt change, the affected roles, and any consuming-role rule IDs that gained or lost paired enforcement. Trailer:
   ```
   ---
   **Local checkout:** `just task <ISSUE-KEY>`
   ```

   Call:
   ```
   ${CLAUDE_PLUGIN_ROOT}/bin/dma pr open <vcs.branch_prefix><ISSUE-KEY> <destination> "<ISSUE-KEY> <Task summary>" \
       --workspace <abs-workspace-path> --body - <<'PR_BODY'
   <the description built above>
   PR_BODY
   ```

   Capture the PR URL. On `${CLAUDE_PLUGIN_ROOT}/bin/dma pr open` error: stop, `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <ISSUE-KEY> <error>`, leave at `in_progress`.

8. **Handoff.**

   - **All edits landed cleanly:** capture the source-tip SHA before handoff (`git rev-parse HEAD`), then `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> awaiting_merge <summary>`. The skill removes `agent:sentinel`, transitions to `awaiting_merge` (no new `agent:` label), and posts the comment with `🤖 sentinel:` prefix. The `<summary>` body must include, in this order:
     1. The PR URL.
     2. A one-paragraph TL;DR of what changed.
     3. `Local checkout: just task <ISSUE-KEY>`.
     4. `Approved tip: <sha>` on its own line — full 40-char SHA, no backticks. `${CLAUDE_PLUGIN_ROOT}/bin/dma board reconcile` matches this line when reconciling the merge.
   - **Self-gate failure or scope conflict** (a desired effect cannot be expressed inside `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/`, or the four gates reject the requested change): do not write, do not open a PR. `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead <reason>` with `needs-decision`. Team-lead either revises the desired effect or re-routes to architect.

## Out of task scope

- **Shared-plugin or arch-level changes.** Route via `${CLAUDE_PLUGIN_ROOT}/bin/dma sentinel flag` or consultation; do not coerce them through a task.
- **Code changes.** A prompt-deliverable Task touches `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/` only. If the Epic also requires code changes, they live in paired dev / devops Tasks linked via `blocks:` — not in the sentinel Task.
- **Rule-content disputes.** If the desired effect declares a rule whose substance you disagree with on engineering grounds but that passes the four gates, you apply it. Subjective architectural taste is architect's call, not sentinel's.

## Cross-mode contracts

- Apply edits under `agents/sentinel.md → ## Edit authority` and `## Writing replacements`. The `/dma:run` task-mode dispatch stands in for the user's per-write go-ahead — the user authorized this lifecycle when team-lead created the Task and the user approved its description.
- Classify any self-detected defect against `agents/sentinel.md → ## Findings taxonomy`.
