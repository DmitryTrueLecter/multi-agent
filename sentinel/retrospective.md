# Retrospective mode — procedure

Epic-scoped lifecycle analysis. Run manually via `/dma:sentinel retrospective <EPIC-KEY>`. Detect recurring meta-problems from how one Epic actually played out; scope is the Epic and its children — do not audit the broader system here.

## Procedure

1. Fetch the Epic and every child via the tracker:
   - `/dma:task-read <EPIC-KEY>` — description, status, comments.
   - `/dma:issue-search parent:<EPIC-KEY>` — list of children.
   - `/dma:task-read <CHILD-KEY>` for each child.

2. Per child, extract from `/dma:task-read` output:
   - Count of `🤖 qa (<area>): handoff → dev` rejections.
   - Count of `🤖 reviewer (<area>): handoff → dev` rejections.
   - Whether the child ever sat in `on_hold` with `agent:team-lead` (look for `🤖 dev … handoff → team-lead`).
   - User-decline cycles (`🤖 user (decline) via PR …`).
   - Whether the child carries the `stale-merge` label.
   - `ARCH-EPIC-SYNC` drift handoffs (`🤖 dev … handoff → team-lead (ARCH-EPIC-SYNC drift)`).

3. Cross-reference the sentinel inbox archive: grep `${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/archive/*.md` for `originating_task: <CHILD-KEY>` in frontmatter. Catalog the flags fired during the Epic's lifetime.

4. Aggregate against the taxonomy:
   - Same rejection reason in ≥2 children → `PATTERN-REPEAT` candidate.
   - A process incident (drift handoff, partial-promote, stale-merge) with no documented recovery in the prompts → `PROMPT-INCOMPLETE`.
   - Repeated `on_hold` cycles converging on the same architectural question → `ARCH-ROLE-GAP`.
   - Reviewer-block citing a rule whose detection is absent from `reviewer.md` → `RULE-ORPHANED`.

5. Print the report.

## Report

```markdown
## Sentinel retrospective — <EPIC-KEY> "<Epic summary>"

**Children:** N (X done, Y in flight).
**Spec stability:** N edits to Epic description after first child created (or "none").

### Bounce profile

| Child | dev→qa | qa→dev | reviewer block | on_hold | user-decline | done |
|-------|--------|--------|----------------|---------|--------------|------|
| KEY-1 | 1 | 0 | 0 | 0 | 0 | yes |
| KEY-2 | 2 | 1 | 1 | 1 | 0 | yes |

### Recurring rejection reasons

1. **<short phrase>** — fired on KEY-X, KEY-Y. Rule: `<DEV-* / AREA-*>` or "no rule". `PATTERN-REPEAT` candidate.
2. ...

### Process incidents

- ARCH-EPIC-SYNC drift on KEY-X — resolved / open.
- Partial-promote state on parent Epic — resolved / open.
- (or "none").

### Sentinel flags filed during this Epic

- <archive filename> — <type> — one-line summary.

### Findings

#### 1. <title> `[<taxonomy-id>]`
...

### Knowledge base updates

New pattern entries to record.

### Recommended prompt changes

Ordered list. Each item names the file:section.
```

## Cross-mode contracts

- Classify findings against `agents/sentinel.md → ## Findings taxonomy`.
- Apply edits only after per-file user OK — `agents/sentinel.md → ## Edit authority`. The retrospective itself produces evidence, not prompt edits.
