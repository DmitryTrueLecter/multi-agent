---
name: sentinel-full-audit
description: "Sentinel full-audit procedure: one exhaustive pass over a fixed inventory of agent prompts, skills, orchestration commands, KB and configs, with cross-checks and a severity-ranked report. Invoked by the sentinel agent on `Mode: full-audit`."
user-invocable: false
---

# Sentinel full-audit

Surface structural defects across the agent system in one pass. Exhaustive within the inventory below; a finding that needs a file outside it names that file in the report instead of widening the pass. Run manually via `/dma:sentinel full-audit`, never scheduled.

## Procedure

1. Prime: read every `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/patterns/*.md`, `solutions/*.md`, `task-schema.md`, `area-config-schema.md`, `agent-roles.md`, `status-invariants.md`.
2. Read the inventory, every entry:
   - all `${CLAUDE_PLUGIN_ROOT}/agents/*.md`, including `sentinel.md`, with each file's `tools:` frontmatter;
   - all `${CLAUDE_PLUGIN_ROOT}/skills/*/SKILL.md`;
   - `${CLAUDE_PLUGIN_ROOT}/commands/run.md` and `commands/board.md`; other commands only when an entry above references one;
   - `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` and `${CLAUDE_PLUGIN_ROOT}/config.example.yml`;
   - flag titles and `flag-type:` labels: `${CLAUDE_PLUGIN_ROOT}/bin/dma board list --label sentinel-flag` — for `PATTERN-REPEAT` candidates (the same type recurring);
   - one `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/area.yml`, only when a finding pivots on area-config shape.
3. Run the cross-checks:
   - Every `<RULE-ID>` cited in any agent or skill is defined in its source-of-truth (`dev.md ## Code standards`, `architect.md ## Project-level invariants` / `## Process invariants`, `area.yml.review_checks`). Missing → `RULE-GHOST`.
   - Every rule defined in those sources has paired enforcement (reviewer detection, dev pre-handoff step, or a process step in another agent). Missing → `RULE-ORPHANED`.
   - Every status semantic key in a shared-plugin file appears in `config.example.yml.tasks.workflow.statuses`. Missing → schema drift.
   - Every `agent:<X>` label referenced anywhere has `<X>` in `agent-roles.md`'s tracked-queue set.
   - Every MCP tool a skill body names appears in that skill's `tools:` frontmatter.
   - Every tool an agent's prompt tells it to use (`Skill`, `Edit`, `Write`, …) appears in its `tools:` frontmatter → else `TOOL-DRIFT`; granted but never used → `TOOL-EXCESS` (informational).
4. Classify each finding against the charter's `## Findings taxonomy` and rank by severity:
   - **Critical** — breaks a real workflow path: a skill reads a field the tracker does not return, a mandatory file is missing, a required tool is not granted, a referenced status key is absent from config.
   - **Medium** — inconsistency that leaks bugs over time: stale `tools:` lists, vestigial fragments after a rewrite, unmapped statuses, unenforced rules.
   - **Low** — wording or formatting drift that signals upcoming fragmentation.
5. Compose each `Fix:` per the charter's `## Writing replacements` — before-span, fenced replacement.
6. Print the report. Apply nothing: edits follow the charter's `## Edit authority`, per file, on the user's OK.

## Report format

```markdown
## Sentinel full-audit — <date>

**Scope:** N agent files, M skills, K commands, plus KB and configs.

### Critical

#### 1. <one-line title> `[<taxonomy-id>]` `[shared-plugin (cross-project: yes) | project-local]`
Where: file:section
Finding: one paragraph.
Fix: before-span, then the fenced replacement.

### Medium
…

### Low
…

### Knowledge base updates
New patterns or solutions to record, with the proposed file path — or "none".

### Recommended next actions
Ordered, biggest leverage first; each item names the file(s) to touch.
```
