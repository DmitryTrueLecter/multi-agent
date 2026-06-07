# Triage mode — procedure

Process the sentinel inbox: per flag, read the cited location, classify, and present findings for the user to apply, route, or archive.

## Procedure

1. List inbox: `ls ${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/*.md` (sorted, oldest first). Empty → report "Inbox empty." and stop.
2. For each flag:
   a. Read the flag file. Parse frontmatter (`type`, `reporter`, `where`, `created_at`, `originating_task`) and the `## Problem` / `## Details` body.
   b. Read the cited `where` location. **Only** that section plus the minimum adjacent context needed to evaluate the defect. Do not sweep the system.
   c. Type-specific reads beyond `where`:
      - `RULE-CONTRADICTION` → also the paired enforcement (`agents/reviewer.md` detection block, or `areas/<area>/area.yml → review_checks` entry).
      - `ARCH-ROLE-GAP` / `ARCH-ROLE-OVERLAP` → the one or two agent files the flag implicates.
      - `ENV-FRICTION` → `${CLAUDE_PLUGIN_ROOT}/hooks/` and the project's `${CLAUDE_PROJECT_DIR}/.claude/settings*.json` for the rule blocking the prescribed command.
      - Others — just `where`.
   d. Classify:
      - **Confirmed defect** — produce a finding with the concrete fix. For prompt edits, the full rewritten paragraph.
      - **Duplicate** — another flag earlier in this inbox covers it. Cite the duplicate's filename.
      - **Not actionable** — flag does not describe a defect, or `where` is wrong. Explain why.
3. Print the report (see `## Report format` below).
4. Wait for the user's response. Per flag, branch:
   - **OK to apply:** `Write` the rewrite, then `mv` the flag to `${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/archive/`.
   - **OK to route via task:** call `/dma:issue-create Task "<summary>" labels:agent:team-lead description:<full finding + recommended steps>`. The task lands in `to_do + agent:team-lead`, picked up by `/dma:run` auto-mode bucket #2. `mv` the flag to archive with a sidecar `<flag-filename>.disposition.txt` recording `routed via <ISSUE-KEY>`. Use when the fix needs another role's action — architect consultation + `Mode: structure` apply, area scaffolding, cross-area cleanup — not a prompt rewrite sentinel can do directly.
   - **OK to archive only** (duplicate, not actionable, deferred): `mv` to archive with a sidecar `<flag-filename>.disposition.txt` recording the reason.
   - **Silent / unclear:** leave the flag in the inbox until the user speaks.
5. Originals stay in archive — they are the audit chain.

## Report format

```markdown
## Inbox: <N> flag(s)

### 1. <flag-filename> — <type>
Reporter: <role> (<area>)
Where: <file:section>
Originating task: <KEY or "—">

**Disposition:** confirmed defect / duplicate of <other> / not actionable

**Finding:**
<one-paragraph description of the structural defect>

**Fix:**
<concrete change — for prompt edits, the rewritten paragraph in full>

**Scope:** shared-plugin (cross-project: yes/no) / project-local

---

### 2. ...
```

Trailing line: `Archived <N> flag(s) to ${CLAUDE_PROJECT_DIR}/.claude/sentinel-inbox/archive/.`

## Cross-mode contracts

- Classify findings against `agents/sentinel.md → ## Findings taxonomy`.
- Compose `**Fix:**` blocks under `agents/sentinel.md → ## Writing replacements` — audit block first, fenced replacement second, in the same turn.
- Apply edits only after per-file user OK — `agents/sentinel.md → ## Edit authority`.
