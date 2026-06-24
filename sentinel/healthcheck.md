# Sentinel healthcheck — procedure

Reference document. Authoritative source for the healthcheck check catalogue, severity scheme, auto-fix contract, and report format. The sentinel charter (`agents/sentinel.md → ## Healthcheck mode`) dispatches here; new checks land here, not in the charter.

## Scope

Triggered by `Mode: healthcheck` (diagnose only) or `Mode: healthcheck. Fix: true` (diagnose + auto-fix safe findings). Read-only by default. With `Fix: true`, sentinel applies the declared auto-fix command for each finding that has one; everything else stays a manual finding.

## Severity scheme

| Glyph | Meaning |
|-------|---------|
| `✓` | PASS — check satisfied. |
| `✗` | FAIL — defect; severity from the check's declaration (CRITICAL/WARN). |
| `⚠` | WARN — non-critical drift. |
| `ℹ` | INFO — hygiene signal; never a defect. |
| `–` | SKIPPED — prerequisite failed; check not run. |
| `↻` | FIXED — auto-fix applied in this run (only emitted under `Fix: true`). |

## Check format

Each check declares:

- **ID** — `HC-<STAGE>-NNN` for citation.
- **Description** — one sentence, what is being verified.
- **Severity** — CRITICAL / WARN / INFO.
- **Detection** — concrete commands or file-reads that produce the verdict.
- **Auto-fix** — exact command when the check is auto-fixable; absent otherwise. Applied only under `Fix: true`.
- **Manual fix** — what to tell the user when auto-fix is not declared, or when the auto-fix itself fails.

## Auto-fix contract

Under `Fix: true`, sentinel may run these classes of action without per-action confirmation:

1. **Directory create** — `mkdir -p <path>` for an empty, project-local directory the workflow expects.
2. **Template materialization** — copy a template file into a missing project-local path; never overwrites an existing file.
3. **Apply config-declared git identity** — when `config.yml → git.identity.email` AND `git.identity.name` are both set, copy them into a workspace's local git config via `git -C <workspace> config user.email <config.git.identity.email> && git -C <workspace> config user.name <config.git.identity.name>`. Only when both target keys are unset on the workspace — never overwrites. When `git.identity` is absent from config, no auto-fix is attempted: sentinel does not invent identity values. Requires `settings.json` to whitelist `Bash(git -C * config user.email *)` and `Bash(git -C * config user.name *)`; on permission denial, falls through to the standard auto-fix-failure line.
4. **Flag migration** — for each leftover file under `${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/`, create the equivalent flag issue in the Sentinel queue and delete the file (HC-MIG-001). This is the lone tracker-mutating auto-fix: each issue is a mechanical 1:1 projection of an existing flag file, not user-authored content. Runs only when the tracker responds and the `sentinel_inbox` status is transition-ready.
5. **Seed `settings.local.json` `env.PATH`** — when a `worktree.setup_commands` binary is unresolved (HC-WT-004) but found in a fixed set of standard executable directories, prepend that directory to `${CLAUDE_PROJECT_DIR}/.claude/settings.local.json` → `env.PATH`. The value is the detected directory of an existing executable, not user-authored, and the file is per-machine and gitignored. Creates the `env` block if absent, seeding `PATH` from the current environment so system directories survive; idempotent; never removes an entry. No match in the standard set → no auto-fix. Used by HC-WT-004.

Everything else — config edits other than `settings.local.json` → `env.PATH`, tracker mutations other than the one-time flag migration (HC-MIG-001), area-schema fields — stays a manual finding even in fix mode. The boundary: deterministic mechanical action with no user-choice content. Display names, area paths, label semantics are user choices; sentinel does not invent them. `settings.local.json` → `env.PATH` is the only auto-fixable config edit precisely because its value is detected, not authored.

When an auto-fix runs successfully, the check line uses `↻ FIXED — <command>`. On auto-fix failure (e.g. permission denied), the line is `✗ FAIL — auto-fix failed: <stderr>; manual fix: <command>`.

## Stage 1 — Filesystem & config files

`${CLAUDE_PLUGIN_ROOT}` is supplied pre-resolved by Claude Code; there is no plugin-root resolution step and no per-entry symlink to verify. A plugin loads atomically — if sentinel is running, the `dma` plugin is enabled and all its components are present. Claude Code surfaces any plugin load failure in `/plugin`, `claude plugin list`, and `/doctor`. This stage checks only project-local state the plugin cannot supply.

