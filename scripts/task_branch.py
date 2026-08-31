"""Task-branch operations. Mirrors dev.md "Task workflow" step 2 and qa/reviewer step 2.

    dma branch prepare    --workspace P --issue K [--epic E] [--area A]
    dma branch checkout   --workspace P --issue K [--epic E] [--area A] [--create]
    dma branch sync-epic  --workspace P --epic E [--area A]
    dma branch create-epic --workspace P --epic E [--area A]

`prepare` is what dev calls: one command, so the sequence cannot be executed
half-way. Under the hood it is `sync-epic` (only for a fresh epic-parented task)
followed by `checkout --create`. The two are separately callable because
`sync-epic` writes to a *shared* branch — it merges the dev branch into the epic
branch and pushes it — and that is too big a side effect to hide inside a name
about checking out.

`--remote`, `--dev-branch` and `--prefix` are resolved from config.yml (and the
area's area.yml when `--area` is given); pass them explicitly only to override.

Exit codes:
    0   ok
    1   git error / usage
    10  epic branch missing on remote          (dev.md 2a)
    11  ARCH-EPIC-SYNC conflict, aborted       (dev.md 2c)
    12  epic branch push did not land on the remote (decompose.md step 4)
    13  task branch or base missing on remote  (qa.md / reviewer.md "Ref absent")
"""

import os
import subprocess
import sys

import yaml

import issue


class GitError(Exception):
    pass


