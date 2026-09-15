---
name: sentinel-task
description: "Sentinel task procedure: implement a prompt-deliverable Task scoped to one area's `.claude/dma/areas/<area>/`, on the task branch in the assigned worktree, open a PR, hand off to awaiting_merge. Invoked by the sentinel agent on `Mode: task`."
user-invocable: false
---

# Sentinel task

Implement one prompt-deliverable Task scoped to `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/`, open a PR, hand off to `awaiting_merge`. No dev / qa / reviewer cycle — the user reviews the PR directly. `/dma:run`'s dispatch is the write authorization: team-lead created the Task per `agents/team-lead.md → ## Consulting sentinel → Task` and the user approved its description.

Invocation (automated by `/dma:run`, the `sentinel` row of its Role → queue mapping):
```
Agent(subagent_type="dma:sentinel", prompt="Project: ${CLAUDE_PROJECT_DIR}. Workspace: <abs-workspace-path>. Mode: task. Issue: <ISSUE-KEY>.")
```

## Scope

Write only files matching `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/**` for the area on the Task's `area:<area>` label. A desired effect that needs anything else — `agents/*.md`, `skills/**`, `commands/**`, `hooks/**`, `arch.yml`, `config.yml`, code — ends the task per step 9 (scope conflict); shared-plugin or arch-level prompt changes travel by `${CLAUDE_PLUGIN_ROOT}/bin/dma sentinel flag` (async) or consultation (sync). Code the Epic needs lives in paired dev / devops Tasks linked via `blocks:`. A rule whose substance you disagree with but that passes the gates is applied — taste is architect's call.

## Procedure

1. Read the issue: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <ISSUE-KEY>`. `/dma:run` has already claimed it (`in_progress`, `agent:sentinel`). The description carries `## Context` / `## Desired effect` / `## References`.
2. Read the area: `area.yml` and every role overlay under `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/`; `${CLAUDE_PROJECT_DIR}/.claude/dma/arch.yml` (edits must not contradict an `ARCH-*` rule); `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/structure-gates.md`; `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/area-config-schema.md` when the desired effect introduces or touches an `area.yml` field.
3. Resolve the base branch from the issue's `parent` field: `parent.type == "group"` → `<vcs.branch_prefix><parent.key>` (the Epic branch); otherwise `<vcs.dev_branch>`.
4. Stay on the task branch. `Workspace: <abs-workspace-path>` is a worktree already checked out on `<vcs.branch_prefix><ISSUE-KEY>`, cut from that base. Create or switch no branches. `ARCH-EPIC-SYNC` does not apply — area prompt files do not collide with cross-area code drift.
5. Plan the edits: translate `## Desired effect` into concrete create / modify / delete operations under `<abs-workspace-path>/.claude/dma/areas/<area>/`. Run the four gates from `structure-gates.md` on each as a self-check. Any gate fails → step 9, scope conflict; write nothing.
6. Apply, one file per cycle, per the charter's `## Writing replacements`: before-span, fenced replacement, then `Write`. Every `Write` / `Edit` target is under `<abs-workspace-path>/.claude/dma/areas/<area>/` — the worktree, where the branch and PR live; `${CLAUDE_PROJECT_DIR}` is for reading config you do not edit (`config.yml`, `arch.yml`). Substance — rule IDs, thresholds, grep patterns — stays as the desired effect prescribed; polish is voice and structure only.
7. Commit (no push yet):
   ```
   <ISSUE-KEY> subject line

   Body: what prompt-deliverable changed and why (3-7 lines).
   Touches <files>. Effect on consuming roles: <one line>.
   ```
8. Push and open the PR:
   ```
   git push <workspace.remote> <vcs.branch_prefix><ISSUE-KEY>
   ```
   Destination = the base from step 3. Body: one paragraph — the prompt change, the affected roles, any consuming-role rule IDs that gained or lost paired enforcement — then the trailer:
   ```
   ---
   **Local checkout:** `just task <ISSUE-KEY>`
   ```
   Call:
   ```
   ${CLAUDE_PLUGIN_ROOT}/bin/dma pr open <vcs.branch_prefix><ISSUE-KEY> <destination> "<ISSUE-KEY> <Task summary>" \
       --workspace <abs-workspace-path> --body - <<'PR_BODY'
   <the body built above>
   PR_BODY
   ```
   Capture the PR URL. On error: stop, `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <ISSUE-KEY> <error>`, leave the task at `in_progress`.
9. Hand off:
   - **Clean landing:** `git rev-parse HEAD` for the tip SHA, then `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> awaiting_merge <summary>` (removes `agent:sentinel`, transitions, posts with the `🤖 sentinel:` prefix). The summary carries, in this order: the PR URL; a one-paragraph TL;DR; `Local checkout: just task <ISSUE-KEY>`; `Approved tip: <sha>` on its own line — full 40-char SHA, no backticks (`dma board reconcile` matches it).
   - **Scope conflict or gate failure:** no write, no PR. `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead <reason>` with `needs-decision`. Team-lead revises the desired effect or re-routes to architect.