- **HC-FS-001** — `.claude/` exists at project root.
  - Severity: CRITICAL.
  - Detection: `test -d ${CLAUDE_PROJECT_DIR}/.claude`.
  - Auto-fix: none. Project not bootstrapped at all.
  - Manual fix: bootstrap the project — beyond healthcheck scope.

- **HC-FS-005** — `${CLAUDE_PROJECT_DIR}/.claude/config.yml` parses as YAML.
  - Severity: CRITICAL.
  - Detection: read file; YAML parser returns without error.
  - Auto-fix: none. Parser errors require human-readable resolution.
  - Manual fix: address the parse error at the cited line.

- **HC-FS-007** — If `config.yml → devops_paths` is declared OR the tracker has an `area:devops` label: `${CLAUDE_PROJECT_DIR}/.claude/devops/environments.md` exists.
  - Severity: WARN.
  - Detection: precondition + `test -f ${CLAUDE_PROJECT_DIR}/.claude/devops/environments.md`.
  - Auto-fix: `mkdir -p ${CLAUDE_PROJECT_DIR}/.claude/devops && cp ${CLAUDE_PLUGIN_ROOT}/sentinel/templates/environments.md ${CLAUDE_PROJECT_DIR}/.claude/devops/environments.md`. Only when the destination is missing entirely; never overwrites. After materialization, the agent must still tell the user to populate the file with real environment facts.
  - Manual fix: copy the template from `${CLAUDE_PLUGIN_ROOT}/sentinel/templates/environments.md` to `${CLAUDE_PROJECT_DIR}/.claude/devops/environments.md` and populate.

- **HC-FS-008** — If `config.yml → docs.root` declared: the directory exists at that path.
  - Severity: WARN.
  - Detection: `test -d ${CLAUDE_PROJECT_DIR}/<docs.root>`.
  - Auto-fix: none — silent directory creation would mask a config typo.
  - Manual fix: create the directory or remove the `docs.root` key.

- **HC-FS-009** — Each workspace has a local git identity (`user.email` AND `user.name`) set. Workspace set: project root if it is a git repo, plus every distinct path from `area.yml.workspace.path` (per area) and `config.yml.workspace.path` (if set); skip duplicates and non-git directories.
  - Severity: WARN.
  - Detection: per workspace, first `git -C <path> rev-parse --git-dir >/dev/null 2>&1` (skip the workspace silently if not a git repo); then `git -C <path> config user.email` and `git -C <path> config user.name` — both must return non-empty. One report line per workspace; never collapse.
  - Auto-fix: per workspace failing the check, **only if** `config.yml → git.identity.email` AND `git.identity.name` are both set — `git -C <path> config user.email <config.git.identity.email> && git -C <path> config user.name <config.git.identity.name>`. Sets only keys that are unset; never overwrites. When `git.identity` is absent from config, no auto-fix runs — manual fix reported instead.
  - Manual fix: declare `git.identity.email` and `git.identity.name` in `${CLAUDE_PROJECT_DIR}/.claude/config.yml` and re-run with `Fix: true`; or set them directly with `git -C <path> config user.email <your-email> && git -C <path> config user.name <your-name>`. Sentinel does not pick the identity — it is project- and user-specific (personal repo → personal identity; shared repo → conventional bot identity).

## Stage 2 — Config completeness

Read `${CLAUDE_PROJECT_DIR}/.claude/config.yml` once. All checks operate on the parsed structure. If HC-FS-005 failed, skip the entire stage.

No check in this stage has an auto-fix — every value here carries user-choice content (display names, branch names, paths, team keys), and silent injection of defaults would mask a real configuration intent.

- **HC-CFG-001** — `vcs.dev_branch` set.
  - Severity: CRITICAL. Detection: non-empty string. Manual fix: set in `config.yml`.

- **HC-CFG-002** — `vcs.branch_prefix` set.
  - Severity: CRITICAL. Detection: non-empty string. Manual fix: set in `config.yml`.

- **HC-CFG-003** — `tasks.provider` ∈ {`linear`, `jira`}.
  - Severity: CRITICAL. Detection: value match. Manual fix: set the value.

