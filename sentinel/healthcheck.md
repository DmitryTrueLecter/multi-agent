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

Everything else — config edits, tracker mutations, area-schema fields — stays a manual finding even in fix mode. The boundary: deterministic mechanical action with no user-choice content. Display names, area paths, label semantics are user choices; sentinel does not invent them.

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

- **HC-FS-002** — `.claude/.multi-agent` symlink resolves to a live directory.
  - Severity: CRITICAL.
  - Detection: `readlink -f <abs-project-root>/.claude/.multi-agent` returns a path and `test -d` on that path succeeds.
  - Auto-fix: none — re-pointing the plugin requires knowing where the plugin lives, which is a user choice.
  - Manual fix: `ln -snf <correct-plugin-path> <abs-project-root>/.claude/.multi-agent`.

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
  - Severity: WARN. Detection: `test -f <abs-project-root>/.mcp.json`. Manual fix: configure MCP servers.

- **HC-MCP-002** — Configured tracker MCP responds.
  - Severity: WARN.
  - Detection: one trivial read call —
    - `linear` → `mcp__linear__list_teams`.
    - `jira` → `mcp__atlassian__jira_search` with a result limit of 1.
  - Manual fix: authenticate or verify credentials.

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
✗ HC-FS-002 — .claude/.multi-agent dangling
  Manual fix: ln -snf <plugin-path> <abs-project-root>/.claude/.multi-agent
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
