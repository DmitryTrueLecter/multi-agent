---
name: sentinel-healthcheck
description: "Sentinel healthcheck procedure: diagnose project-local dma setup drift (directories, config completeness, area schema, tracker alignment, worktrees) stage by stage; with `Fix: true` apply the declared mechanical auto-fixes. Invoked by the sentinel agent on `Mode: healthcheck`."
user-invocable: false
---

# Sentinel healthcheck

Surface setup drift in the project-local dma state and, under `Fix: true`, apply the auto-fixes the catalogue declares. Read-only otherwise. Run manually via `/dma:sentinel healthcheck` or `/dma:sentinel healthcheck fix`; passing `Fix: true` is the user's authorization for the auto-fix classes below — no per-fix confirmation.

## Procedure

1. Read the catalogue: `${CLAUDE_PLUGIN_ROOT}/skills/sentinel-healthcheck/checks.md`. Every check you run comes from there; run every check in it.
2. Run the stages in order — Filesystem & config files, Config completeness, Area config schema, Live integration, Hygiene, Worktrees. Honour each stage's skip rule (a stage or check whose prerequisite failed prints `– SKIPPED — <prerequisite> failed`, and runs nothing).
3. Per check, print one line with the verdict glyph, the ID, and the one-line result; on `✗` or `⚠`, add the manual fix on the next line. Never collapse per-workspace or per-area checks into one line.
4. Under `Fix: true`, when a failing check declares an auto-fix in one of the classes below, run it and print `↻ FIXED — <command>`. On auto-fix failure print `✗ FAIL — auto-fix failed: <stderr>; manual fix: <command>`. A check without a declared auto-fix stays a manual finding in fix mode too.
5. Print the summary and stop. The user picks which findings to address: prompt-level findings go through triage, plugin or area-schema defects through architect, tracker setup by hand.

## Verdict glyphs

| Glyph | Meaning |
|-------|---------|
| `✓` | PASS — check satisfied. |
| `✗` | FAIL — defect; severity from the check's declaration (CRITICAL / WARN). |
| `⚠` | WARN — non-critical drift. |
| `ℹ` | INFO — hygiene signal; never a defect. |
| `–` | SKIPPED — prerequisite failed; check not run. |
| `↻` | FIXED — auto-fix applied in this run (only under `Fix: true`). |

## Auto-fix classes

The boundary: a deterministic mechanical action with no user-choice content. Display names, area paths, label semantics, identities are user choices; sentinel does not invent them.

1. **Directory create** — `mkdir -p <path>` for an empty, project-local directory the workflow expects.
2. **Template materialization** — copy a template from `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/templates/` into a missing project-local path; never overwrites.
3. **Config-declared git identity** — when `config.yml → git.identity.email` and `git.identity.name` are both set, copy them into a workspace's local git config (`git -C <workspace> config user.email … && … user.name …`), only for keys unset on that workspace. Absent `git.identity` → no auto-fix. Needs `settings.json` to allow `Bash(git -C * config user.email *)` and `Bash(git -C * config user.name *)`; on denial fall through to the failure line.
4. **Flag migration** — each leftover file under `${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/` becomes one flag issue in the Sentinel queue and the file is deleted (HC-MIG-001). The lone tracker-mutating auto-fix: a 1:1 projection of an existing flag file. Runs only when the tracker responds and `sentinel_inbox` is transition-ready.
5. **Seed `settings.local.json` → `env.PATH`** — when a `worktree.setup_commands` binary is unresolved (HC-WT-004) but found in `$HOME/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, or `/opt/local/bin`, prepend that directory to `${CLAUDE_PROJECT_DIR}/.claude/settings.local.json` → `env.PATH` (create the `env` block if absent, seeding `PATH` from the current environment; idempotent; never removes an entry). The value is detected, not authored, and the file is per-machine and gitignored — the only auto-fixable config edit.
6. **Layout migration** — project-local dma state at the legacy `.claude/` root (HC-FS-002) relocates into `.claude/dma/` with `git mv` (tracked) or `mv` (untracked), per path (`config.yml`, `arch.yml`, `areas/`, `devops/`, `Justfile`); a path whose `.claude/dma/<name>` counterpart exists is skipped and reported manual. The project-root `Justfile` import rewrite (`import '.claude/dma/Justfile'`) is reported as a manual follow-up, never applied.

Everything else — other config edits, other tracker mutations, area-schema fields — stays manual even in fix mode.

## Report format

```markdown
## Sentinel healthcheck — <YYYY-MM-DD>

**Project:** ${CLAUDE_PROJECT_DIR}
**Provider:** <linear | jira | —>
**Areas:** <comma-separated names>
**Mode:** <diagnose | diagnose + fix>

### Stage 1 — Filesystem & config files
✓ HC-FS-001 — .claude/ present
↻ HC-FS-007 — devops/environments.md missing — FIXED via template copy
✗ HC-FS-005 — config.yml parse error at line 12
  Manual fix: address the parse error at the cited line

### Stage 2 — Config completeness
✗ HC-CFG-005 — missing status key: awaiting_ops
  Manual fix: add to ${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml → tasks.workflow.statuses

### Stage 3 — Area config schema
⚠ HC-AREA-003 — area "backend" has no qa.yml
  Manual fix: decide whether QA is enforced; if yes, route through architect

### Stage 4 — Live integration
– SKIPPED — HC-CFG-005 failed (statuses incomplete)

### Stage 5 — Hygiene
ℹ HC-HYG-001 — 3 open flags in Sentinel queue

### Stage 6 — Worktrees
✓ HC-WT-001 — no orphaned worktrees

### Summary
N CRITICAL, N WARN, N INFO. Auto-fix applied: M (under Fix: true).
Stage X skipped due to <upstream failure>.
Top priority: <top FAIL ID and one-line fix>.
Manual actions remaining: <count>.
```
