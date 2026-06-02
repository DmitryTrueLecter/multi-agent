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

1. **Symlink create/restore** — `ln -snf <target> <link>`. Reversible by `rm <link>`. Always safe when `<target>` resolves.
2. **Directory create** — `mkdir -p <path>` for empty, project-local directories (e.g. `.claude/sentinel-inbox/`).
3. **Template materialization** — copy a template file into a missing project-local path; never overwrites an existing file.
4. **Apply config-declared git identity** — when `config.yml → git.identity.email` AND `git.identity.name` are both set, copy them into a workspace's local git config via `git -C <workspace> config user.email <config.git.identity.email> && git -C <workspace> config user.name <config.git.identity.name>`. Only when both target keys are unset on the workspace — never overwrites. When `git.identity` is absent from config, no auto-fix is attempted: sentinel does not invent identity values. Requires `settings.json` to whitelist `Bash(git -C * config user.email *)` and `Bash(git -C * config user.name *)`; on permission denial, falls through to the standard auto-fix-failure line.
5. **Append to JSON permissions allowlist** — add deterministic permission entries to `<abs-project-root>/.claude/settings.local.json` → `permissions.allow`. Preserves all other top-level keys and existing allow entries; skips entries already present. When the file is absent, creates it with the minimal `{"permissions": {"allow": [...]}}` shape. The set of entries is derived mechanically from the resolved environment (e.g. absolute `<ma-root>` path), not chosen by the user. Used by HC-FS-010.
6. **Append to `config.yml` `worktree.link_paths`** — add a detected link-safe runtime-artifact directory name (a self-contained runtime such as a virtualenv dir) to `config.yml` → `worktree.link_paths`, creating the `worktree:` block if absent. Values are derived mechanically from the workspace — present on disk, gitignored, and carrying a known runtime marker — not chosen by the user. Scope is link-safe artifacts only; install-managed trees (e.g. `node_modules`) are never added here — their provisioning is a user-authored `setup_commands` entry. Never removes an existing entry; idempotent (skips names already listed). Used by HC-WT-003.

Everything else — config edits other than `worktree.link_paths`, tracker mutations, area-schema fields — stays a manual finding even in fix mode. The boundary: deterministic mechanical action with no user-choice content. Display names, area paths, label semantics are user choices; sentinel does not invent them. `worktree.link_paths` is the lone auto-fixable config edit precisely because its values are detected, not authored.

When an auto-fix runs successfully, the check line uses `↻ FIXED — <command>`. On auto-fix failure (e.g. permission denied), the line is `✗ FAIL — auto-fix failed: <stderr>; manual fix: <command>`.

## Resolving `<ma-root>`

Most auto-fix commands need the shared-plugin root path. Resolve in order:

1. `readlink -f <abs-project-root>/.claude/.multi-agent`. If it resolves and points to a live directory — that is `<ma-root>`.
2. Fallback: pick any working `<abs-project-root>/.claude/<entry>` symlink, read its target, walk up one level — that's `<ma-root>`.
3. If neither resolves: `<ma-root>` is unknown. Skip every auto-fix that needs it (symlink restores) and mark them `✗ FAIL — auto-fix skipped: <ma-root> unresolvable; manual fix: <command>`.

## Stage 1 — Filesystem & symlinks

- **HC-FS-001** — `.claude/` exists at project root.
  - Severity: CRITICAL.
  - Detection: `test -d <abs-project-root>/.claude`.
  - Auto-fix: none. Project not bootstrapped at all.
  - Manual fix: bootstrap the project — beyond healthcheck scope.

- **HC-FS-002** — `<ma-root>` resolves via the bootstrap procedure in `## Resolving <ma-root>`.
  - Severity: CRITICAL.
  - Detection: run the resolution procedure. PASS if any of paths 1–2 yields a live directory; FAIL only if both fall through. The parent-symlink name under `.claude/` is irrelevant — projects pin to upstream repo names (e.g. `.claude-multi-agent-jira` when the Bitbucket repo is named that way), and path-2 (walk up from any working entry symlink) handles every variant.
  - Auto-fix: none — selecting a plugin checkout is a user choice.
  - Manual fix: ensure at least one symlink under `.claude/` points into a live plugin checkout. The canonical name `.multi-agent` is supported by path-1 for speed, but any name works via path-2 fallback.

