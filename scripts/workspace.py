"""The work area of a task: its worktree and the branch checked out in it.

    dma workspace prepare <KEY>
    dma workspace remove  <KEY>

`prepare` is what the main session runs in run.md step 7, before spawning an
agent — the spawn prompt has to carry the path, so the area must be ready first.
It is `worktree bootstrap` followed by `branch checkout`, in one call: there is no
outcome where the directory exists but the branch was never set up, and a spawn is
never spent on a task whose epic branch is missing or whose sync conflicts.

Everything else comes from one read of the issue: its `area:` label gives the
checkout to work from, its `parent` gives the base branch (an epic branch when the
parent is a group), and its `agent:` label gives the role. The role decides whether
the task branch may be cut: dev, devops and sentinel produce it; qa and reviewer
read it, so for them a branch dev never pushed stops here with REF_ABSENT instead
of handing them an empty one.

`--workspace`, `--epic`, `--create` and `--no-create` override those, for a tracker
the CLI has no backend for and for tests.

`remove` is called when a task closes; it looks in every checkout the project
declares, because the worktree lives in the repo of whichever area owned the task.

Exit codes: 0 ok · 1 error · 2 provider not supported · 10 epic branch missing
            11 epic sync conflict · 13 task branch or base missing on the remote
"""

import os
import sys

import issue
import task_branch
import worktree


# The roles that produce the task branch; the rest may only read it.
BRANCH_AUTHORS = {"dev", "devops", "sentinel", "team-lead"}


def resolve(key, tracker):
    """The area, the base and the role — from the issue, in one read. `tracker` is
    a scripts/tracker.py backend: the issue arrives in the one shape both trackers
    answer in, so this works the same for Jira and Linear."""
    data = tracker.read(key)
    labels = data["labels"]
    area = next((l[len("area:"):] for l in labels if l.startswith("area:")), None)
    role = next((l[len("agent:"):] for l in labels if l.startswith("agent:")), None)
    parent = data["parent"]
    epic = parent["key"] if parent and parent["type"] == "group" else None
    return area, epic, role


def open_tracker_or_die():
    """The tracker the project configures. No backend for it → exit 2 and name
    the overrides that make `prepare` work without reading the issue."""
    import tracker as tracker_module

    try:
        return tracker_module.open_tracker(issue.load_config())
    except tracker_module.Unsupported as e:
        issue.die(f"{e} — pass --workspace / --epic / --create", 2)
    except tracker_module.TrackerError as e:
        issue.die(str(e))


def prepare(key, workspace_path=None, epic_key=None, area=None, create=None):
    # The overrides are complete only when both the checkout and the create
    # decision are given; `--epic` absent then means a standalone task, not
    # "unknown". Anything less and the issue is read to fill the gaps.
    if workspace_path is None or create is None:
        issue_area, issue_epic, role = resolve(key, open_tracker_or_die())
        area = area or issue_area
        epic_key = epic_key or issue_epic
        if create is None:
            create = role in BRANCH_AUTHORS
        workspace_path = workspace_path or worktree.area_workspace(area)

    settings = task_branch.Settings(area)
    path = worktree.bootstrap(workspace_path, key)
    if create:
        task_branch.prepare(path, settings, key, epic_key)
    else:
        task_branch.checkout(path, settings, key, epic_key, create=False)
    return path


def remove(key):
    """Try every checkout the project knows: the worktree sits in the repo of the
    area that owned the task, which the caller no longer needs to know."""
    removed = []
    for workspace_path in worktree.candidate_workspaces():
        try:
            ok, message = worktree.remove(workspace_path, key)
        except worktree.WorktreeError as e:
            print(f"WARNING {e}")
            continue
        if ok:
            removed.append(message)
            print(message)
        elif "no worktree at" not in message:
            print(f"WARNING {message}")
    if not removed:
        print(f"no worktree for {key}")
    return removed


FLAGS = ("--workspace", "--epic", "--area")


def main(argv):
    if len(argv) < 2 or argv[0] not in ("prepare", "remove"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    command, key = argv[0], argv[1]
    options, create, i = {}, None, 2
    while i < len(argv):
        if argv[i] in ("--create", "--no-create"):
            create, i = argv[i] == "--create", i + 1
            continue
        if argv[i] not in FLAGS or i + 1 >= len(argv):
            issue.die(__doc__.strip())
        options[argv[i][2:]] = argv[i + 1]
        i += 2

    if command == "remove":
        remove(key)
        return 0
    try:
        path = prepare(key, options.get("workspace"), options.get("epic"), options.get("area"), create)
    except task_branch.Stop as stop:
        print(str(stop))
        return stop.code
    except (task_branch.GitError, worktree.WorktreeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"workspace: {path}")
    return 0
