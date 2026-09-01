"""Task-branch operations. Mirrors dev.md "Task workflow" step 2 and qa/reviewer step 2.

    dma branch prepare      <KEY>        make the task branch ready to work in
    dma branch checkout     <KEY>        switch to it; it must already exist
    dma branch verify-remote <KEY>       the remote holds what was reviewed
    dma branch sync-epic    <EPIC-KEY> --area A   merge the dev branch into it
    dma branch create-epic  <EPIC-KEY> --area A   cut it off the dev branch
    dma branch drift        <EPIC-KEY> --area A   has the dev branch moved on

A task key is all these need: the issue says which area it belongs to, and that
gives the checkout and — for `prepare` and `checkout` — the worktree the task
works in. An epic carries no area label, so those three take `--area` (skip it in
a monorepo). `--workspace`, `--epic` and `--create` remain as overrides, for a
tracker the CLI cannot read and for tests.

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
    14  the remote branch is not at the local HEAD (reviewer.md step 7a)
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
            # "first hit wins": an area with no area.yml is simply no hit at that
            # level — a label like `area:devops` need not have a config of its own.
            path = os.path.join(issue.PROJECT_DIR, ".claude", "dma", "areas", area, "area.yml")
            if os.path.exists(path):
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


def verify_remote(workspace, settings, key):
    """reviewer.md step 7a: the branch on the remote is the state that was reviewed.

    The dev pushes at QA handoff and the reviewer never pushes, so a mismatch means
    the reviewed tree is not the tree that would merge — the PR must not be opened.
    """
    task_branch = settings.branch(key)
    git(workspace, "fetch", settings.remote, task_branch, check=False)
    local = git(workspace, "rev-parse", "HEAD")
    print(f"LOCAL {local}")
    if not on_remote(workspace, settings.remote, task_branch):
        raise Stop(14, f"REMOTE_MISSING {task_branch} is not on {settings.remote}; "
                       f"push the reviewed commits ({local})")
    remote_head = git(workspace, "rev-parse", f"{settings.remote}/{task_branch}")
    print(f"REMOTE {remote_head}")
    if remote_head != local:
        raise Stop(14, f"REMOTE_BEHIND {task_branch} on {settings.remote} is at {remote_head}, "
                       f"the reviewed HEAD is {local}; push the reviewed commits")
    print("MATCH")


def drift(workspace, settings, epic_key):
    """epic-closeout.md step 7: has the dev branch moved on since the epic branch
    was cut, and does the movement touch the same files?

    Path-disjoint drift is a non-event a plain merge handles at PR time. Overlapping
    drift carries semantic-conflict risk, and rewriting a shared epic branch is not
    a decision to take without the user, so this only reports.
    """
    epic_branch = settings.branch(epic_key)
    git(workspace, "fetch", settings.remote)
    if not on_remote(workspace, settings.remote, epic_branch):
        raise Stop(10, f"EPIC_MISSING {epic_branch} on {settings.remote}")
    # Both sides are read as remote refs: those are what the PR will merge, and a
    # worktree need not have either branch locally.
    epic_ref = f"{settings.remote}/{epic_branch}"
    dev_ref = f"{settings.remote}/{settings.dev_branch}"
    base = git(workspace, "merge-base", epic_ref, dev_ref)
    ahead = int(git(workspace, "rev-list", f"{base}..{dev_ref}", "--count") or 0)
    print(f"MERGE_BASE {base}")
    print(f"DEV_AHEAD {ahead}")
    if not ahead:
        print("DRIFT none")
        return
    dev_files = set(git(workspace, "diff", "--name-only", f"{base}..{dev_ref}").splitlines())
    epic_files = set(git(workspace, "diff", "--name-only", f"{base}..{epic_ref}").splitlines())
    overlap = sorted(dev_files & epic_files)
    print(f"DRIFT {'overlapping' if overlap else 'disjoint'}")
    if overlap:
        print("OVERLAP")
        for path in overlap:
            print(path)


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

FLAGS = ("--workspace", "--epic", "--area", "--remote", "--dev-branch", "--prefix")


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


TASK_COMMANDS = ("prepare", "checkout", "verify-remote")
EPIC_COMMANDS = ("sync-epic", "create-epic", "drift")


def resolve_workspace(command, key, options):
    """Where the command runs. A task command works inside that task's worktree;
    an epic command works in the area's own checkout, because at decomposition and
    at close-out there is no per-task tree yet."""
    if options.get("workspace"):
        return options["workspace"], options.get("area"), options.get("epic")

    import worktree

    area = options.get("area")
    epic = None
    if command in TASK_COMMANDS and not area:
        import workspace as workspace_module
        import tracker as tracker_module

        config = issue.load_config()
        try:
            backend = tracker_module.open_tracker(config)
        except (tracker_module.Unsupported, tracker_module.TrackerError) as e:
            issue.die(f"{e} — pass --workspace and --area", 2)
        area, epic, _ = workspace_module.resolve(key, backend.api if hasattr(backend, "api") else backend)
    checkout = worktree.area_workspace(area)
    if command in EPIC_COMMANDS:
        return checkout, area, None
    return worktree.worktree_path(checkout, key), area, epic


def main(argv):
    if not argv or argv[0] not in TASK_COMMANDS + EPIC_COMMANDS or len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    command, key = argv[0], argv[1]
    options, create = parse(argv[2:])

    workspace, area, found_epic = resolve_workspace(command, key, options)
    if not os.path.isdir(workspace):
        issue.die(f"workspace not found: {workspace}")
    settings = Settings(area, overrides={
        "remote": options.get("remote"),
        "dev_branch": options.get("dev_branch"),
        "prefix": options.get("prefix"),
    })
    epic = options.get("epic") or found_epic

    try:
        if command in EPIC_COMMANDS:
            {"sync-epic": sync_epic, "create-epic": create_epic, "drift": drift}[command](
                workspace, settings, key)
        elif command == "verify-remote":
            verify_remote(workspace, settings, key)
        elif command == "prepare":
            prepare(workspace, settings, key, epic)
        else:
            checkout(workspace, settings, key, epic, create=create)
    except Stop as stop:
        print(str(stop))
        return stop.code
    except GitError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0
