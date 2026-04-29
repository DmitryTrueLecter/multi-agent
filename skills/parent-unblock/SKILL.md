---
name: parent-unblock
description: Check whether all children of a parent task are Done; if so, unblock the parent so team-lead can continue it. Idempotent — if any child is still open, makes no changes. Invocation: `/parent-unblock <PARENT-KEY>`.
---

# Parent unblock

Re-evaluate a parent task after one of its children reaches `Done`. If **every** child of `<PARENT-KEY>` is now in `Done`, transition the parent from `On Hold` to `To Do` and post a comment so the parent lands in the team-lead continuation queue.

This skill is the **single source of truth** for the recursive parent-unblock rule. It is invoked from:

- `reviewer` — at the end of an APPROVE handoff, with the parent key taken from the just-completed child's `parent` field.
- `team-lead` — when team-lead closes a decomposed task directly to `Done` (bypassing reviewer), with the parent key taken from the just-completed task's `parent` field.

If the just-completed task has no parent, do **not** invoke this skill — there is nothing to unblock.

## Usage

`/parent-unblock <PARENT-KEY>`

## Steps

1. Identify your calling context:
   - **From role** — your own role (`reviewer` or `team-lead`). Used for the comment prefix.
   - **Area** — your area (`reviewer` is per-area; `team-lead` has no area). Used for the comment prefix.
2. Search for non-Done children of `<PARENT-KEY>` via `jira_search`:

   ```
   parent = <PARENT-KEY> AND status != Done
   ```

3. If the search returns **any** results, make no changes and exit. Report to the caller: `parent <PARENT-KEY> still has open children, no action`.
4. If the search returns **zero** results, unblock the parent:
   - **Read** the parent issue with `jira_get_issue` to learn its current labels and status.
   - **Transition status** with `jira_transition_issue` to `To Do`. The expected current status of the parent is `On Hold`. If the transition is rejected (the parent is in some other status), stop and report — do **not** retry; investigation is needed.
   - **Update labels** with `jira_update_issue`. Pass the **full** label list:
     - preserve `area:<area>` and any other non-routing labels;
     - keep `agent:team-lead` (add it if not already present);
     - remove `needs-decision` if present.
   - **Post a comment** with `jira_add_comment`. The body must start with the standard role prefix:
     - From `reviewer`: `🤖 reviewer (<area>): all child tasks under <PARENT-KEY> are Done — parent unblocked for team-lead continuation.`
     - From `team-lead`: `🤖 team-lead: all child tasks under <PARENT-KEY> are Done — parent unblocked for team-lead continuation.`
5. Confirm to the caller: `parent <PARENT-KEY> unblocked → To Do, agent:team-lead`.

## Invariants

- The parent's `area:*` and other domain labels are never touched.
- `agent:team-lead` is the routing label on the unblocked parent.
- `needs-decision` is **never** present after this skill exits successfully — it is removed if it was set, untouched if it wasn't.
- The skill never transitions to any status other than `To Do`, and never to `Done`.
- The skill does no git operations. Branch state (merging children into the parent's branch) is the caller's responsibility and happens before this skill is invoked.

## Notes

- This is single-level. When the unblocked parent itself eventually reaches `Done` (through its own dev/qa/reviewer cycle, or via a direct team-lead → `Done`), the role responsible for that final transition is responsible for invoking this skill again with **the parent's own** parent key. Recursion happens naturally one step at a time.
- Idempotent on the "no changes" branch: invoking it again while children are still open is safe and a no-op.
- This skill is **not** a `/handoff` substitute. `/handoff team-lead` is for blocker escalation (`On Hold` + `needs-decision`), which is the wrong meaning here. Use `/parent-unblock` for the "all children done" case.