- **HC-FS-003** — Each `.claude/<entry>` symlink resolves. Iteration set: `ls <ma-root>` minus `config.example.yml`. Currently: `agents`, `commands`, `hooks`, `scripts`, `sentinel`, `skills`, `Justfile`, `settings.json`.
  - Severity: CRITICAL per missing entry.
  - Detection: per entry, `readlink -f <abs-project-root>/.claude/<entry>` resolves and `test -e` on the target succeeds. One report line per entry; never collapse.
  - Auto-fix: `ln -snf <ma-root>/<entry> <abs-project-root>/.claude/<entry>`. Requires `<ma-root>` resolved (HC-FS-002). Skip if unknown.
  - Manual fix: same command.

- **HC-FS-004** — Shared-plugin agents present at `<ma-root>/agents/`: `dev.md`, `qa.md`, `reviewer.md`, `architect.md`, `team-lead.md`, `devops.md`, `sentinel.md`.
  - Severity: CRITICAL per missing file.
  - Detection: `test -f <ma-root>/agents/<file>`.
  - Auto-fix: none. Missing shared-plugin files mean the plugin tree is corrupt.
  - Manual fix: re-pull the plugin repository.

- **HC-FS-005** — `.claude/config.yml` parses as YAML.
  - Severity: CRITICAL.
  - Detection: read file; YAML parser returns without error.
  - Auto-fix: none. Parser errors require human-readable resolution.
  - Manual fix: address the parse error at the cited line.

- **HC-FS-006** — `.claude/sentinel-inbox/` directory exists.
  - Severity: WARN.
  - Detection: `test -d <abs-project-root>/.claude/sentinel-inbox`.
  - Auto-fix: `mkdir -p <abs-project-root>/.claude/sentinel-inbox`.
  - Manual fix: same command.

- **HC-FS-007** — If `config.yml → devops_paths` is declared OR the tracker has an `area:devops` label: `.claude/devops/environments.md` exists.
  - Severity: WARN.
  - Detection: precondition + `test -f <abs-project-root>/.claude/devops/environments.md`.
  - Auto-fix: `mkdir -p <abs-project-root>/.claude/devops && cp <ma-root>/sentinel/templates/environments.md <abs-project-root>/.claude/devops/environments.md`. Only when the destination is missing entirely; never overwrites. After materialization, the agent must still tell the user to populate the file with real environment facts.
  - Manual fix: copy the template from `<ma-root>/sentinel/templates/environments.md` to `.claude/devops/environments.md` and populate.

- **HC-FS-008** — If `config.yml → docs.root` declared: the directory exists at that path.
  - Severity: WARN.
  - Detection: `test -d <abs-project-root>/<docs.root>`.
  - Auto-fix: none — silent directory creation would mask a config typo.
  - Manual fix: create the directory or remove the `docs.root` key.

- **HC-FS-009** — Each workspace has a local git identity (`user.email` AND `user.name`) set. Workspace set: project root if it is a git repo, plus every distinct path from `area.yml.workspace.path` (per area) and `config.yml.workspace.path` (if set); skip duplicates and non-git directories.
  - Severity: WARN.
  - Detection: per workspace, first `git -C <path> rev-parse --git-dir >/dev/null 2>&1` (skip the workspace silently if not a git repo); then `git -C <path> config user.email` and `git -C <path> config user.name` — both must return non-empty. One report line per workspace; never collapse.
  - Auto-fix: per workspace failing the check, **only if** `config.yml → git.identity.email` AND `git.identity.name` are both set — `git -C <path> config user.email <config.git.identity.email> && git -C <path> config user.name <config.git.identity.name>`. Sets only keys that are unset; never overwrites. When `git.identity` is absent from config, no auto-fix runs — manual fix reported instead.
  - Manual fix: declare `git.identity.email` and `git.identity.name` in `.claude/config.yml` and re-run with `Fix: true`; or set them directly with `git -C <path> config user.email <your-email> && git -C <path> config user.name <your-name>`. Sentinel does not pick the identity — it is project- and user-specific (personal repo → personal identity; shared repo → conventional bot identity).

- **HC-FS-010** — `.claude/settings.local.json → permissions.allow` covers subagent reads through `.claude/` symlinks. The resolved `<ma-root>` absolute path differs per machine, so this allow lives in `settings.local.json` (per-machine), not the shared `settings.json`. Without it, every read of a symlinked agent prompt or skill body prompts the user once per call.
  - Severity: WARN.
  - Detection: precondition — HC-FS-002 passed (ma-root resolves). Read `<abs-project-root>/.claude/settings.local.json` (missing file → empty allow set); parse JSON; `permissions.allow` must contain all three entries verbatim: `Read(//<ma-root>/**)`, `Glob(//<ma-root>/**)`, `Grep(//<ma-root>/**)`. The leading `//` is Claude Code's absolute-path notation in permission patterns. Substitute `<ma-root>` with the resolved absolute path (e.g. `/home/alice/code/multi-agent` → `Read(//home/alice/code/multi-agent/**)`).
  - Auto-fix: append the missing entries to `permissions.allow` per the JSON-allowlist class in the auto-fix contract. Idempotent — entries already present are left untouched.
  - Manual fix: add the three allow lines to `permissions.allow` in `.claude/settings.local.json`, substituting `<ma-root>` for the resolved path.

