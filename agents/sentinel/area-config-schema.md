# area.yml — canonical schema

Source-of-truth structure for `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/area.yml`. The architect authors it (responsibility #5 in `agents/architect.md`); dev, qa, reviewer, team-lead, and sentinel read it.

## Placement rule: area.yml vs role overlays

| File | Audience | Holds |
|------|----------|-------|
| `area.yml` | all roles | area-wide architectural facts |
| `dev.yml` | dev | role-specific for dev: `role`, `context`, `write` paths, dev `guidelines` |
| `qa.yml` | qa | role-specific for qa: `role`, `context`, `visible_signatures` (optional; qa greps exported declarations when absent), `checks`, `edge_cases`, `migration_checks` |

**Rule:** if more than one role reads the field, it lives in `area.yml`. Role-specific behavior (what exactly one role uniquely consumes) lives in the role overlay. The duplication smell — same value appearing in `dev.yml` and `qa.yml` of the same area — indicates the field belongs in `area.yml`.

**Devops is project-scoped, not area-scoped.** Devops has no `areas/<area>/devops.yml` overlay. Its write fence — `config.yml → devops_paths` — is a top-level project key, defined once per project. Knowledge files (environments, runbooks) live at `${CLAUDE_PROJECT_DIR}/.claude/dma/devops/` (project-local), not under `areas/`. Do not propose moving devops into the area model: an area's defining trait is that dev / qa / reviewer share a code surface; devops does not share a surface with any area.

## Field reference

| Field | Type | Optional | Consumed by | Purpose |
|-------|------|----------|-------------|---------|
| `name` | string | no | all | Area identifier; matches directory name. |
| `display_name` | string | no | all | Human-readable area name. |
| `paths` | list of globs | no | all | Files and directories owned by this area. |
| `cross_team` | list of "trigger → area" strings | yes | dev, team-lead | Hand-off heuristic for cross-area concerns. |
| `review_checks` | list of strings (may carry `<AREA>-NNN:` IDs and `ENFORCEMENT:` clauses) | yes | reviewer | Enforceable rules. |
| `guidelines` | list of strings | yes | dev | Binding implementation rules. |
| `test_command` | string | no | dev, qa, team-lead | Per-area test invocation, run from `workspace.path`. |
| `build_command` | string | yes | team-lead | Per-area build/typecheck command. Define when `test_command` does NOT exercise full strict mode of the underlying toolchain (see `patterns/toolchain-config-divergence.md`). |
| `test_levels` | map `<level>: <description>` | no | architect | Declares which test levels are installed. Keys: `unit`, `integration`, `e2e`. Each value is a one-line description of the framework. Omit (or comment-out with reason) a key if the level is not installed. Architect prescribes test levels only from this map; if a contract logically requires an undeclared level, architect names the missing infra and requests an infra task rather than prescribing the level (see `agents/architect.md → ## Output format → ## Test contract`). |
| `file_size_caps` | map (`look`, `must_justify`) | yes | dev, reviewer | LOC thresholds for DEV-SPLIT. Overrides defaults `look=400` / `must_justify=700`. |
| `workspace` | map (`path`, `remote`, `dev_branch`) | yes | all | Per-area workspace override. |
| `authorized_layer_exceptions` | map `<file>: <reason>` | yes | reviewer | Legitimate bypasses of `review_checks` ENFORCEMENT hits. Source-code comments are never overrides — only entries here count. |

## What belongs in qa.yml.checks

`qa.yml.checks` entries run by inspection or shell on every task in the area. Two rules:

- **Express the rule as a pytest assertion if you can.** Field set on a class, exports from a module, schema shape — write `assert <expr>` in a unit test next to the code; the test runs on every change and does not depend on per-task QA procedure. Reserve `qa.yml.checks` for structural sweeps across many files (grep for forbidden imports, scan for files in wrong directories) and quality conventions a linter cannot catch (every DTO field has both a type annotation AND a description).
- **Make each entry apply to every task in the area.** A check whose body asserts the content of one specific file fires on every task — including those that do not touch the file — and produces false positives. Move single-file shape contracts into that file's own pytest, not `qa.yml`.

### Counter-example — do not write this

```yaml
- "<ClassName> fields in <path/to/file.py> exactly match the list in <spec.yml> (<field_a>, <field_b>, …)."
```

Fires on every task in the area even when the diff does not touch the file; duplicates a declaration that already lives in `<spec.yml>` into a procedural string so the two drift; correct home is a pytest in the file's own test module that imports the class and asserts the field set against the source-of-truth declaration.

### Shapes that do belong

```yaml
# structural sweep — area-wide grep for forbidden imports
- "<AREA>-LEAF: grep -rnE '^(from|import) <forbidden.modules>' <area-paths> — must return zero hits."

# quality convention applied to every file matching a glob
- "Every DTO field in <area-dto-glob> has a type annotation and a docstring or `Field(description=...)`."
```

Both rules apply unchanged to `qa.yml.edge_cases` (scenario names the agent confirms have test coverage) and `qa.yml.migration_checks` (procedural rules about migrations needing the agent's reading judgment).

## Adding a new field

A new field in `area.yml` is a structural decision that propagates across every project on this plugin. Procedure:

1. Architect proposes the field shape (key name, type, audience, purpose).
2. Sentinel extends this schema (`area-config-schema.md`) before any project's `area.yml` carries the field. Direct edits to a project's `area.yml` adding undocumented fields are a `PROMPT-FRAGMENTED` smell — flag via `/dma:sentinel-flag`.
3. Once the schema lands, the architect rolls the field into the affected project's `area.yml` and updates any consuming agent prompt (`agents/*.md`) to read it.
