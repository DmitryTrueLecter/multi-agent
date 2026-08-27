#!/usr/bin/env bash
# Task-branch setup for dev / qa / reviewer. Mirrors dev.md "Task workflow" step 2.
#
#   task-branch.sh dev-start <workspace> <remote> <dev_branch> <prefix> <ISSUE-KEY> [EPIC-KEY]
#   task-branch.sh checkout  <workspace> <remote> <dev_branch> <prefix> <ISSUE-KEY> [EPIC-KEY]
#
# Exit codes:
#   0   ok
#   1   git error
#   10  epic branch missing on remote        (dev.md 2a)
#   11  ARCH-EPIC-SYNC conflict, aborted     (dev.md 2c)
#   13  task branch or base missing on remote (qa.md / reviewer.md "Ref absent")

set -euo pipefail

command=$1
workspace=$2
remote=$3
dev_branch=$4
prefix=$5
issue=$6
epic=${7:-}

task_branch="$prefix$issue"

if [ -n "$epic" ]; then
    base="$prefix$epic"
else
    base="$dev_branch"
fi

cd "$workspace"
git fetch "$remote"

# ---------------------------------------------------------------- dev-start
if [ "$command" = "dev-start" ]; then

    # Re-run: the task branch already exists on the remote.
    # Continue from the previous attempt, do not recreate, do not lose commits.
    if git ls-remote --exit-code --heads "$remote" "$task_branch" >/dev/null; then
        if git show-ref --verify --quiet "refs/heads/$task_branch"; then
            git checkout "$task_branch"
        else
            git checkout -b "$task_branch" --track "$remote/$task_branch"
        fi
        git pull --no-rebase "$remote" "$task_branch"
        echo "MODE=rerun"
        echo "BASE=$base"
        git log --oneline "$remote/$base..HEAD"
        exit 0
    fi

    # Fresh task.
    if [ -n "$epic" ]; then

        # 2a. The epic branch must exist on the remote. Never fall back to dev_branch.
        if ! git ls-remote --exit-code --heads "$remote" "$base" >/dev/null; then
            echo "EPIC_MISSING $base on $remote"
            exit 10
        fi

        # 2b. ARCH-EPIC-SYNC: merge dev_branch into the epic branch and push it.
        # Done on a detached HEAD at the remote epic tip: the epic branch may be
        # checked out in another worktree (main repo, team-lead close-out), and
        # "git checkout <epic>" would fail with "already used by worktree".
        git checkout --detach "$remote/$base"

        if ! git merge --no-edit "$remote/$dev_branch"; then
            # 2c. Conflict: abort, report, do not resolve, do not push.
            conflicted_files=$(git diff --name-only --diff-filter=U)
            git merge --abort
            if [ -z "$conflicted_files" ]; then
                echo "merge failed without content conflicts (see git output above)" >&2
                exit 1
            fi
            echo "SYNC_CONFLICT"
            echo "dev_branch SHA tried: $(git rev-parse "$remote/$dev_branch")"
            echo "Conflicted files:"
            echo "$conflicted_files"
            exit 11
        fi

        git push "$remote" "HEAD:$base"
    fi

    # 2d. Cut the task branch from the remote base ref.
    git checkout -b "$task_branch" --no-track "$remote/$base"
    echo "MODE=fresh"
    echo "BASE=$base"
    exit 0
fi

# ---------------------------------------------------------------- checkout
if [ "$command" = "checkout" ]; then

    # Base must be on the remote; the task branch may be local-only (dev committed
    # but did not push) — same as the old "git checkout <task branch>" allowed.
    if ! git ls-remote --exit-code --heads "$remote" "$base" >/dev/null; then
        echo "REF_ABSENT $base on $remote"
        exit 13
    fi

    if git show-ref --verify --quiet "refs/heads/$task_branch"; then
        git checkout "$task_branch"
    elif git ls-remote --exit-code --heads "$remote" "$task_branch" >/dev/null; then
        git checkout -b "$task_branch" --track "$remote/$task_branch"
    else
        echo "REF_ABSENT $task_branch (not local, not on $remote)"
        exit 13
    fi
    if git ls-remote --exit-code --heads "$remote" "$task_branch" >/dev/null; then
        git pull --no-rebase "$remote" "$task_branch"
    fi
    echo "BASE=$base"
    git diff --stat "$remote/$base...HEAD"
    exit 0
fi

echo "usage: $0 <dev-start|checkout> <workspace> <remote> <dev_branch> <prefix> <ISSUE-KEY> [EPIC-KEY]" >&2
exit 1