- **HC-CFG-004** — `tasks.team_key` and `tasks.project` set.
  - Severity: CRITICAL. Detection: non-empty strings. Manual fix: set in `config.yml`.

- **HC-CFG-005** — `tasks.workflow.statuses` has all required semantic keys: `to_do`, `in_progress`, `qa`, `code_review`, `on_hold`, `awaiting_merge`, `awaiting_ops`, `done`. Each maps to a non-empty string.
  - Severity: CRITICAL. Detection: key presence + value non-empty.
  - Manual fix: add missing keys with chosen display names.

- **HC-CFG-006** — If `provider: jira`: every value in `tasks.jira.transitions` is a non-zero integer.
  - Severity: CRITICAL. Detection: per-key integer non-zero.
  - Manual fix: run `/dma:sentinel-bootstrap-jira` — IDs come from the live Jira workflow.

- **HC-CFG-007** — (WARN) `runtime.<key>` paths (if declared) point to existing executable files.
  - Severity: WARN. Detection: `test -x <path>` per key. Manual fix: correct path or remove key.

- **HC-CFG-008** — At least one area under `${CLAUDE_PROJECT_DIR}/.claude/areas/<area>/` with both `area.yml` and `dev.yml`.
  - Severity: CRITICAL. Detection: glob + file presence. Manual fix: route through architect.

- **HC-CFG-009** — (WARN) `devops_paths` declared as a non-empty list.
  - Severity: WARN. Detection: key presence + list non-empty. Manual fix: add the list to `config.yml`.

If HC-CFG-003 fails, mark every tracker-side check downstream `– SKIPPED — HC-CFG-003 failed`.

## Stage 3 — Area config schema

For each subdirectory `<area>` under `${CLAUDE_PROJECT_DIR}/.claude/areas/`. No auto-fix — schema population is architect's responsibility.

- **HC-AREA-001** — `area.yml` parses and has required fields per `${CLAUDE_PLUGIN_ROOT}/sentinel/area-config-schema.md`: `name`, `display_name`, `paths`, `test_command`, `test_levels`.
  - Severity: WARN. Manual fix: route through architect.

- **HC-AREA-002** — `dev.yml` parses and has `role`, `context`, `write`.
  - Severity: WARN. Manual fix: route through architect.

- **HC-AREA-003** — `qa.yml` exists for the area.
  - Severity: WARN. Manual fix: decide whether QA is enforced; if yes, route through architect.

## Stage 4 — Live integration

Skip entirely if any of HC-FS-005, HC-CFG-003, HC-CFG-005 failed. No auto-fix in this stage except HC-MIG-001 (the one-time flag migration) — other tracker mutations require admin-only API and user-choice naming.

- **HC-MCP-001** — `.mcp.json` exists at project root.
  - Severity: CRITICAL. Without it every provider-bound skill (`/dma:issue-create`, `/dma:task-read`, `/dma:handoff`, `/dma:issue-search`, etc.) deadlocks — `ToolSearch` returns no matching deferred tool for the tracker MCP.
  - Detection: `test -f ${CLAUDE_PROJECT_DIR}/.mcp.json`.
  - Manual fix: copy `.mcp.json` from a sibling project's root, edit `mcpServers.<key>` to match `tasks.provider`, then restart Claude Code. MCP servers register only at session start — without a restart the file is inert.

- **HC-MCP-002** — Configured tracker MCP responds.
  - Severity: CRITICAL. A non-responding tracker MCP blocks every automated tracker write — handoffs, status transitions, comment posting all fail mid-flow.
  - Detection: one trivial read call —
    - `linear` → `mcp__linear__list_teams`.
    - `jira` → `mcp__atlassian__jira_search` with a result limit of 1.
    A `tool not available` outcome (`ToolSearch` cannot load the deferred-tool schema) means the server is not registered for this session — usually `.mcp.json` was modified without a Claude Code restart.
  - Manual fix: if `.mcp.json` was recently written or edited, restart Claude Code. Otherwise verify the MCP URL in `.mcp.json` and authenticate at the provider's auth flow.

