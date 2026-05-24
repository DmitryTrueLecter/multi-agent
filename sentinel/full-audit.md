# Full-audit mode — procedure

System-wide structural audit across the agent system. Run manually via `/sentinel full-audit` — never auto-scheduled. Exhaustive within a fixed inventory; if a finding requires reading outside that inventory, name the missing file in the report rather than expanding the read budget mid-pass.

## Inventory (read every entry)

1. All `<abs-ma-root>/agents/*.md` — every agent prompt, including this one.
2. All `<abs-ma-root>/skills/*/SKILL.md` — every skill the agents call.
3. `<abs-ma-root>/commands/run.md` and `<abs-ma-root>/commands/board.md` — the two orchestration commands. Other commands only when an entry above references one.
4. `<abs-ma-root>/sentinel/patterns/*.md`, `<abs-ma-root>/sentinel/solutions/*.md`, `<abs-ma-root>/sentinel/area-config-schema.md`.
5. `<abs-project-root>/.claude/config.yml` and `<abs-ma-root>/config.example.yml`.
6. `<abs-project-root>/.claude/sentinel-inbox/archive/*.md` — frontmatter only, last 14 days. Use to spot `PATTERN-REPEAT` candidates.
7. One representative `<abs-project-root>/.claude/areas/<area>/area.yml` — on demand, only if a finding pivots on area-config shape.

## Cross-checks (after the inventory pass)

- Every `<RULE-ID>` cited in any agent or skill must be defined in its declared source-of-truth (`dev.md ## Code standards`, `architect.md ## Project-level invariants`, `area.yml.review_checks`). Missing → `RULE-GHOST`.
- Every rule defined in those sources-of-truth must have paired enforcement (reviewer detection, dev pre-handoff step, or process step in another agent). Missing → `RULE-ORPHANED`.
- Every status semantic key referenced in a shared-plugin file must appear in `config.example.yml.tasks.workflow.statuses`. Missing → schema drift.
- Every `agent:<X>` label referenced anywhere must have `<X>` in the `agents/sentinel.md → ## Agent roles` table.
- Every MCP tool referenced in a skill body must appear in that skill's `tools:` frontmatter.

## Severity

- **Critical** — defect breaks a real workflow path: skill calls a field the MCP does not return, mandatory file missing, required tool not granted, status key referenced is absent from config.
- **Medium** — structural inconsistency that does not break one run but leaks bugs over time: stale `tools:` lists, vestigial fragments after a rewrite, unmapped statuses, unenforced rules.
- **Low** — wording or formatting drift that survives a careful reading but signals upcoming fragmentation.

## Report

```markdown
## Sentinel full-audit — <date>

**Scope:** N agent files, M skills, K commands, plus KB and configs.

### Critical

#### 1. <one-line title> `[<taxonomy-id>]` `[<scope tag>]`
Where: file:section
Finding: one paragraph.
Fix: concrete next step. For prompt rewrites, the rewritten paragraph in full.

#### 2. ...

### Medium

...

### Low

...

### Knowledge base updates

New patterns or solutions to record, with the proposed file path (or "none").

### Recommended next actions

Ordered list, biggest leverage first. Each item names the file(s) to touch.
```

## Cross-mode contracts

- Classify findings against `agents/sentinel.md → ## Findings taxonomy`.
- Compose `Fix:` blocks under `agents/sentinel.md → ## Prompt rewrite style`.
- Apply edits only after per-file user OK — `agents/sentinel.md → ## Edit authority`.
