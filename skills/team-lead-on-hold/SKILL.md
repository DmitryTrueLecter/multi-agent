---
name: team-lead-on-hold
description: "Team-lead On Hold procedure: triage a task parked for a decision — read the whole epic, find the root cause (spec gap, misunderstanding, ARCH-EPIC-SYNC drift, pre-existing test rot, spec conflict), present the analysis, act only on the user's approval. Invoked by the team-lead agent on `On Hold task: <KEY>`."
user-invocable: false
---

# Team-lead: On Hold

Triage one task a role parked for a decision: understand the whole epic, name the root cause, propose one action, and wait for the user before touching the tracker. Spawned by `/dma:run` with `On Hold task: <KEY>`; every rule of `agents/team-lead.md` applies here.

## Handling On Hold tasks

**Always check On Hold tasks first** when invoked:

```
${CLAUDE_PLUGIN_ROOT}/bin/dma board list --status "On Hold" --label agent:team-lead
```

For each On Hold task:
1. **Claim the task**: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim <KEY>`. On failure (another runner claimed it first), skip and try the next. On success, the skill returns the full task data — use it directly as step 2. (When launched as a subagent via `/dma:run`, the claim is already done; use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>` to get the data.)
2. Read the issue and its comments (from `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim` response, or `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>` if pre-claimed) to understand what the dev flagged.
3. **Read the entire epic** — all tasks, their descriptions, statuses, dependencies, and comments. Understand the full picture before reacting.
4. **Investigate the root cause.** Do NOT blindly create a task from the dev's comment. Ask yourself:
   - Is this already covered by another task in the epic?
   - Is the spec wrong or incomplete?
   - Did the dev misunderstand the requirement?
   - Is this a real gap that needs new work?
   - **Is this an `ARCH-EPIC-SYNC` drift handoff?** Look for `🤖 dev (<area>): handoff → team-lead (ARCH-EPIC-SYNC drift)` as the most recent dev comment. If yes: create a new Task `<EPIC-KEY>: reconcile <dev_branch> drift into epic branch` in the affected area, label `area:<area> agent:dev`, link `Blocks` the on-hold task, description names the conflicting files copied from the dev's comment and the two SHAs being merged. Once the reconcile task reaches Done, return the original task to `To Do` + `agent:dev` so the dev re-runs step 2 (which will now find the epic branch current). Do not skip this routing — sending the dev back to the same conflict produces a bounce loop on the original task.
   - **Is this a pre-existing test-rot handoff?** Look for a `🤖 dev (<area>): handoff → team-lead` comment listing failing test IDs and a base SHA, filed because the suite is red on tests the dev's diff did not introduce. If yes: read each listed test against the current code state and pick one outcome per test (or per group sharing a failure mode):
     - **Fix** — the symbols and contracts the test references still exist; only the assertions or expected shapes drifted. File a task to update the test.
     - **Delete** — the tested behavior is gone for good (module removed, v1 schema replaced by v2 with no v1 path). File a task to remove the test.
     - **Temporarily disable** — the contract is in flux and the test will be revived after a known follow-up (v1 tests during a v1→v2 migration with a planned port). File a task to add the language-appropriate skip marker with the tracking-issue ID in the reason field.

     Link each triage task `Blocks` the on-hold task. Return the on-hold task via `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> dev` only after the triage lands — the dev's re-run baseline must include the triage outcomes.
5. Read the spec and relevant architecture docs to verify.
6. Present your analysis to the user in the format under `## Analysis format` below.
7. **Wait for user approval before making any changes.** Nothing is created, transitioned, or commented until the user says so.
8. After approval, execute: use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> <role> <comment>` to route the task to the next role. The skill removes `agent:team-lead` + `needs-decision`, sets the appropriate `agent:` label, and transitions status:
   - back to dev → `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> dev <explanation>`
   - to qa → `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> qa <explanation>`
   - to reviewer → `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> reviewer <explanation>`
   - to devops → `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> devops <explanation>` (re-routing an infra-flavored task that landed in the wrong queue)

## Handling spec-conflict handoffs

When qa or reviewer hands off with `spec-conflict:` prefix:

1. Read the prior verdict they cite and the current spec text they quote.
2. Classify the conflict dimension:
   - **Runtime behavior** (API shape, contract details): rewrite the description to match live code. Cite the source — branch/SHA/file:line.
   - **Engineering correctness** (re-entrancy, race conditions, error handling, type safety): rewrite the description to require the engineering-correct pattern, naming why (the rule ID or the failure mode).
   - **Scope** (the spec asked for X, neither role disputed it, but they disagree on how X must look): a product question — what the user should see or get — goes to the analyst through `agents/team-lead.md → ## Requirements objection`; an engineering one is presented to the user. Do not unilaterally rewrite scope.
3. After rewriting, return the task to the role that handed off, *not* to dev: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <ISSUE-KEY> <originating-role> "spec reconciled — <one-line>. Re-evaluate against current description."` The originating role's next verdict now runs against the corrected spec.
4. Bounce counter does NOT reset against dev. The dev's pre-handoff diff stands; this round is a process correction, not a re-implementation.

## Analysis format

```markdown
## On Hold: <KEY> — <task summary>

**Flagged by:** <role> — <one line quoting what they flagged>
**Kind:** spec gap | misunderstanding | already covered by <KEY> | ARCH-EPIC-SYNC drift | pre-existing test rot | spec conflict | real gap

**What I found:**
<one paragraph: the evidence from the epic, the code, the comments — file:line, SHAs, test IDs where they exist>

**Proposed action:**
<one action: the handoff target, or the task(s) to create — summary, labels, `Blocks` links, and the description text with every file, SHA, and test ID written out, never "the two files" — or the spec section to rewrite; and what the dev does next>

Awaiting your approval.
```

<example>
## On Hold: PROJ-212 — Add retry endpoint for failed exports

**Flagged by:** dev — "suite red on base: 3 failures in `apps/exports/tests/test_legacy_csv.py` not touched by my diff (base `a1b2c3d`)"
**Kind:** pre-existing test rot

**What I found:**
The three failing tests assert the v1 CSV header order that PROJ-198 (merged 2026-08-30, epic PROJ-190) replaced with the v2 header; no v1 path remains in `apps/exports/csv.py`. The dev's diff touches `router.py` and `queue.py` only, and the same three tests fail on the base SHA the dev cited. This is not covered by any open task in PROJ-190 or PROJ-200.

**Proposed action:**
Create `PROJ-190: remove v1 CSV header tests superseded by v2` (`area:exports`, `agent:dev`, description names the three test IDs and the v2 commit) and link it `Blocks` PROJ-212. Return PROJ-212 to dev only after that task lands, so the dev's re-run baseline is green.

Awaiting your approval.
</example>