- **HC-BOARD-001** — For each value in `tasks.workflow.statuses`: the tracker exposes that status display name.
  - Severity: WARN per missing status.
  - Detection:
    - `linear` → `mcp__linear__list_issue_statuses` for the configured team; intersect.
    - `jira` → `mcp__atlassian__jira_get_transitions` on a recent issue; union of `to_status` names is the live set.
  - Manual fix: create the missing status in the tracker, or correct the display name in `config.yml`.

- **HC-BOARD-002** — Required labels exist in tracker: `agent:dev`, `agent:qa`, `agent:reviewer`, `agent:devops`, `agent:team-lead`, `needs-decision`.
  - Severity: WARN per missing label.
  - Detection:
    - `linear` → `mcp__linear__list_issue_labels` for the team; intersect.
    - `jira` → trivial search per label (`label = "agent:dev"`). A `0 results` response with `200 OK` means label exists; an error indicates label is unknown.
  - Manual fix: create the missing label.

- **HC-BOARD-003** — For each `${CLAUDE_PROJECT_DIR}/.claude/areas/<area>/`: label `area:<area>` exists in tracker.
  - Severity: WARN. Detection: as HC-BOARD-002. Manual fix: create label.

- **HC-BOARD-004** — If `devops_paths` non-empty: label `area:devops` exists.
  - Severity: WARN. Detection: as HC-BOARD-002. Manual fix: create label.

- **HC-BOARD-005** — If `provider: jira`: every transition ID in `tasks.jira.transitions` matches a real workflow transition.
  - Severity: WARN.
  - Detection: `mcp__atlassian__jira_get_transitions` on any in-flight issue; cross-check IDs.
  - Manual fix: run `/dma:sentinel-bootstrap-jira` — workflow has changed.

- **HC-MIG-001** — No leftover file-based flags under `${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/`; any legacy flag is migrated to the Sentinel queue. Covers the file→tracker cutover; once clean it is a permanent no-op.
  - Severity: WARN per leftover flag.
  - Detection: `ls ${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/*.md 2>/dev/null` — each top-level match is an unmigrated flag. PASS when the directory is absent or holds no top-level `*.md`. SKIPPED when HC-MCP-002 failed, or (jira) `tasks.jira.transitions.sentinel_inbox` is `0` — migration cannot create issues.
  - Auto-fix: per leftover file, parse its frontmatter (`type`, `reporter`, `where`, `originating_task`) and `## Problem` / `## Details` body, then create the flag issue as `/dma:sentinel-flag` would — `/dma:issue-create Task "[<TYPE>] <problem>" labels:sentinel-flag,flag-type:<type lowercased>,agent:sentinel state:sentinel_inbox description:<Where / Reporter / Originating / Details>`. On a created key, delete the file (`git rm` if tracked, else `rm`). Emit one `↻` line per migrated flag with its new key.
  - Manual fix: re-file each via `/dma:sentinel-flag`, or run `/dma:sentinel healthcheck fix` once the tracker responds and (jira) the `sentinel_inbox` transition id is populated via `/dma:sentinel-bootstrap-jira`.

## Stage 5 — Hygiene

Pure visibility; never a FAIL, never auto-fixed.

- **HC-HYG-001** — Count open flags in the Sentinel queue: `/dma:issue-search status:<S> label:sentinel-flag`, where `<S>` is the display name of `sentinel_inbox` from `config.yml.tasks.workflow.statuses`. Report count; if >20, suggest triage.
- **HC-HYG-002** — Tasks in `on_hold` for >7 days. Detection: tracker search with status filter and updated-before predicate. List keys and last-updated dates.
- **HC-HYG-003** — Tasks in `awaiting_merge` for >7 days. Same shape.
- **HC-HYG-004** — Tasks in `awaiting_ops` for >7 days. Same shape.

## Stage 6 — Worktrees

Persistent per-task worktrees created by `/dma:run → ## Worktree bootstrap` need one invariant: every worktree on disk belongs to an open task. Flags raised inside a worktree go straight to the tracker's Sentinel queue, so no project-local flag state needs sharing across worktrees. The `dma` plugin itself needs no replication either — Claude Code loads it globally, so subagents reach their prompts in every worktree without any per-worktree symlink.

