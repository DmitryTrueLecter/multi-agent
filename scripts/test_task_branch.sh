#!/usr/bin/env bash
# Tests for task-branch.sh. Creates a throwaway bare "remote" and a few clones,
# runs the script against them, checks exit codes and resulting git state.
#
#   bash scripts/test_task_branch.sh
#
# Every check is one line: "check <description> <shell test...>".

set -uo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/task-branch.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
remote="$tmp/remote.git"
failed=0

# No commit signing / no user prompts inside the fixture or inside the script under test.
export GIT_CONFIG_COUNT=4
export GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false
export GIT_CONFIG_KEY_1=user.email     GIT_CONFIG_VALUE_1=test@test
export GIT_CONFIG_KEY_2=user.name      GIT_CONFIG_VALUE_2=test
export GIT_CONFIG_KEY_3=init.defaultBranch GIT_CONFIG_VALUE_3=dev

check() {                                   # check "<what>" <command...>
    local what=$1; shift
    if "$@" >/dev/null 2>&1; then
        echo "  ok    $what"
    else
        echo "  FAIL  $what"
        failed=1
    fi
}

# "seed" is where we push branches to the remote to set up each scenario.
# "commit_to <clone> <branch> <file>" adds a commit on <branch> in <clone> and pushes it.
commit_to() {
    local clone=$1 branch=$2 file=$3
    ( cd "$clone" && git checkout -q "$branch" && echo "$file" > "$file" && git add "$file" \
        && git commit -q -m "$file" && git push -q origin "$branch" )
}

# "fresh_worktree <name>" = a clone detached at origin/dev, like /dma:run creates.
fresh_worktree() {
    rm -rf "$tmp/$1"
    git clone -q "$remote" "$tmp/$1"
    ( cd "$tmp/$1" && git checkout -q --detach origin/dev )
}

# --- remote with a "dev" branch
git init -q --bare "$remote"
git clone -q "$remote" "$tmp/seed" 2>/dev/null
# first commit by hand: in an empty repo "dev" is unborn, commit_to's checkout would fail
( cd "$tmp/seed" && git checkout -q -b dev && echo base.txt > base.txt && git add base.txt \
    && git commit -q -m base.txt && git push -q origin dev )

echo "fresh standalone task: cut ai/T-1 from origin/dev"
fresh_worktree ws1
bash "$script" dev-start "$tmp/ws1" origin dev ai/ T-1 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "prints MODE=fresh"          grep -q "MODE=fresh" "$tmp/out"
check "on branch ai/T-1"           test "$(git -C "$tmp/ws1" rev-parse --abbrev-ref HEAD)" = ai/T-1
check "has base.txt from dev"      test -f "$tmp/ws1/base.txt"

echo "re-run: ai/T-1 already on remote — checkout + pull, keep commits"
commit_to "$tmp/ws1" ai/T-1 work1.txt
fresh_worktree ws2
bash "$script" dev-start "$tmp/ws2" origin dev ai/ T-1 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "prints MODE=rerun"          grep -q "MODE=rerun" "$tmp/out"
check "lists previous commit"      grep -q "work1.txt" "$tmp/out"
check "has work1.txt"              test -f "$tmp/ws2/work1.txt"

echo "re-run again: local ai/T-1 exists but remote moved ahead — must pull"
commit_to "$tmp/ws1" ai/T-1 work2.txt
bash "$script" dev-start "$tmp/ws2" origin dev ai/ T-1 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "has work2.txt after pull"   test -f "$tmp/ws2/work2.txt"

echo "qa/reviewer checkout of ai/T-1"
fresh_worktree ws3
bash "$script" checkout "$tmp/ws3" origin dev ai/ T-1 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "on branch ai/T-1"           test "$(git -C "$tmp/ws3" rev-parse --abbrev-ref HEAD)" = ai/T-1
check "has work2.txt"              test -f "$tmp/ws3/work2.txt"

echo "checkout of missing task branch → exit 13"
bash "$script" checkout "$tmp/ws3" origin dev ai/ T-404 >"$tmp/out" 2>&1; rc=$?
check "exit 13"                    test "$rc" = 13
check "prints REF_ABSENT ai/T-404" grep -q "REF_ABSENT ai/T-404" "$tmp/out"

echo "checkout with missing base branch → exit 13"
bash "$script" checkout "$tmp/ws3" origin no-such-branch ai/ T-1 >"$tmp/out" 2>&1; rc=$?
check "exit 13"                    test "$rc" = 13
check "prints REF_ABSENT no-such-branch" grep -q "REF_ABSENT no-such-branch" "$tmp/out"

