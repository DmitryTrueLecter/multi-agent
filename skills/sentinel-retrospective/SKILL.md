---
name: sentinel-retrospective
description: "Sentinel retrospective procedure: reconstruct how one Epic's children moved through the pipeline — bounce profile, recurring rejections, process incidents, flags filed — and aggregate into taxonomy findings. Invoked by the sentinel agent on `Mode: retrospective. Epic: <KEY>`."
user-invocable: false
---

# Sentinel retrospective

Detect recurring meta-problems from how one Epic actually played out. Scope is the Epic and its children; the broader system belongs to full-audit. Run manually via `/dma:sentinel retrospective <EPIC-KEY>`. The output is evidence, never a prompt edit.

## Procedure

1. Prime: read every `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/patterns/*.md` and `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/task-schema.md` (the comment prefixes below are defined there).
2. Fetch the Epic and its children:
   - `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <EPIC-KEY>` — description, status, comments;
   - `${CLAUDE_PLUGIN_ROOT}/bin/dma board list --parent <EPIC-KEY>` — the children;
   - `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <CHILD-KEY>` for each child.
3. Per child, extract from its comments:
   - count of `🤖 qa (<area>): handoff → dev`;
   - count of `🤖 reviewer (<area>): handoff → dev`;
   - `on_hold` episodes (`🤖 dev … handoff → team-lead`);
   - user-decline cycles (`🤖 user (decline) via PR …`);
   - the `stale-merge` label;
   - `ARCH-EPIC-SYNC` drift handoffs (`🤖 dev … handoff → team-lead (ARCH-EPIC-SYNC drift)`).
4. Cross-reference flags: `${CLAUDE_PLUGIN_ROOT}/bin/dma board list --label sentinel-flag`, then read each flag's `Originating` field; keep those originating in this Epic's children.
5. Aggregate against the charter's `## Findings taxonomy`:
   - the same rejection reason in ≥2 children → `PATTERN-REPEAT` candidate;
   - a process incident (drift handoff, partial promote, stale-merge) with no documented recovery in the prompts → `PROMPT-INCOMPLETE`;
   - repeated `on_hold` cycles converging on one architectural question → `ARCH-ROLE-GAP`;
   - a reviewer block citing a rule with no detection in `reviewer.md` → `RULE-ORPHANED`.
6. Print the report.

## Report format

```markdown
## Sentinel retrospective — <EPIC-KEY> "<Epic summary>"

**Children:** N (X done, Y in flight).
**Spec stability:** N edits to the Epic description after the first child was created — or "none".

### Bounce profile

| Child | dev→qa | qa→dev | reviewer block | on_hold | user-decline | done |
|-------|--------|--------|----------------|---------|--------------|------|
| KEY-1 | 1 | 0 | 0 | 0 | 0 | yes |

### Recurring rejection reasons
1. **<short phrase>** — fired on KEY-X, KEY-Y. Rule: `<DEV-* | AREA-*>` or "no rule". `PATTERN-REPEAT` candidate.

### Process incidents
- ARCH-EPIC-SYNC drift on KEY-X — resolved | open.
- (or "none")

### Sentinel flags filed during this Epic
- <KEY> — <flag-type> — one-line summary.

### Findings
#### 1. <title> `[<taxonomy-id>]`
<one paragraph>

### Knowledge base updates
New pattern entries to record — or "none".

### Recommended prompt changes
Ordered; each item names file:section.
```
