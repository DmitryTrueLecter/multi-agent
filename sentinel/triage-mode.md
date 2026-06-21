# Triage mode — procedure

Process the Sentinel flag queue: per flag, read the cited location, classify, and present findings for the user to apply, route, or resolve.

## Procedure

1. List the queue: `/dma:issue-search status:<S> label:sentinel-flag`, where `<S>` is the display name of `sentinel_inbox` from `config.yml.tasks.workflow.statuses` (oldest first). Empty → report "Sentinel queue empty." and stop.
2. For each flag:
   a. Read the flag issue: `/dma:task-read <issue-key>`. Take `type` from the `flag-type:<t>` label and `where` / `reporter` / `originating` / `details` from the description fields.
   b. Read the cited `where` location. **Only** that section plus the minimum adjacent context needed to evaluate the defect. Do not sweep the system.
   c. Type-specific reads beyond `where`:
      - `RULE-CONTRADICTION` → also the paired enforcement (`agents/reviewer.md` detection block, or `areas/<area>/area.yml → review_checks` entry).
      - `ARCH-ROLE-GAP` / `ARCH-ROLE-OVERLAP` → the one or two agent files the flag implicates.
      - `ENV-FRICTION` → `${CLAUDE_PLUGIN_ROOT}/hooks/` and the project's `${CLAUDE_PROJECT_DIR}/.claude/settings*.json` for the rule blocking the prescribed command.
      - Others — just `where`.
   d. Classify:
      - **Confirmed defect** — produce a finding with the concrete fix. For prompt edits, the full rewritten paragraph.
      - **Duplicate** — another flag in the queue covers it. Cite the duplicate's issue key.
      - **Not actionable** — flag does not describe a defect, or `where` is wrong. Explain why.
3. Print the report (see `## Report format` below).
4. Wait for the user's response. Per flag, branch:
   - **OK to apply:** `Write` the rewrite, then resolve the flag: `/dma:handoff <issue-key> done "applied: <one-line summary>"`.
   - **OK to route via task:** call `/dma:issue-create Task "<summary>" labels:agent:team-lead description:<full finding + recommended steps>`. The task lands in `to_do + agent:team-lead`, picked up by `/dma:run` auto-mode bucket #2. Then resolve the flag: `/dma:handoff <issue-key> done "routed via <new-KEY>"`. Use when the fix needs another role's action — architect consultation + `Mode: structure` apply, area scaffolding, cross-area cleanup — not a prompt rewrite sentinel can do directly.
   - **OK to resolve only** (duplicate, not actionable): `/dma:handoff <issue-key> done "<reason>"`.
   - **Silent / unclear / deferred:** leave the flag in the queue until the user speaks.
5. Resolved flag issues stay in `done` — their history is the audit chain.

## Report format

```markdown
## Sentinel queue: <N> flag(s)

### 1. <issue-key> — <type>
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

Trailing line: `Resolved <N> flag(s) to done.`

## Cross-mode contracts

- Classify findings against `agents/sentinel.md → ## Findings taxonomy`.
- Compose `**Fix:**` blocks under `agents/sentinel.md → ## Writing replacements` — audit block first, fenced replacement second, in the same turn.
- Apply edits only after per-file user OK — `agents/sentinel.md → ## Edit authority`.
