Procedure for team-lead epic close-out. Spawned with `Group close-out: <KEY>` (and a `Workspaces:` map). Read this after the spine in `agents/team-lead.md` — it inherits every rule there.

## Workspaces from spawn prompt (epic close-out)

When `/dma:run` spawns you for epic close-out (group issue in `code_review`), the spawn prompt carries `Workspaces: <area1>=<abs-path-1>;<area2>=<abs-path-2>;…`. Each path is a pre-created git worktree under the area-repo's `.worktrees/<EPIC-KEY>/`. **Use those paths instead of resolving `workspace.path` from `area.yml`** for the duration of this close-out — every `(cd <workspace.path> && …)` subshell in this prompt substitutes the matching worktree path for the area.

If an area appears in your close-out plan but is missing from the `Workspaces` map, fall back to the `area.yml.workspace.path` resolution and proceed without a worktree (single-runner mode). If you find no `Workspaces:` field at all (you were not spawned for close-out, or the orchestrator predates this contract), nothing changes.

After close-out completes and the epic transitions to `done`, `/dma:handoff <EPIC-KEY> done` cleans up the worktrees automatically (see `skills/handoff/SKILL.md → ## Worktree cleanup`).

## Closing Epics (Epic in Code Review with `agent:team-lead`)

When the reviewer closes the **last** Task of an Epic, it promotes the Epic to `Code Review` with `agent:team-lead` — that is your signal to do the final epic-level review and close it.

Search:

```
/dma:issue-search type:group status:"Code Review" label:agent:team-lead
```

For each such group issue:
1. **Claim it**: `/dma:issue-claim <EPIC-KEY>`. On failure (another runner claimed it first), skip. On success, use the returned data directly. (When launched via `/dma:run`, the claim is already done; use `/dma:task-read <EPIC-KEY>` to get the data.)
2. Read its full child list:
   ```
   /dma:issue-search parent:<EPIC-KEY>
   ```
3. Verify every child Task is in `Done`. If any child is not Done, the reviewer made a mistake — run `/dma:issue-comment <EPIC-KEY> <explanation>` to document the issue, then `/dma:issue-update-labels <EPIC-KEY> remove:agent:team-lead` to clear the team-lead marker (Epic stays in `Code Review` without an agent label — `/dma:pr-feedback` will re-add `agent:team-lead` once all children are Done), and stop.
4. Re-read the Epic description and recent comments. Check for any open follow-ups, deferred items, or "out of scope" notes that should become new tasks before the Epic closes:
   - Search comments and descriptions for `TODO`, `follow-up`, `deferred`, `out of scope`, etc.
   - Cross-check with the spec — anything the spec required that isn't covered by an existing Done child?
5. Present your assessment to the user:
   - Confirmation that all N children are Done.
   - List of any follow-ups you found (or "none found").
   - Recommendation: **close** the Epic, or **hold** it pending follow-up tasks.
