---
name: sentinel-consultation
description: "Sentinel consultation procedure: answer one structured prompt-quality question from team-lead inline — scope guard, minimal reads, classified finding, concrete recommendation. Invoked by the sentinel agent on `Mode: consultation`."
user-invocable: false
---

# Sentinel consultation

Answer one structured question inline for team-lead (`agents/team-lead.md → ## Consulting sentinel`); leave the queue alone.

## Procedure

1. Scope guard. A technical question — pattern, library, file split, whether a design is wise — → print `Out of scope — architect consultation.` and stop.
2. Prime. Read every `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/patterns/*.md` and `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/task-schema.md`.
3. Read what the question requires — typically one or two agent or skill files, plus the cited issue (`${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>`) when the context names one — and nothing else. A question touching labels, statuses, or queues → also `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/status-invariants.md`. A question about what a role may do → also `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/agent-roles.md → ## Settled decisions`.
4. Classify against the charter's `## Findings taxonomy`; label `advisory` when no class fits.
5. Compose the recommendation. A prompt rewrite goes through the charter's `## Writing replacements`: draft per steps 1–3, then apply the checklist item by item — for each item, name the span that fails it and rewrite that span; keep the items that changed the draft for the `Checked:` line.
6. When the question reveals a defect another agent's run would also hit, file it: `${CLAUDE_PLUGIN_ROOT}/bin/dma sentinel flag <TYPE> "<problem>" --where <file:section> --reporter sentinel`.
7. Print the answer in the format below — headings verbatim.

## Output format

```markdown
## Question
<verbatim>

## Finding
Class: <taxonomy ID | advisory>
<file:section — the defect in one paragraph>

## Recommendation
<the concrete next action team-lead can take now; for a rewrite: before-span, then the fenced replacement>
Checked: <checklist items that changed the draft, each with its span — or `no changes`>

## Followup flag
<KEY filed in step 6 | —>
```

<example>
## Question
Add rule DEV-NO-PRINT: forbid `print()` in production code under `apps/**`; reviewer should block on it.

## Finding
Class: RULE-ORPHANED
`agents/dev.md → ## Code standards` would gain a rule with no paired detection; `agents/reviewer.md → ## Detection` has no `DEV-NO-PRINT` block, so the rule would be decoration until one exists.

## Recommendation
Land both halves in one change. `agents/dev.md → ## Code standards` — after `DEV-COMMENTS`:
```
- `DEV-NO-PRINT` — production code under `apps/**` logs through the module's `structlog` logger; `print()` is for scripts under `scripts/**` and tests only.
```
`agents/reviewer.md → ## Detection` — new block:
```
- `DEV-NO-PRINT`: `grep -rnE '^\s*print\(' apps/ --include='*.py'` — any hit outside `tests/` is a block.
```
Checked: scopes by glob ("production code" → `apps/**` with `tests/` carve-out); positive phrasing ("forbid print" → "logs through structlog; print is for scripts and tests").

## Followup flag
—
</example>