## Stage 2 — Config completeness

Read `<abs-project-root>/.claude/config.yml` once. All checks operate on the parsed structure. If HC-FS-005 failed, skip the entire stage.

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
  - Manual fix: run `/sentinel-bootstrap-jira` — IDs come from the live Jira workflow.

- **HC-CFG-007** — (WARN) `runtime.<key>` paths (if declared) point to existing executable files.
  - Severity: WARN. Detection: `test -x <path>` per key. Manual fix: correct path or remove key.

- **HC-CFG-008** — At least one area under `.claude/areas/<area>/` with both `area.yml` and `dev.yml`.
  - Severity: CRITICAL. Detection: glob + file presence. Manual fix: route through architect.

- **HC-CFG-009** — (WARN) `devops_paths` declared as a non-empty list.
  - Severity: WARN. Detection: key presence + list non-empty. Manual fix: add the list to `config.yml`.

If HC-CFG-003 fails, mark every tracker-side check downstream `– SKIPPED — HC-CFG-003 failed`.

## Stage 3 — Area config schema

For each subdirectory `<area>` under `.claude/areas/`. No auto-fix — schema population is architect's responsibility.

- **HC-AREA-001** — `area.yml` parses and has required fields per `sentinel/area-config-schema.md`: `name`, `display_name`, `paths`, `test_command`, `test_levels`.
  - Severity: WARN. Manual fix: route through architect.

- **HC-AREA-002** — `dev.yml` parses and has `role`, `context`, `write`.
  - Severity: WARN. Manual fix: route through architect.

- **HC-AREA-003** — `qa.yml` exists for the area.
  - Severity: WARN. Manual fix: decide whether QA is enforced; if yes, route through architect.

## Stage 4 — Live integration

Skip entirely if any of HC-FS-005, HC-CFG-003, HC-CFG-005 failed. No auto-fix in this stage — tracker mutations require admin-only API and user-choice naming.

- **HC-MCP-001** — `.mcp.json` exists at project root.
  - Severity: CRITICAL. Without it every provider-bound skill (`/issue-create`, `/task-read`, `/handoff`, `/issue-search`, etc.) deadlocks — `ToolSearch` returns no matching deferred tool for the tracker MCP.
  - Detection: `test -f <abs-project-root>/.mcp.json`.
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

- **HC-BOARD-003** — For each `.claude/areas/<area>/`: label `area:<area>` exists in tracker.
  - Severity: WARN. Detection: as HC-BOARD-002. Manual fix: create label.

- **HC-BOARD-004** — If `devops_paths` non-empty: label `area:devops` exists.
  - Severity: WARN. Detection: as HC-BOARD-002. Manual fix: create label.

- **HC-BOARD-005** — If `provider: jira`: every transition ID in `tasks.jira.transitions` matches a real workflow transition.
  - Severity: WARN.
  - Detection: `mcp__atlassian__jira_get_transitions` on any in-flight issue; cross-check IDs.
  - Manual fix: run `/sentinel-bootstrap-jira` — workflow has changed.

## Stage 5 — Hygiene

Pure visibility; never a FAIL, never auto-fixed.

- **HC-HYG-001** — Count files in `.claude/sentinel-inbox/`. Report count; if >20, suggest triage.
- **HC-HYG-002** — Tasks in `on_hold` for >7 days. Detection: tracker search with status filter and updated-before predicate. List keys and last-updated dates.
- **HC-HYG-003** — Tasks in `awaiting_merge` for >7 days. Same shape.
- **HC-HYG-004** — Tasks in `awaiting_ops` for >7 days. Same shape.

## Stage 6 — Worktrees

Persistent per-task worktrees created by `/run → ## Worktree bootstrap` need two invariants: (a) every worktree on disk belongs to an open task, (b) every worktree whose checkout includes `.claude/` has the gitignored plugin / inbox symlinks resolved so subagents can read their prompts.