echo "epic task, epic branch missing on remote → exit 10, nothing cut"
fresh_worktree ws4
bash "$script" dev-start "$tmp/ws4" origin dev ai/ T-2 E-1 >"$tmp/out" 2>&1; rc=$?
check "exit 10"                    test "$rc" = 10
check "prints EPIC_MISSING ai/E-1" grep -q "EPIC_MISSING ai/E-1" "$tmp/out"
check "still detached (no branch)" test "$(git -C "$tmp/ws4" rev-parse --abbrev-ref HEAD)" = HEAD

echo "epic task, epic present, dev moved ahead → sync dev into epic, push, cut from epic"
( cd "$tmp/seed" && git checkout -q -b ai/E-1 dev )
commit_to "$tmp/seed" ai/E-1 epic.txt
commit_to "$tmp/seed" dev newer-dev.txt
fresh_worktree ws5
bash "$script" dev-start "$tmp/ws5" origin dev ai/ T-2 E-1 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "prints BASE=ai/E-1"         grep -q "BASE=ai/E-1" "$tmp/out"
check "on branch ai/T-2"           test "$(git -C "$tmp/ws5" rev-parse --abbrev-ref HEAD)" = ai/T-2
check "has epic.txt (cut from epic)"        test -f "$tmp/ws5/epic.txt"
check "has newer-dev.txt (dev synced in)"   test -f "$tmp/ws5/newer-dev.txt"
( cd "$tmp/seed" && git fetch -q origin )
check "remote ai/E-1 contains dev"  git -C "$tmp/seed" merge-base --is-ancestor origin/dev origin/ai/E-1

echo "epic task, epic branch checked out in the main repo (as in a worktree flow) → sync still works"
( cd "$tmp/seed" && git checkout -q ai/E-1 )
git -C "$tmp/seed" worktree add -q --detach "$tmp/seed/.worktrees/T-4" origin/dev
bash "$script" dev-start "$tmp/seed/.worktrees/T-4" origin dev ai/ T-4 E-1 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "on branch ai/T-4"           test "$(git -C "$tmp/seed/.worktrees/T-4" rev-parse --abbrev-ref HEAD)" = ai/T-4
check "has newer-dev.txt"          test -f "$tmp/seed/.worktrees/T-4/newer-dev.txt"
( cd "$tmp/seed" && git checkout -q dev )

echo "qa checkout of a local-only task branch (dev did not push) → allowed, like before"
( cd "$tmp/seed" && git checkout -q -b ai/T-5 dev && echo local > local.txt && git add local.txt && git commit -q -m local && git checkout -q dev )
git -C "$tmp/seed" worktree add -q --detach "$tmp/seed/.worktrees/T-5" origin/dev
bash "$script" checkout "$tmp/seed/.worktrees/T-5" origin dev ai/ T-5 >"$tmp/out" 2>&1; rc=$?
check "exit 0"                     test "$rc" = 0
check "on branch ai/T-5"           test "$(git -C "$tmp/seed/.worktrees/T-5" rev-parse --abbrev-ref HEAD)" = ai/T-5
check "has local.txt"              test -f "$tmp/seed/.worktrees/T-5/local.txt"

echo "epic task, sync conflict → abort, exit 11, tree clean, nothing pushed"
( cd "$tmp/seed" && git checkout -q ai/E-1 && git pull -q origin ai/E-1 && echo A > same.txt && git add same.txt && git commit -q -m A && git push -q origin ai/E-1 )
( cd "$tmp/seed" && git checkout -q dev && echo B > same.txt && git add same.txt && git commit -q -m B && git push -q origin dev )
fresh_worktree ws6
bash "$script" dev-start "$tmp/ws6" origin dev ai/ T-3 E-1 >"$tmp/out" 2>&1; rc=$?
check "exit 11"                    test "$rc" = 11
check "prints SYNC_CONFLICT"       grep -q "SYNC_CONFLICT" "$tmp/out"
check "lists same.txt"             grep -q "same.txt" "$tmp/out"
check "working tree clean"         test -z "$(git -C "$tmp/ws6" status --porcelain)"
check "ai/T-3 not created"         test "$(git -C "$tmp/ws6" rev-parse --abbrev-ref HEAD)" != ai/T-3
( cd "$tmp/seed" && git fetch -q origin )
check "remote ai/E-1 NOT updated with dev" test "$(git -C "$tmp/seed" rev-parse origin/ai/E-1)" != "$(git -C "$tmp/seed" rev-parse origin/dev)"

echo
if [ "$failed" = 0 ]; then echo "ALL OK"; else echo "FAILED"; fi
exit "$failed"
