"""Task-branch setup for dev / qa / reviewer. Mirrors dev.md "Task workflow" step 2.

    dma branch dev-start <workspace> <remote> <dev_branch> <prefix> <ISSUE-KEY> [EPIC-KEY]
    dma branch checkout  <workspace> <remote> <dev_branch> <prefix> <ISSUE-KEY> [EPIC-KEY]

Exit codes:
    0   ok
    1   git error
    10  epic branch missing on remote          (dev.md 2a)
    11  ARCH-EPIC-SYNC conflict, aborted       (dev.md 2c)
    13  task branch or base missing on remote  (qa.md / reviewer.md "Ref absent")
"""

import subprocess
import sys


class GitError(Exception):
    pass


def git(workspace, *args, check=True):
    """Run git in the workspace; stdout is returned, stderr is passed through."""
    result = subprocess.run(["git", "-C", workspace, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def on_remote(workspace, remote, branch):
    return subprocess.run(["git", "-C", workspace, "ls-remote", "--exit-code", "--heads", remote, branch],
                          capture_output=True).returncode == 0


def local_branch_exists(workspace, branch):
    return subprocess.run(["git", "-C", workspace, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode == 0


def checkout_existing(workspace, remote, branch):
    if local_branch_exists(workspace, branch):
        git(workspace, "checkout", branch)
    else:
        git(workspace, "checkout", "-b", branch, "--track", f"{remote}/{branch}")


def dev_start(workspace, remote, dev_branch, prefix, issue, epic):
    task_branch = prefix + issue
    base = prefix + epic if epic else dev_branch
    git(workspace, "fetch", remote)

    # Re-run: the task branch already exists on the remote.
    # Continue from the previous attempt, do not recreate, do not lose commits.
    if on_remote(workspace, remote, task_branch):
        checkout_existing(workspace, remote, task_branch)
        git(workspace, "pull", "--no-rebase", remote, task_branch)
        print("MODE=rerun")
        print(f"BASE={base}")
        print(git(workspace, "log", "--oneline", f"{remote}/{base}..HEAD"))
        return 0

    # Fresh task.
    if epic:
        # 2a. The epic branch must exist on the remote. Never fall back to dev_branch.
        if not on_remote(workspace, remote, base):
            print(f"EPIC_MISSING {base} on {remote}")
            return 10

        # 2b. ARCH-EPIC-SYNC: merge dev_branch into the epic branch and push it.
        # Done on a detached HEAD at the remote epic tip: the epic branch may be
        # checked out in another worktree, and "git checkout <epic>" would fail.
        git(workspace, "checkout", "--detach", f"{remote}/{base}")
        merge = subprocess.run(["git", "-C", workspace, "merge", "--no-edit", f"{remote}/{dev_branch}"],
                               capture_output=True, text=True)
        if merge.returncode != 0:
            # 2c. Conflict: abort, report, do not resolve, do not push.
            conflicted = git(workspace, "diff", "--name-only", "--diff-filter=U")
            git(workspace, "merge", "--abort", check=False)
            if not conflicted:
                raise GitError(f"merge failed without content conflicts\n{merge.stdout}\n{merge.stderr}")
            print("SYNC_CONFLICT")
            print(f"dev_branch SHA tried: {git(workspace, 'rev-parse', f'{remote}/{dev_branch}')}")
            print("Conflicted files:")
            print(conflicted)
            return 11
        git(workspace, "push", remote, f"HEAD:{base}")

    # 2d. Cut the task branch from the remote base ref.
    git(workspace, "checkout", "-b", task_branch, "--no-track", f"{remote}/{base}")
    print("MODE=fresh")
    print(f"BASE={base}")
    return 0


def checkout(workspace, remote, dev_branch, prefix, issue, epic):
    task_branch = prefix + issue
    base = prefix + epic if epic else dev_branch
    git(workspace, "fetch", remote)

    # Base must be on the remote; the task branch may be local-only (dev committed
    # but did not push) — same as the old "git checkout <task branch>" allowed.
    if not on_remote(workspace, remote, base):
        print(f"REF_ABSENT {base} on {remote}")
        return 13
    if local_branch_exists(workspace, task_branch):
        git(workspace, "checkout", task_branch)
    elif on_remote(workspace, remote, task_branch):
        git(workspace, "checkout", "-b", task_branch, "--track", f"{remote}/{task_branch}")
    else:
        print(f"REF_ABSENT {task_branch} (not local, not on {remote})")
        return 13
    if on_remote(workspace, remote, task_branch):
        git(workspace, "pull", "--no-rebase", remote, task_branch)
    print(f"BASE={base}")
    print(git(workspace, "diff", "--stat", f"{remote}/{base}...HEAD"))
    return 0


def main(argv):
    if len(argv) < 6 or argv[0] not in ("dev-start", "checkout"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    command, workspace, remote, dev_branch, prefix, issue = argv[:6]
    epic = argv[6] if len(argv) > 6 else None
    run = dev_start if command == "dev-start" else checkout
    try:
        return run(workspace, remote, dev_branch, prefix, issue, epic)
    except GitError as e:
        print(str(e), file=sys.stderr)
        return 1
