"""Per-task git worktrees — the procedure of commands/run.md "Worktree bootstrap".

    dma worktree bootstrap --workspace P --issue K    creates it, prints its path
    dma worktree remove    --workspace P --issue K

`--workspace` is the checkout the area lives in, resolved by the caller exactly as
run.md step 7 resolves it (area.yml → config.yml → "."). `--issue` is the issue
key, or the epic key for a group close-out.

bootstrap: resolve the repo owning the workspace, create
`<repo-root>/.worktrees/<KEY>` detached at HEAD, link the gitignored artifacts
listed in `config.yml` `worktree.link_paths`, run `worktree.setup_commands` from
the worktree root, and mark the worktree provisioned.

A worktree that carries the mark is reused as it stands, so re-claiming a task does
not reinstall its dependencies. A worktree without it — one whose setup commands
failed half-way, on a flaky install or a missing binary — is provisioned again
rather than handed over silently broken.

Exit codes: 0 ok · 1 error (git failure, or a setup command that failed)
"""

import os
import subprocess
import sys

import issue


class WorktreeError(Exception):
    pass


def repo_root(workspace_path):
    """The repo owning the workspace: the project root in a monorepo, the
    area-repo in a multi-repo project."""
    result = subprocess.run(["git", "-C", workspace_path, "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise WorktreeError(f"not a git repository: {workspace_path}\n{result.stderr.strip()}")
    return result.stdout.strip()


def worktree_path(workspace_path, key):
    return os.path.join(repo_root(workspace_path), ".worktrees", key)


MARK = "dma-provisioned"


def mark_path(worktree):
    """Kept in git's private per-worktree directory, so it never shows up as a
    stray file in the tree the agent works in."""
    git_dir = subprocess.run(["git", "-C", worktree, "rev-parse", "--absolute-git-dir"],
                             capture_output=True, text=True)
    if git_dir.returncode != 0:
        raise WorktreeError(f"not a git worktree: {worktree}\n{git_dir.stderr.strip()}")
    return os.path.join(git_dir.stdout.strip(), MARK)


def provision(path, root):
    """Link what the project shares, run what it needs built. Arbitrary project
    commands: a non-zero exit aborts and names the command."""
    worktree_config = issue.load_config().get("worktree") or {}

    for entry in worktree_config.get("link_paths") or []:
        source = os.path.join(root, entry)
        target = os.path.join(path, entry)
        if os.path.exists(source) and not os.path.exists(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            subprocess.run(["ln", "-snf", source, target], check=True)
            print(f"linked {entry}")

    for command in worktree_config.get("setup_commands") or []:
        if subprocess.run(command, shell=True, cwd=path).returncode != 0:
            raise WorktreeError(f"setup command failed in {path}: {command}")
        print(f"ran {command}")

    open(mark_path(path), "w").close()


def bootstrap(workspace_path, key):
    root = repo_root(workspace_path)
    path = os.path.join(root, ".worktrees", key)

    if os.path.isdir(path):
        if os.path.exists(mark_path(path)):
            print(f"reused {path}")
            return path
        print(f"reprovisioning {path} — the previous setup did not finish")
        provision(path, root)
        print(path)
        return path

    created = subprocess.run(["git", "-C", root, "worktree", "add", "--detach", path, "HEAD"],
                             capture_output=True, text=True)
    if created.returncode != 0:
        # Typical cause: that branch is already checked out in another worktree.
        raise WorktreeError(f"could not create worktree {path}\n{created.stderr.strip()}")

    provision(path, root)
    print(path)
    return path


def remove(workspace_path, key):
    """Never forced: uncommitted work in the worktree stays for a human to judge."""
    root = repo_root(workspace_path)
    path = os.path.join(root, ".worktrees", key)
    if not os.path.isdir(path):
        return False, f"no worktree at {path}"
    result = subprocess.run(["git", "-C", root, "worktree", "remove", path], capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"worktree not removed (uncommitted changes?): {path}\n{result.stderr.strip()}"
    return True, f"removed {path}"


def candidate_workspaces():
    """Every checkout a worktree for a key could live in: the project root plus
    each area's workspace. Used when closing a task, where the area that owns the
    worktree is not known up front."""
    paths = [issue.PROJECT_DIR]
    config = issue.load_config()
    project_path = (config.get("workspace") or {}).get("path")
    if project_path:
        paths.append(os.path.normpath(os.path.join(issue.PROJECT_DIR, project_path)))
    areas_dir = os.path.join(issue.PROJECT_DIR, ".claude", "dma", "areas")
    for area in sorted(os.listdir(areas_dir)) if os.path.isdir(areas_dir) else []:
        area_config = os.path.join(areas_dir, area, "area.yml")
        if not os.path.exists(area_config):
            continue
        import yaml
        with open(area_config) as f:
            path = (((yaml.safe_load(f) or {}).get("workspace") or {}).get("path"))
        if path:
            paths.append(path if os.path.isabs(path) else os.path.normpath(os.path.join(issue.PROJECT_DIR, path)))
    return [p for p in dict.fromkeys(paths) if os.path.isdir(p)]


def parse(argv, allowed=("--workspace", "--issue")):
    options, i = {}, 0
    while i < len(argv):
        if argv[i] not in allowed or i + 1 >= len(argv):
            return None
        options[argv[i][2:]] = argv[i + 1]
        i += 2
    return options


def main(argv):
    options = parse(argv[1:]) if argv else None
    if not argv or argv[0] not in ("bootstrap", "remove") or not options \
            or not options.get("workspace") or not options.get("issue"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    command, workspace_path, key = argv[0], options["workspace"], options["issue"]
    try:
        if command == "bootstrap":
            bootstrap(workspace_path, key)
            return 0
        ok, message = remove(workspace_path, key)
        print(message)
        return 0 if ok else 1
    except WorktreeError as e:
        print(str(e), file=sys.stderr)
        return 1
