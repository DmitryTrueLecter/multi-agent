---
name: sentinel-triage
description: "Sentinel triage procedure: process Sentinel-queue flags one by one — read the cited location, classify, report, then apply / route / resolve on the user's word. Invoked by the sentinel agent on `Mode: triage` or when the user asks to triage."
user-invocable: false
---

# Sentinel triage

Process the Sentinel flag queue: per flag, read the cited location, classify, present a finding; apply, route, or resolve only on the user's direction.

## Procedure

1. Prime. Read every `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/patterns/*.md` and `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/task-schema.md`. A flag that matches a pattern's signature cites the pattern instead of re-deriving the analysis.
2. List the queue: `${CLAUDE_PLUGIN_ROOT}/bin/dma board list --status <S> --label sentinel-flag`, `<S>` = display name of `sentinel_inbox` from `config.yml`. Empty → print `Sentinel queue empty.` and stop. Order oldest first unless the user named flags.
3. Per flag, in order:
   a. `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>`. `type` = the `flag-type:<t>` label; `where`, `reporter`, `originating`, `details` = the description fields.
   b. When `where` names an area, read `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/area.yml`, then every `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/solutions/*.md` whose IF-condition that area meets.
   c. Read `where` — that section plus the minimum adjacent context — and its consumer: the agent prompt that applies the fragment (`${CLAUDE_PLUGIN_ROOT}/agents/sentinel/area-config-schema.md → ## Field reference` names the reader per `area.yml` field; for a prompt section, the step that applies it). Confirm the defect is still present in the current file and in the code it governs. Read nothing beyond that.
   d. Type-specific reads:
      - `RULE-CONTRADICTION` → the paired enforcement: the detection block in `${CLAUDE_PLUGIN_ROOT}/agents/reviewer.md`, or the `review_checks` entry in `areas/<area>/area.yml`.
      - `ARCH-ROLE-GAP` / `ARCH-ROLE-OVERLAP` → the one or two agent files the flag implicates, plus `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/agent-roles.md`.
      - `ENV-FRICTION` → `${CLAUDE_PLUGIN_ROOT}/hooks/` and `${CLAUDE_PROJECT_DIR}/.claude/settings*.json` for the rule blocking the prescribed command.
      - A flag touching labels, statuses, or queues → `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/status-invariants.md`.
      - A flag questioning what a role may do — run tests, write outside its paths, decide product scope — → `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/agent-roles.md → ## Settled decisions` first; a flag that asks to reverse a settled decision is **not actionable** as a defect and goes to the user as a question.
   e. Classify:
      - **Confirmed defect** — the problem is systemic and still present. Derive the fix from the defect and from what the consumer does with the fragment across the plugin; the change the flag asks for is input, never the fix as written. State what changes in the consumer's behaviour.
      - **Obsolete** — the fragment was rewritten, the governed code removed, or the mechanism replaced. Cite what resolved it (file:line or commit).
      - **Duplicate** — another queued flag covers it. Cite its key.
      - **Not actionable** — no defect described, or `where` is wrong. Explain why.
   f. For a confirmed defect, draft the fix per the charter's `## Writing replacements` steps 1–3, then apply its checklist item by item: for each item, name the span in the draft that fails it and rewrite that span. Keep the items that changed the draft — they become the `**Checked:**` line.
4. Print the report in the format below — headings and field labels verbatim. Before printing, re-read the format against the draft.
5. Wait for the user. Per flag, on their word:
   - **apply** → `Write` the rewrite, then `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> done "applied: <one-line summary>"`.
   - **route** → `${CLAUDE_PLUGIN_ROOT}/bin/dma issue create task "<summary>" --labels agent:team-lead --description -` (lands in `to_do + agent:team-lead`, the coordination queue `/dma:run` walks first), then `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> done "routed via <new-KEY>"`. Route when the fix needs another role — architect consultation plus `Mode: structure`, area scaffolding, cross-area cleanup.
   - **resolve only** (obsolete / duplicate / not actionable) → `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> done "<reason>"`.
   - **silent, unclear, or deferred** → the flag stays in the queue.
