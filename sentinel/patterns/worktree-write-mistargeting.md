# WORKTREE-WRITE-MISTARGETING

## Signature

An agent runs inside a per-task git worktree (`.worktrees/<KEY>`) handed to it as `<abs-workspace-path>`, but its file edits or commits land on the **parent checkout** at the project root instead. The root cause is a path-construction gap in the role prompt, not agent carelessness: absolute-path tools (`Read` / `Edit` / `Write`) require an absolute prefix, the prompt hands the agent `${CLAUDE_PROJECT_DIR}` for `.claude/*` reads, and no rule maps task-tree files to the `<abs-workspace-path>` prefix. The agent generalizes the only absolute prefix it was given, builds `${CLAUDE_PROJECT_DIR}/...` targets, and writes to the parent checkout — which typically sits on an unrelated branch. A blanket "paths are always project-relative; no absolute paths" rule compounds it: it is unfollowable for tools that demand absolute paths, so the agent ignores it and falls back to the project root.

## Observed instances

- **dev/qa/sentinel worktree mis-targeting (2026-05-27, AITSAI-216).** Recurred 4× in one session (sentinel/AITSAI-213, dev/AITSAI-209, dev/AITSAI-212, dev/AITSAI-216): edits/commits landed on the main checkout (on branch `ai/AITSAI-207`); AITSAI-216 recovery needed `git reset --soft HEAD^` on the branch the team-lead session occupied. All self-recovered, no work escaped. Fix: added an explicit absolute-path prefix rule (`<abs-workspace-path>` for task-tree files, `${CLAUDE_PROJECT_DIR}` only for `.claude/*`) to the Workspace section of `agents/dev.md`, `qa.md`, `reviewer.md`, and step 5 of `sentinel/task-mode.md`; replaced the false "always project-relative; no absolute paths" bullet with a Bash-scoped rule that defers to Workspace.

## Triage rule

When an agent reports editing or committing into the wrong checkout (main repo instead of its worktree, or vice versa for task-mode): check whether the role prompt gives an explicit absolute-path prefix rule mapping task-tree files to `<abs-workspace-path>`. If the only absolute prefix the prompt names is `${CLAUDE_PROJECT_DIR}` (for config reads), that gap is the cause. Recommend a prefix rule in the Workspace section, and scope any "project-relative paths" bullet to `Bash` only — absolute-path tools cannot honor it. A confinement hook (`PreToolUse` on `Edit`/`Write` refusing targets outside the worktree cwd) is the defense-in-depth complement to the prompt fix.

## Untriggered candidates

Other shapes likely to fit this pattern when they surface:

- Agent `cd`s correctly into the worktree but uses `git -C <project-root>` or an absolute `git --git-dir` that re-targets the parent repo.
- task-mode (inverse direction): sentinel edits `.claude/areas/<area>/**` but writes to `${CLAUDE_PROJECT_DIR}/.claude/...` rather than the worktree copy, so the change never reaches the PR branch.
- Any future agent role that gains `Edit`/`Write` authority without inheriting the Workspace prefix rule.
