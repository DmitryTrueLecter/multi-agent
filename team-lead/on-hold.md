Procedure for tasks parked for a decision. Spawned with `On Hold task: <KEY>`. Read this after the spine in `agents/team-lead.md` — it inherits every rule there.

## Handling On Hold tasks

**Always check On Hold tasks first** when invoked:

```
/dma:issue-search status:"On Hold" label:agent:team-lead
```

For each On Hold task:
1. **Claim the task**: `/dma:issue-claim <KEY>`. On failure (another runner claimed it first), skip and try the next. On success, the skill returns the full task data — use it directly as step 2. (When launched as a subagent via `/dma:run`, the claim is already done; use `/dma:task-read <KEY>` to get the data.)
2. Read the issue and its comments (from `/dma:issue-claim` response, or `/dma:task-read <KEY>` if pre-claimed) to understand what the dev flagged.
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

     Link each triage task `Blocks` the on-hold task. Return the on-hold task via `/dma:handoff <KEY> dev` only after the triage lands — the dev's re-run baseline must include the triage outcomes.
5. Read the spec and relevant architecture docs to verify.
6. Present your analysis and proposed action to the user:
   - What the dev flagged
   - What you found after reviewing the full context
   - Your recommendation (fix spec, update existing task, create new task, tell dev to proceed differently)
7. **Wait for user approval before making any changes.**
8. After approval, execute: use `/dma:handoff <KEY> <role> <comment>` to route the task to the next role. The skill removes `agent:team-lead` + `needs-decision`, sets the appropriate `agent:` label, and transitions status:
   - back to dev → `/dma:handoff <KEY> dev <explanation>`
   - to qa → `/dma:handoff <KEY> qa <explanation>`
   - to reviewer → `/dma:handoff <KEY> reviewer <explanation>`
   - to devops → `/dma:handoff <KEY> devops <explanation>` (re-routing an infra-flavored task that landed in the wrong queue)

## Handling spec-conflict handoffs

When qa or reviewer hands off with `spec-conflict:` prefix:

1. Read the prior verdict they cite and the current spec text they quote.
2. Classify the conflict dimension:
   - **Runtime behavior** (API shape, contract details): rewrite the description to match live code. Cite the source — branch/SHA/file:line.
   - **Engineering correctness** (re-entrancy, race conditions, error handling, type safety): rewrite the description to require the engineering-correct pattern, naming why (the rule ID or the failure mode).
   - **Scope** (the spec asked for X, neither role disputed it, but they disagree on how X must look): present to user. Do not unilaterally rewrite scope.
3. After rewriting, return the task to the role that handed off, *not* to dev: `/dma:handoff <ISSUE-KEY> <originating-role> "spec reconciled — <one-line>. Re-evaluate against current description."` The originating role's next verdict now runs against the corrected spec.
4. Bounce counter does NOT reset against dev. The dev's pre-handoff diff stands; this round is a process correction, not a re-implementation.