- **HC-WT-001** — No orphaned worktree directories.
  - Severity: WARN.
  - Detection: enumerate candidate repos (project root + each area-repo from `area.yml.workspace.path`). For each, list `git -C <repo> worktree list --porcelain` entries whose path matches `<repo>/.worktrees/<KEY>`. For each `<KEY>`, query the tracker. Orphaned = task is `done` or the issue does not exist.
  - Auto-fix: `git -C <repo> worktree remove <repo>/.worktrees/<KEY>`. If removal fails on uncommitted changes, downgrade to WARN with the file list and do not force.
  - Manual fix: same command, or `git worktree remove --force` after reviewing uncommitted files yourself.

- **HC-WT-003** — every declared `worktree.link_paths` entry resolves at its repo root and is gitignored.
  - Severity: WARN per entry.
  - Detection: for each entry in `config.yml` → `worktree.link_paths` (unset or empty → skip the check), at each workspace repo root (project root + each `area.yml.workspace.path`): `<repo>/<entry>` exists on disk AND `git -C <repo> check-ignore -q <entry>` returns 0. Finding once per entry missing at the repo root (bootstrap step 5 silently skips it, leaving the worktree without it) or not gitignored (a tracked path needs no link).
  - Auto-fix: none — a missing or mistyped entry needs human judgment.
  - Manual fix: correct or remove the entry in `${CLAUDE_PROJECT_DIR}/.claude/config.yml` → `worktree.link_paths`; an artifact a `setup_commands` step rebuilds belongs there, not in `link_paths`.

- **HC-WT-004** — Every `worktree.setup_commands` leading binary resolves on PATH.
  - Severity: CRITICAL — an unresolved binary aborts the worktree bootstrap (`commands/run.md` step 6), so no agent run on a fresh worktree can proceed.
  - Detection: for each entry in `config.yml` → `worktree.setup_commands` (unset or empty → skip the check): strip leading `NAME=value` env-assignment tokens, take the next token as `<bin>`, and run `command -v <bin>`. PASS when every `<bin>` resolves; FAIL once per unresolved `<bin>`. Detection runs in sentinel's own Bash, which carries the same session environment — including `settings.local.json` → `env.PATH` — that the bootstrap subshell inherits, so resolution here is a faithful proxy for bootstrap. SKIPPED when HC-FS-005 failed.
  - Auto-fix: per unresolved `<bin>`, search a fixed set of standard executable directories (`$HOME/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `/opt/local/bin`) for an executable named `<bin>`; on a hit, prepend its directory to `settings.local.json` → `env.PATH` per the env-PATH class in the auto-fix contract. No hit in the standard set → no auto-fix.
  - Manual fix: add the directory containing `<bin>` to `${CLAUDE_PROJECT_DIR}/.claude/settings.local.json` → `env.PATH` (per-machine, gitignored), or install `<bin>`. Version-manager-versioned directories (e.g. nvm node bins) are not auto-located — add them here explicitly.

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
...

### Stage 2 — Config completeness
✗ HC-CFG-005 — missing status key: awaiting_ops
  Manual fix: add to ${CLAUDE_PROJECT_DIR}/.claude/config.yml → tasks.workflow.statuses
...

### Stage 3 — Area config schema
⚠ HC-AREA-003 — area "backend" has no qa.yml
  Manual fix: decide whether QA enforced; if yes, route through architect
...

### Stage 4 — Live integration
↻ HC-MIG-001 — 2 legacy file flags migrated to Sentinel queue (<KEY1>, <KEY2>)
<other per-check lines, or>
– SKIPPED — HC-CFG-005 failed (statuses incomplete)

### Stage 5 — Hygiene
ℹ HC-HYG-001 — 3 open flags in Sentinel queue
ℹ HC-HYG-002 — 0 tasks stuck on_hold >7d
...

### Summary
N CRITICAL, N WARN, N INFO. Auto-fix applied: M (under Fix: true).
Stage X skipped due to <upstream failure>.
Top priority: <top FAIL ID and one-line fix>.
Manual actions remaining: <count>.
```

## After the report

Without `Fix: true`: read-only — no system mutation.

With `Fix: true`: only the actions declared as auto-fixable were applied; everything else remains a manual finding. The user picks which findings to address, routes prompt-level findings through the normal sentinel triage path, sends structural defects in the plugin or area schema through architect, and applies tracker setup manually.
