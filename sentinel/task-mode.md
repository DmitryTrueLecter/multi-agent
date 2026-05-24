# Task mode — procedure

Spawn-time invocation by `/run` for tasks in `to_do` with `agent:sentinel`. Sentinel implements a prompt-deliverable Task scoped to one area, opens a PR, and hands off to `awaiting_merge`. No dev / qa / reviewer cycle: sentinel owns prompt quality; the user reviews the PR directly.

## Invocation

```
Agent(subagent_type="sentinel", prompt="Project: <abs-project-root>. Mode: task. Issue: <ISSUE-KEY>.")
```

Spawn is automated by `/run` — see `commands/run.md → ## Auto-mode` bucket #3 and `## Steps` step 9.

## In scope

Files matching `.claude/areas/<area>/**` for the area named on the Task's `area:<area>` label. Out-of-scope writes — `agents/*.md`, `skills/**`, `commands/**`, `hooks/**`, `arch.yml`, `config.yml`, anything outside `.claude/areas/<area>/` — abort the task and hand back to team-lead per step 8. Shared-plugin or arch-level prompt changes route through `/sentinel-flag` (async) or consultation (sync), not task-mode.

## Procedure

1. Read the issue with `/task-read <ISSUE-KEY>`. By the time you are spawned, `/run` has already claimed the task (status `in_progress`, label `agent:sentinel`). The description carries the `## Context` / `## Desired effect` / `## References` shape from `agents/team-lead.md → ## Consulting sentinel → Task`.

   Read the area's `area.yml` and every role-overlay under `.claude/areas/<area>/` to learn the area's stack, conventions, and existing rules. Read `.claude/arch.yml` for project-level invariants — edits must not contradict an `ARCH-*` rule. Read `sentinel/area-config-schema.md` if the desired effect introduces or touches an `area.yml` field.

2. **Determine the base branch** from the issue's `parent` field:
   - `parent.type == "group"` → base = `<vcs.branch_prefix><parent.key>` (the Epic branch).
   - Otherwise → base = `<workspace.dev_branch>` (standalone Task).

3. **Resolve the task branch** in the area's workspace. The branch is `<vcs.branch_prefix><ISSUE-KEY>`. Two cases:

   ```
   cd <workspace.path>
   git fetch <workspace.remote>
   ```

   - **Re-run** (`git ls-remote --exit-code <workspace.remote> <vcs.branch_prefix><ISSUE-KEY>` returns 0): `git checkout <vcs.branch_prefix><ISSUE-KEY>` + `git pull`. Continue from prior state — the user declined a previous PR; read the most recent `🤖 user (decline) via PR <URL>:` comment for what objections to address.
   - **Fresh task**: `git checkout <base>` → `git pull` → `git checkout -b <vcs.branch_prefix><ISSUE-KEY>`.

   `ARCH-EPIC-SYNC` does not apply to sentinel tasks — prompt-deliverable changes touch `.claude/areas/<area>/` paths only and do not collide with the cross-area code drift that rule exists to prevent.

4. **Plan the edits.** Translate the `## Desired effect` into concrete create / modify / delete operations on files under `.claude/areas/<area>/`. For each operation, apply the four gates from `sentinel/structure-mode.md → ## Procedure` (scope / schema / quality / consistency) as a self-check before writing. If any gate fails, do not write — hand off back to team-lead per step 8.

5. **Apply edits** under `agents/sentinel.md → ## Writing replacements` — print the style-audit block, then the fenced replacement, then `Write`. One file per replacement cycle. Substance — rule IDs, thresholds, grep patterns — stays as the desired effect prescribed; polish is voice and structure only.

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
   /pr-open <vcs.branch_prefix><ISSUE-KEY> <destination> "<ISSUE-KEY> <Task summary>" workspace-path:<abs-workspace-path> remote:<workspace.remote> description:<pr-description>
   ```

   Capture the PR URL. On `/pr-open` error: stop, `/issue-comment <ISSUE-KEY> <error>`, leave at `in_progress`.

8. **Handoff.**

   - **All edits landed cleanly:** capture the source-tip SHA before handoff (`git rev-parse HEAD`), then `/handoff <ISSUE-KEY> awaiting_merge <summary>`. The skill removes `agent:sentinel`, transitions to `awaiting_merge` (no new `agent:` label), and posts the comment with `🤖 sentinel:` prefix. The `<summary>` body must include, in this order:
     1. The PR URL.
     2. A one-paragraph TL;DR of what changed.
     3. `Local checkout: just task <ISSUE-KEY>`.
     4. `Approved tip: <sha>` on its own line — full 40-char SHA, no backticks. `/pr-feedback` matches this line when reconciling the merge.
   - **Self-gate failure or scope conflict** (a desired effect cannot be expressed inside `.claude/areas/<area>/`, or the four gates reject the requested change): do not write, do not open a PR. `/handoff <ISSUE-KEY> team-lead <reason>` with `needs-decision`. Team-lead either revises the desired effect or re-routes to architect.

## Out of task scope

- **Shared-plugin or arch-level changes.** Route via `/sentinel-flag` or consultation; do not coerce them through a task.
- **Code changes.** A prompt-deliverable Task touches `.claude/areas/<area>/` only. If the Epic also requires code changes, they live in paired dev / devops Tasks linked via `blocks:` — not in the sentinel Task.
- **Rule-content disputes.** If the desired effect declares a rule whose substance you disagree with on engineering grounds but that passes the four gates, you apply it. Subjective architectural taste is architect's call, not sentinel's.

## Cross-mode contracts

- Apply edits under `agents/sentinel.md → ## Edit authority` and `## Writing replacements`. The `/run` task-mode dispatch stands in for the user's per-write go-ahead — the user authorized this lifecycle when team-lead created the Task and the user approved its description.
- Classify any self-detected defect against `agents/sentinel.md → ## Findings taxonomy`.