6. Resolved flags stay in `done`; never delete one.

## Report format

```markdown
## Sentinel queue: <N> flag(s)

### 1. <KEY> — <TYPE>
Reporter: <role> (<area>)
Where: <file:section>
Originating task: <KEY or "—">

**Disposition:** confirmed defect | obsolete | duplicate of <KEY> | not actionable

**Finding:**
<one paragraph: the structural defect and the criterion that decides the next case>

**Fix:**
<before — the literal changed span, fenced>
<after — the fenced replacement; for a removed span the fence reads `(deleted — <where its action now lives>)`>
<one before/after pair per changed span, the sibling that absorbs a rule ID included>

**Checked:** <checklist items that changed the draft, each with its span — or `no changes`>

**Note:** <≤3 sentences; omit when nothing to add>

**Scope:** shared-plugin (cross-project: yes) | project-local

---
```

After the user's dispositions, one trailing line: `Resolved <N> flag(s) to done.`

<example>
## Sentinel queue: 2 flag(s)

### 1. PROJ-101 — RULE-CONTRADICTION
Reporter: team-lead (payments)
Where: `.claude/dma/areas/payments/area.yml` : `review_checks` → `PAY-RETRY-BACKOFF` + paired guideline
Originating task: PROJ-88

**Disposition:** confirmed defect

**Finding:**
The rule requires every outbound call to wrap itself in `RetryPolicy.exponential()`; PROJ-88 replaced that helper with a transport-level retry in `libs/net/client.py`, so the helper no longer exists and the rule's ENFORCEMENT grep returns nothing. A reviewer applying the rule literally would block the new transport. Criterion for the next case: retries live in the shared transport; a call site that adds its own retry loop is the violation.

**Fix:**
`review_checks` — before:
```
- "PAY-RETRY-BACKOFF: every outbound HTTP call wraps itself in `RetryPolicy.exponential()`. ENFORCEMENT: `grep -rnL 'RetryPolicy' apps/payments/clients/` — a client file without it is a violation."
```
`review_checks` — after:
```yaml
- "PAY-RETRY-BACKOFF: retries live in the shared transport (`libs/net/client.py`); a call site retries nothing itself. A `for`/`while` loop around an outbound call, or a `sleep(` between attempts, is a violation. ENFORCEMENT: `grep -rnE 'for attempt|while .*retry|time\\.sleep\\(' apps/payments/clients/` — any hit is a violation."
```
`guidelines` — before:
```
- Wrap outbound calls in `RetryPolicy.exponential()`; never call `httpx` directly.
```
`guidelines` — after:
```yaml
- Send outbound calls through `libs/net/client.py` and leave retries to it (PAY-RETRY-BACKOFF).
```

**Checked:** references (`RetryPolicy.exponential()` → `libs/net/client.py`, the helper no longer exists); thresholds ("retries responsibly" in the draft → the loop/sleep detection); voice (guideline draft opened "Retries are handled by…" → "Send … and leave …"); positive phrasing (guideline draft ended "never loop, never sleep between attempts" → dropped, the rule names the violations); one home (guideline draft repeated the rule's violation list → cites the rule ID and keeps only the action).

**Note:** `PAY-TIMEOUTS` cites `RetryPolicy` in its own text; it is not this flag's `where` — filed separately as PROJ-102.

**Scope:** project-local

---

### 2. PROJ-97 — ENV-FRICTION
Reporter: dev (payments)
Where: `hooks/bash_safety.py` : generated-files guard
Originating task: PROJ-90

**Disposition:** obsolete

**Finding:**
The guard blocked read-only `cat` of files under the generated-clients directory on a path-substring match. The current guard matches only creation verbs (`>`, `tee`, `touch`, `cp` into the directory); `cat`, `grep`, `sed -n` pass. Resolved by the guard rewrite that shipped with PROJ-95.

**Scope:** shared-plugin (cross-project: yes)

---
</example>
