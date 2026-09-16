---
name: agent-common
description: "Shared operating contract for dev, qa, reviewer and devops: the tracker CLI, the per-task worktree and path rules, runtime and search conventions, and the sentinel flag invocation. Each charter invokes it as Bootstrap step 0; never invoked by hand."
user-invocable: false
---

# Agent common contract

Rules every task-running role — dev, qa, reviewer, devops — works under. Your charter holds what is specific to your role; this file holds what is identical across roles, once.

## Tracker commands

Tracker operations are one Bash call to the plugin CLI `${CLAUDE_PLUGIN_ROOT}/bin/dma` — always the full path, it is not on `PATH`. It reads the project's `config.yml` and tracker credentials itself; run it from `${CLAUDE_PROJECT_DIR}` or with `CLAUDE_PROJECT_DIR` set.

| Command | What it does |
|---------|--------------|
| `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <ISSUE-KEY>` | description, labels, parent, blockers, comments newest-first |
| `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <ISSUE-KEY> <body \| ->` | a comment, without touching status or labels |
| `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> [to-role] [body \| ->]` | swap the `agent:` label, transition, post the comment with the `🤖 <role> (<area>):` prefix |

Multi-line bodies go through stdin: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead - <<'EOF' … EOF`. Exit `2` means the project's tracker has no backend in the CLI — there is no other path; stop and report the message. Any other non-zero exit: stop and report the stderr text. A handoff or comment the CLI covers never goes through the tracker's MCP tools directly — the CLI is the single source of truth for label, status and prefix.

Status names in the charters are semantic keys (`in_progress`, `qa`, `code_review`, `awaiting_merge`, `awaiting_ops`, …); the tracker display name comes from `config.yml.tasks.workflow.statuses[<key>]`, and the CLI resolves it.

## Workspace

`<abs-workspace-path>` comes in your prompt as `Workspace:`. It is a git worktree of this task's repository, created for this task and already checked out on `<vcs.branch_prefix><ISSUE-KEY>`. **Everything you do happens there**: git commands, test runs, reading the code under review, and — for roles that write — edits. Paths in `dev.yml` (`write:`), `area.yml` (`test_command`) and `config.yml` (`devops_paths`) are relative to it; prepend nothing.

`${CLAUDE_PROJECT_DIR}` is the project root. Read `.claude/*` config from it; never edit task files there. A task-tree path under `${CLAUDE_PROJECT_DIR}` that lies outside `<abs-workspace-path>` is the main checkout, shared with everything else — never `Edit` / `Write` it.

Issue text and architect output may quote absolute paths (a leading `${CLAUDE_PROJECT_DIR}`); treat these as references, not targets — drop that prefix and re-root the remainder onto `<abs-workspace-path>`.

Two config values appear in git commands. They are values, not directories: `<workspace.remote>` (`area.yml` → `config.yml` → `origin`) and `<workspace.dev_branch>` (`area.yml` → `config.yml` → `vcs.dev_branch`).

- **Cwd:** `( cd <abs-workspace-path> && <cmd> )`. No bare `cd`, no `git -C` (not in the allowlist).
- **Paths:** in `Bash`, relative to `<abs-workspace-path>` after that `cd`. Absolute-path tools (`Read`, `Edit`, `Write`) take `<abs-workspace-path>/<relative>` for task files and `${CLAUDE_PROJECT_DIR}/.claude/…` for config only.
- **Branch state:** you start on `<vcs.branch_prefix><ISSUE-KEY>` — stay on that branch in that workspace until your handoff. Compare against other branches with `git diff <branch>...HEAD` or `git log <branch>..HEAD`; no checkout.
- **Runtime:** binary paths from `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `runtime:`. No `source … activate &&` and no login-shell wrapper (`bash -lc`, `sh -lc`) — both blocked by hook.
- **File search:** `Grep` / `Glob` tools, not shell `find` / `grep`.
- **Language:** every artifact in English — code, comments, commits, PRs, tracker comments, runbooks. Never mirror the user's chat language.

## Flag sentinel

Two situations always require a flag, whatever your role:

1. **You ran a prescribed command, the environment refused it, and you started looking for a workaround.** Hook blocked it, binary missing, credential not set, `runtime.*` path unresolved. The workaround search itself is the signal: the prompt failed to anticipate this case. → `ENV-FRICTION`
2. **The same kind of breakdown recurs across different tasks because the prompt's prescribed steps cause it.** Your charter's `## Flag sentinel` names the shape this takes for your role. → `PATTERN-REPEAT`

Your charter lists the further, role-specific triggers. Invocation:

```
${CLAUDE_PLUGIN_ROOT}/bin/dma sentinel flag <TYPE> "<one-line problem>" \
    --where <file:section> --reporter <your role> \
    [--originating <ISSUE-KEY>] [--details - <<'DETAILS' … DETAILS]
```

Creates a Task in the tracker's Sentinel queue. Async — your current task is unaffected. If the prompt issue also blocks you, additionally `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> team-lead`. Findings about the diff or task at hand go through `issue handoff`, never through a flag.