6. **Wait for user approval.**
7. On approval to close:
   - **Integration-drift check (`ARCH-EPIC-SYNC` belt-and-suspenders) — run BEFORE any tests or PRs.** If devs honored `ARCH-EPIC-SYNC` at every claim, this check finds zero drift and is a no-op. A non-zero rev-count here means dev-side sync did not happen for at least one claim during the Epic's life — log this as a process incident in the closing comment before resolving, so the gap is visible. Agent-reported "tests passed" comments in task issues are from when each task was authored; they say nothing about whether the epic branch still integrates cleanly with the *current* `<workspace.dev_branch>`. For each affected workspace, in a subshell:
     ```
     ( cd <workspace.path> && git fetch <workspace.remote> <workspace.dev_branch> )
     ( cd <workspace.path> && git merge-base <vcs.branch_prefix><EPIC-KEY> <workspace.remote>/<workspace.dev_branch> )
     ( cd <workspace.path> && git rev-list <merge-base>..<workspace.remote>/<workspace.dev_branch> --count )
     ```
     If the third command returns a non-zero count, `<workspace.remote>/<workspace.dev_branch>` has advanced past the merge-base since the epic branch was cut. Classify the drift before acting — path-overlapping drift carries semantic-conflict risk; path-disjoint drift is a non-event that plain merge handles at PR time:
     ```
     ( cd <workspace.path> && git diff --name-only <merge-base>..<workspace.remote>/<workspace.dev_branch> )
     ( cd <workspace.path> && git diff --name-only <merge-base>..<vcs.branch_prefix><EPIC-KEY> )
     ```
     - Lists have no intersection: log `/dma:issue-comment <EPIC-KEY> "🤖 team-lead: integration-drift check: N-commit drift on <workspace.dev_branch>, path-disjoint vs epic branch. No rebase required."` and proceed to the next bullet.
     - Lists intersect: rewriting a shared epic branch is a unilateral destructive decision — escalate first. Post the rebase plan and overlapping paths as a `🤖 team-lead:` comment on the Epic, surface to user, and wait for confirmation. On approval: `( cd <workspace.path> && git checkout <vcs.branch_prefix><EPIC-KEY> && git rebase <workspace.remote>/<workspace.dev_branch> )`. If rebase conflicts arise that you cannot resolve mechanically (any semantic conflict touching code from an affected dev agent's task), STOP the close-out, post a `🤖 team-lead:` comment listing the conflicting paths, and coordinate with the affected dev agent(s). Do not force-push or merge-resolve unilaterally.
     - After a clean rebase, force-push: `( cd <workspace.path> && git push --force-with-lease <workspace.remote> <vcs.branch_prefix><EPIC-KEY> )`. If a project safety hook refuses the force-push or `git reset --hard`, surface the blocked command to user; the non-destructive rollback primitive that re-points the local branch at its remote tip is `( cd <workspace.path> && git fetch <workspace.remote> <vcs.branch_prefix><EPIC-KEY> && git branch -f <vcs.branch_prefix><EPIC-KEY> <workspace.remote>/<vcs.branch_prefix><EPIC-KEY> )`.
     - Re-run the area test suites against the rebased state (next bullet) — the prior agent-reported passes are now invalidated.

     Only when every affected workspace shows a zero count, has path-disjoint drift logged, or has been rebased to a clean state with the test gate re-passed, may you proceed.
   - **Independent build + test re-run — hard gate against broken integration reaching CI.** Agent-reported test counts in per-task Jira comments are **input signals only, not ground truth**. You re-run from scratch on the merged epic-branch state, per area:
     - **Build/typecheck gate**: for each `area:*` label that appeared on any child Task of this Epic, read its `build_command` from `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/area.yml`. If defined, run `( cd <workspace.path> && <build_command> )`. This catches breakages that `test_command` cannot — e.g. TypeScript areas using `ts-jest` with `isolatedModules: true, diagnostics: false` (Jest does not perform full `tsc`; the build does). For areas without a `build_command` but with a Python entrypoint, run `( cd <workspace.path> && <runtime.python> -c "import apps.<area>.main" )` as a minimal import smoke (substitute the area's actual entrypoint module if it differs); the most common production-breaking regression caught by import-smoke is an undeclared dependency or a stale aliased import that the per-task test suite happened not to exercise. Areas with neither `build_command` nor a Python entrypoint skip this bullet.
     - **Full test suite per area**: for each `area:*` touched by the Epic, read its `test_command` from `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/area.yml` and run it in the area's workspace via subshell: `( cd <workspace.path> && <test_command> )`.

     On any failure (build/typecheck gate, import smoke, or tests) for any area: do **not** open a PR; run `/dma:issue-comment <EPIC-KEY> <failure-details>` (start with `🤖 team-lead:`), leave Epic in `In Progress` with `agent:team-lead`; surface to user and stop.
   - **Open a PR for each affected workspace**: `<vcs.branch_prefix><EPIC-KEY>` → `<workspace.dev_branch>`. Direct push to `<workspace.dev_branch>` is blocked by `bash_safety.py` — integration always goes through PR review.

     For each workspace, call:
     ```
     /dma:pr-open <vcs.branch_prefix><EPIC-KEY> <workspace.dev_branch> "<EPIC-KEY> <Epic summary>" workspace-path:<workspace.path> remote:<workspace.remote> description:<delivered-summary>
     ```

     Capture the PR URL from the skill's response. If `/dma:pr-open` returns an error for any workspace, do **not** proceed: run `/dma:issue-comment <EPIC-KEY> <error-details>`, leave the Epic in `In Progress` with `agent:team-lead`, and stop.
   - Run `/dma:handoff <EPIC-KEY> done <closing-comment>` where the closing comment starts with `🤖 team-lead:`, summarizes what was delivered, and includes the PR URL(s). The skill removes `agent:team-lead`, transitions the Epic to `Done`, and posts the comment.
   - The PR(s) merge to `<workspace.dev_branch>` outside the agent flow (user / CI). `Done` here means "the agent loop is closed", not "shipped to dev".
8. On hold (follow-ups required):
   - Create the follow-up Tasks (linked to the Epic) per the normal task-creation flow using `/dma:issue-create`.
   - Run `/dma:issue-update-labels <EPIC-KEY> remove:agent:team-lead` to remove the team-lead marker while leaving the Epic in `In Progress` (children are actively in their queues — the Epic is "in flight" again).
   - The `/dma:pr-feedback` pre-flight will re-promote the Epic to `Code Review` + `agent:team-lead` when the last follow-up child is merged.