- **HC-WT-001** — No orphaned worktree directories.
  - Severity: WARN.
  - Detection: enumerate candidate repos (project root + each area-repo from `area.yml.workspace.path`). For each, list `git -C <repo> worktree list --porcelain` entries whose path matches `<repo>/.worktrees/<KEY>`. For each `<KEY>`, query the tracker. Orphaned = task is `done` or the issue does not exist.
  - Auto-fix: `git -C <repo> worktree remove <repo>/.worktrees/<KEY>`. If removal fails on uncommitted changes, downgrade to WARN with the file list and do not force.
  - Manual fix: same command, or `git worktree remove --force` after reviewing uncommitted files yourself.

- **HC-WT-002** — Each worktree whose checkout includes `.claude/` has both bootstrap symlinks present and resolving.
  - Severity: WARN per worktree per missing symlink.
  - Detection: for every worktree path `<P>` enumerated by HC-WT-001 where `test -d <P>/.claude` succeeds, discover the plugin parent name (`dirname $(readlink <abs-project-root>/.claude/agents)`) and check:
    - `readlink -f <P>/.claude/<plugin-parent-name>` resolves to a directory.
    - `readlink -f <P>/.claude/sentinel-inbox` resolves to a directory.
    If either fails, the worktree was created before the bootstrap landed or the symlink was removed manually.
  - Auto-fix: re-run `commands/run.md → ## Worktree bootstrap` step 4 against this worktree.
  - Manual fix: `ln -snf <abs-plugin-root> <P>/.claude/<plugin-parent-name>` and `ln -snf <abs-project-root>/.claude/sentinel-inbox <P>/.claude/sentinel-inbox`.

- **HC-WT-003** — `worktree` config covers the project's gitignored runtime artifacts.
  - Severity: WARN per uncovered artifact.
  - Detection: infer the stack from gitignored runtime markers at each workspace repo root (project root + each `area.yml.workspace.path`). A candidate directory is detected when it (a) exists on disk, (b) is gitignored (`git -C <repo> check-ignore -q <dir>` returns 0), and (c) carries a known runtime marker. Classify each by how a worktree should obtain it:
    - **Link-safe** — a self-contained runtime such as a virtualenv (`test -f <dir>/pyvenv.cfg`, conventionally `.venv`). Expected as an entry in `config.yml` → `worktree.link_paths`. Corroborate against `runtime.*` when set (e.g. `runtime.python` resolving inside the venv dir).
    - **Install-managed** — a dependency tree whose internal layout assumes a fixed location, e.g. a `node_modules` directory beside a `package.json` (linking it entangles worktrees under an isolated package-manager linker). Expected to be produced by an install entry in `config.yml` → `worktree.setup_commands`, not linked.
    Finding when a link-safe artifact is absent from `worktree.link_paths`, or when an install-managed artifact is detected while `worktree.setup_commands` is empty. Skip the check when no runtime artifacts are detected.
  - Auto-fix: link-safe case only — append the missing dir name to `config.yml` → `worktree.link_paths` per the config-link-paths class in the auto-fix contract (creates the `worktree:` block if absent; idempotent). The install-managed case has no auto-fix: the install command is user-authored.
  - Manual fix: link-safe → add the dir to `worktree.link_paths`. Install-managed → add the install command (e.g. `pnpm install --frozen-lockfile`, `npm ci`) to `worktree.setup_commands` in `.claude/config.yml`.

## Report format

```markdown
## Sentinel healthcheck — <YYYY-MM-DD>

**Project:** <abs-project-root>
**Provider:** <linear | jira | —>
**Areas:** <comma-separated names>
**Mode:** <diagnose | diagnose + fix>

### Stage 1 — Filesystem & symlinks
✓ HC-FS-001 — .claude/ present
↻ HC-FS-003 — .claude/Justfile symlink dangling — FIXED via `ln -snf <ma-root>/Justfile .claude/Justfile`
✗ HC-FS-002 — <ma-root> unresolvable (both path-1 and path-2 failed)
  Manual fix: ensure at least one symlink under .claude/ points into a live plugin checkout
...

### Stage 2 — Config completeness
✗ HC-CFG-005 — missing status key: awaiting_ops
  Manual fix: add to .claude/config.yml → tasks.workflow.statuses
...

### Stage 3 — Area config schema
⚠ HC-AREA-003 — area "backend" has no qa.yml
  Manual fix: decide whether QA enforced; if yes, route through architect
...

### Stage 4 — Live integration
<per-check lines, or>
– SKIPPED — HC-CFG-005 failed (statuses incomplete)

### Stage 5 — Hygiene
ℹ HC-HYG-001 — 3 pending flags in sentinel-inbox
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