class Stop(Exception):
    """A defined outcome the caller must act on, carrying its exit code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def git(workspace, *args, check=True):
    result = subprocess.run(["git", "-C", workspace, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def on_remote(workspace, remote, branch):
    return subprocess.run(["git", "-C", workspace, "ls-remote", "--exit-code", "--heads", remote, branch],
                          capture_output=True).returncode == 0


def local_exists(workspace, branch):
    return subprocess.run(["git", "-C", workspace, "show-ref", "--verify", "--quiet",
                           f"refs/heads/{branch}"]).returncode == 0


def checkout_existing(workspace, remote, branch):
    if local_exists(workspace, branch):
        git(workspace, "checkout", branch)
    else:
        git(workspace, "checkout", "-b", branch, "--track", f"{remote}/{branch}")


# ----------------------------------------------------------------- settings

class Settings:
    """remote / dev_branch / branch_prefix, resolved area.yml → config.yml → default."""

    def __init__(self, area=None, overrides=None):
        overrides = {k: v for k, v in (overrides or {}).items() if v}
        config = issue.load_config()
        project_ws = config.get("workspace") or {}
        area_ws = {}
        if area:
            path = os.path.join(issue.PROJECT_DIR, ".claude", "dma", "areas", area, "area.yml")
            if not os.path.exists(path):
                issue.die(f"area config not found: {path}")
            with open(path) as f:
                area_ws = (yaml.safe_load(f) or {}).get("workspace") or {}
        vcs = config.get("vcs") or {}
        self.remote = overrides.get("remote") or area_ws.get("remote") or project_ws.get("remote") or "origin"
        self.dev_branch = (overrides.get("dev_branch") or area_ws.get("dev_branch")
                           or project_ws.get("dev_branch") or vcs.get("dev_branch"))
        self.prefix = overrides.get("prefix") or vcs.get("branch_prefix") or ""
        if not self.dev_branch:
            issue.die("vcs.dev_branch is not set in config.yml")

    def branch(self, key):
        return f"{self.prefix}{key}"


# ----------------------------------------------------------------- operations

def sync_epic(workspace, settings, epic_key):
    """ARCH-EPIC-SYNC: bring the epic branch up to date with the dev branch.

    Runs on a detached HEAD at the remote epic tip — the epic branch may be
    checked out in another worktree, where `git checkout <epic>` would fail —
    and pushes the result. This is the step that writes to a shared branch.
    """
    epic_branch = settings.branch(epic_key)
    git(workspace, "fetch", settings.remote)
    if not on_remote(workspace, settings.remote, epic_branch):
        raise Stop(10, f"EPIC_MISSING {epic_branch} on {settings.remote}")

    git(workspace, "checkout", "--detach", f"{settings.remote}/{epic_branch}")
    merge = subprocess.run(["git", "-C", workspace, "merge", "--no-edit",
                            f"{settings.remote}/{settings.dev_branch}"], capture_output=True, text=True)
    if merge.returncode != 0:
        conflicted = git(workspace, "diff", "--name-only", "--diff-filter=U")
        git(workspace, "merge", "--abort", check=False)
        if not conflicted:
            raise GitError(f"merge failed without content conflicts\n{merge.stdout}\n{merge.stderr}")
        dev_sha = git(workspace, "rev-parse", f"{settings.remote}/{settings.dev_branch}")
        raise Stop(11, f"SYNC_CONFLICT dev_branch SHA tried: {dev_sha}\nConflicted files:\n{conflicted}")

    git(workspace, "push", settings.remote, f"HEAD:{epic_branch}")
    print(f"SYNCED {epic_branch} <- {settings.dev_branch}")


def checkout(workspace, settings, key, epic_key=None, create=False):
    """Put the worktree on the task branch.

    Without --create the branch must already exist (qa / reviewer). With --create
    it is cut from the base when missing — the base being the epic branch for an
    epic-parented task, the dev branch otherwise. Never syncs the epic.
    """
    task_branch = settings.branch(key)
    base = settings.branch(epic_key) if epic_key else settings.dev_branch
    git(workspace, "fetch", settings.remote)

    # Every path below needs the base: to diff against it, or to cut from it.
    if not on_remote(workspace, settings.remote, base):
        raise Stop(13, f"REF_ABSENT {base} on {settings.remote}")

    if on_remote(workspace, settings.remote, task_branch):
        checkout_existing(workspace, settings.remote, task_branch)
        git(workspace, "pull", "--no-rebase", settings.remote, task_branch)
        print("MODE=rerun")
        print(f"BASE={base}")
        print(git(workspace, "log", "--oneline", f"{settings.remote}/{base}..HEAD"))
        return

    if not create:
        # The branch may be local-only: dev committed but has not pushed yet.
        if local_exists(workspace, task_branch):
            git(workspace, "checkout", task_branch)
            print(f"BASE={base}")
            print(git(workspace, "diff", "--stat", f"{settings.remote}/{base}...HEAD"))
            return
        raise Stop(13, f"REF_ABSENT {task_branch} (not local, not on {settings.remote})")

    git(workspace, "checkout", "-b", task_branch, "--no-track", f"{settings.remote}/{base}")
    print("MODE=fresh")
    print(f"BASE={base}")


def create_epic(workspace, settings, epic_key):
    """Cut the epic branch off the dev branch and publish it — team-lead's step at
    decomposition, and again when recovering an epic decomposed without one.

    Runs in the area's main checkout (no worktree exists yet at that point), on a
    detached HEAD so it never disturbs whatever branch that checkout is on. The
    push is verified against the remote: a branch that did not land would send
    every child task into EPIC_MISSING.
    """
    epic_branch = settings.branch(epic_key)
    git(workspace, "fetch", settings.remote)
    if on_remote(workspace, settings.remote, epic_branch):
        print(f"EXISTS {epic_branch} on {settings.remote}")
        return

    git(workspace, "push", settings.remote,
        f"{settings.remote}/{settings.dev_branch}:refs/heads/{epic_branch}")
    if not on_remote(workspace, settings.remote, epic_branch):
        raise Stop(12, f"PUSH_NOT_LANDED {epic_branch} is not on {settings.remote} after the push")
    print(f"CREATED {epic_branch} <- {settings.dev_branch}")


def prepare(workspace, settings, key, epic_key=None):
    """What dev calls. Resuming a previous attempt never re-syncs the epic — the
    integration contract was established when the branch was first cut."""
    task_branch = settings.branch(key)
    git(workspace, "fetch", settings.remote)
    fresh = not on_remote(workspace, settings.remote, task_branch)
    if fresh and epic_key:
        sync_epic(workspace, settings, epic_key)
    checkout(workspace, settings, key, epic_key, create=True)


# ----------------------------------------------------------------- cli

FLAGS = ("--workspace", "--issue", "--epic", "--area", "--remote", "--dev-branch", "--prefix")


def parse(argv):
    options, create, i = {}, False, 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--create":
            create, i = True, i + 1
            continue
        if flag not in FLAGS or i + 1 >= len(argv):
            issue.die(__doc__.strip())
        options[flag[2:].replace("-", "_")] = argv[i + 1]
        i += 2
    return options, create


def main(argv):
    if not argv or argv[0] not in ("prepare", "sync-epic", "checkout", "create-epic"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    command = argv[0]
    options, create = parse(argv[1:])

    workspace = options.get("workspace")
    if not workspace:
        issue.die("--workspace is required")
    if not os.path.isdir(workspace):
        issue.die(f"workspace not found: {workspace}")
    settings = Settings(options.get("area"), overrides={
        "remote": options.get("remote"),
        "dev_branch": options.get("dev_branch"),
        "prefix": options.get("prefix"),
    })

    try:
        if command in ("sync-epic", "create-epic"):
            if not options.get("epic"):
                issue.die(f"--epic is required for {command}")
            if command == "sync-epic":
                sync_epic(workspace, settings, options["epic"])
            else:
                create_epic(workspace, settings, options["epic"])
        else:
            if not options.get("issue"):
                issue.die("--issue is required")
            if command == "prepare":
                prepare(workspace, settings, options["issue"], options.get("epic"))
            else:
                checkout(workspace, settings, options["issue"], options.get("epic"), create=create)
    except Stop as stop:
        print(str(stop))
        return stop.code
    except GitError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0
