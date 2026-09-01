"""Tests for `dma branch` (scripts/task_branch.py) against a throwaway bare remote.

`prepare` is the composition dev calls; `sync-epic` and `checkout` are the two
halves it is built from, tested separately because `sync-epic` writes to a shared
branch.

Fixture: a bare remote with a `dev` branch, a `seed` clone used to push scenario
branches, and helper clones detached at origin/dev — the shape /dma:run creates.

Run:  .venv/bin/pytest scripts/
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DMA = os.path.join(ROOT, "bin", "dma")

# No signing / no identity prompts — for the fixture and for the code under test.
GIT_ENV = {
    "GIT_CONFIG_COUNT": "4",
    "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "test@test",
    "GIT_CONFIG_KEY_2": "user.name", "GIT_CONFIG_VALUE_2": "test",
    "GIT_CONFIG_KEY_3": "init.defaultBranch", "GIT_CONFIG_VALUE_3": "dev",
}


@pytest.fixture(autouse=True)
def git_env(monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result.stdout.strip()


def branch_of(repo):
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def remote_has(remote, branch):
    return subprocess.run(["git", "-C", str(remote.seed), "ls-remote", "--exit-code", "--heads",
                           "origin", branch], capture_output=True).returncode == 0


def is_ancestor(repo, ancestor, descendant):
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


class Remote:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.bare = tmp_path / "remote.git"
        self.seed = tmp_path / "seed"
        subprocess.run(["git", "init", "-q", "--bare", str(self.bare)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.bare), str(self.seed)], check=True, capture_output=True)
        git(self.seed, "checkout", "-q", "-b", "dev")
        (self.seed / "base.txt").write_text("base")
        git(self.seed, "add", "base.txt")
        git(self.seed, "commit", "-q", "-m", "base")
        git(self.seed, "push", "-q", "origin", "dev")

    def commit(self, branch, filename, content=None):
        """Add a commit on <branch> (in the seed clone) and push it."""
        git(self.seed, "checkout", "-q", branch)
        (self.seed / filename).write_text(content or filename)
        git(self.seed, "add", filename)
        git(self.seed, "commit", "-q", "-m", filename)
        git(self.seed, "push", "-q", "origin", branch)

    def new_branch(self, name, start="dev"):
        git(self.seed, "checkout", "-q", "-b", name, start)

    def worktree(self, name):
        """A clone detached at origin/dev, like /dma:run creates."""
        path = self.tmp / name
        subprocess.run(["git", "clone", "-q", str(self.bare), str(path)], check=True, capture_output=True)
        git(path, "checkout", "-q", "--detach", "origin/dev")
        return path

    def seed_worktree(self, name):
        """A worktree of the seed clone itself (shares its local branches)."""
        path = self.seed / ".worktrees" / name
        git(self.seed, "worktree", "add", "-q", "--detach", str(path), "origin/dev")
        return path

    def fetch(self):
        git(self.seed, "fetch", "-q", "origin")


@pytest.fixture
def remote(tmp_path):
    return Remote(tmp_path)


CONFIG = """
tasks:
  provider: jira
  project_key: T
  workflow:
    statuses:
      done: "Done"
vcs:
  dev_branch: dev
  branch_prefix: "ai/"
"""


@pytest.fixture
def project(tmp_path_factory):
    """A project root holding config.yml — where remote/dev_branch/prefix come from."""
    root = tmp_path_factory.mktemp("project")
    (root / ".claude" / "dma").mkdir(parents=True)
    (root / ".claude" / "dma" / "config.yml").write_text(CONFIG)
    return root


@pytest.fixture(autouse=True)
def project_env(project, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))


def dma(command, workspace, issue=None, epic=None, extra=()):
    args = [DMA, "branch", command, issue or epic, "--workspace", str(workspace)]
    if issue and epic:
        args += ["--epic", epic]
    args += list(extra)
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


# ------------------------------------------------------------------ dev-start, standalone

def test_fresh_standalone_cuts_branch_from_origin_dev(remote):
    ws = remote.worktree("ws")
    rc, out = dma("prepare", ws, "T-1")
    assert rc == 0, out
    assert "MODE=fresh" in out
    assert branch_of(ws) == "ai/T-1"
    assert (ws / "base.txt").exists()


def test_rerun_checks_out_existing_branch_and_keeps_commits(remote):
    ws1 = remote.worktree("ws1")
    dma("prepare", ws1, "T-1")
    (ws1 / "work1.txt").write_text("w")
    git(ws1, "add", "work1.txt"); git(ws1, "commit", "-q", "-m", "work1.txt"); git(ws1, "push", "-q", "origin", "ai/T-1")

    ws2 = remote.worktree("ws2")
    rc, out = dma("prepare", ws2, "T-1")
    assert rc == 0, out
    assert "MODE=rerun" in out
    assert "work1.txt" in out, "prior commits are listed"
    assert (ws2 / "work1.txt").exists()


def test_rerun_pulls_when_local_branch_is_behind_remote(remote):
    ws1 = remote.worktree("ws1")
    dma("prepare", ws1, "T-1")
    git(ws1, "push", "-q", "origin", "ai/T-1")
    ws2 = remote.worktree("ws2")
    dma("prepare", ws2, "T-1")          # local ai/T-1 now exists in ws2

    (ws1 / "work2.txt").write_text("w")
    git(ws1, "add", "work2.txt"); git(ws1, "commit", "-q", "-m", "work2.txt"); git(ws1, "push", "-q", "origin", "ai/T-1")

    rc, out = dma("prepare", ws2, "T-1")
    assert rc == 0, out
    assert (ws2 / "work2.txt").exists(), "remote commit pulled into the existing local branch"


# ------------------------------------------------------------------ dev-start, epic

def test_epic_missing_on_remote_exits_10_and_cuts_nothing(remote):
    ws = remote.worktree("ws")
    rc, out = dma("prepare", ws, "T-2", "E-1")
    assert rc == 10
    assert "EPIC_MISSING ai/E-1" in out
    assert branch_of(ws) == "HEAD", "still detached"


def test_epic_sync_merges_dev_into_epic_pushes_and_cuts_from_epic(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    remote.commit("dev", "newer-dev.txt")

    ws = remote.worktree("ws")
    rc, out = dma("prepare", ws, "T-2", "E-1")
    assert rc == 0, out
    assert "BASE=ai/E-1" in out
    assert branch_of(ws) == "ai/T-2"
    assert (ws / "epic.txt").exists(), "cut from the epic, not from dev"
    assert (ws / "newer-dev.txt").exists(), "dev synced into the epic"
    remote.fetch()
    assert is_ancestor(remote.seed, "origin/dev", "origin/ai/E-1"), "synced epic pushed"


def test_epic_sync_works_when_epic_is_checked_out_in_another_worktree(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    remote.commit("dev", "newer-dev.txt")
    git(remote.seed, "checkout", "-q", "ai/E-1")             # epic held by the main checkout

    wt = remote.seed_worktree("T-4")
    rc, out = dma("prepare", wt, "T-4", "E-1")
    assert rc == 0, out
    assert branch_of(wt) == "ai/T-4"
    assert (wt / "newer-dev.txt").exists()


def test_epic_sync_conflict_aborts_exits_11_pushes_nothing(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "same.txt", "A")
    remote.commit("dev", "same.txt", "B")

    ws = remote.worktree("ws")
    rc, out = dma("prepare", ws, "T-3", "E-1")
    assert rc == 11
    assert "SYNC_CONFLICT" in out
    assert "same.txt" in out
    assert git(ws, "status", "--porcelain") == "", "tree clean after abort"
    assert branch_of(ws) != "ai/T-3"
    remote.fetch()
    assert not is_ancestor(remote.seed, "origin/dev", "origin/ai/E-1"), "epic not pushed"


# ------------------------------------------------------------------ checkout (qa / reviewer)

def test_checkout_of_pushed_task_branch(remote):
    ws1 = remote.worktree("ws1")
    dma("prepare", ws1, "T-1")
    (ws1 / "work.txt").write_text("w")
    git(ws1, "add", "work.txt"); git(ws1, "commit", "-q", "-m", "work"); git(ws1, "push", "-q", "origin", "ai/T-1")

    ws3 = remote.worktree("ws3")
    rc, out = dma("checkout", ws3, "T-1")
    assert rc == 0, out
    assert branch_of(ws3) == "ai/T-1"
    assert (ws3 / "work.txt").exists()


def test_checkout_of_local_only_task_branch_is_allowed(remote):
    remote.new_branch("ai/T-5")
    (remote.seed / "local.txt").write_text("l")
    git(remote.seed, "add", "local.txt"); git(remote.seed, "commit", "-q", "-m", "local")
    git(remote.seed, "checkout", "-q", "dev")

    wt = remote.seed_worktree("T-5")
    rc, out = dma("checkout", wt, "T-5")
    assert rc == 0, out
    assert branch_of(wt) == "ai/T-5"
    assert (wt / "local.txt").exists()


def test_checkout_missing_task_branch_exits_13(remote):
    ws = remote.worktree("ws")
    rc, out = dma("checkout", ws, "T-404")
    assert rc == 13
    assert "REF_ABSENT ai/T-404" in out


def test_checkout_missing_base_exits_13(remote):
    """The task branch is there, but the base it should be diffed against is not."""
    ws1 = remote.worktree("ws1")
    dma("prepare", ws1, "T-1")
    git(ws1, "push", "-q", "origin", "ai/T-1")

    ws = remote.worktree("ws")
    rc, out = dma("checkout", ws, "T-1", extra=["--dev-branch", "no-such-branch"])
    assert rc == 13
    assert "REF_ABSENT no-such-branch" in out


# ------------------------------------------------------------------ the halves on their own

def test_sync_epic_alone_pushes_the_epic_without_touching_the_task_branch(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    remote.commit("dev", "newer-dev.txt")

    ws = remote.worktree("ws")
    rc, out = dma("sync-epic", ws, epic="E-1")
    assert rc == 0, out
    assert "SYNCED ai/E-1 <- dev" in out
    remote.fetch()
    assert is_ancestor(remote.seed, "origin/dev", "origin/ai/E-1")
    assert not remote_has(remote, "ai/T-2"), "sync-epic creates no task branch"


def test_checkout_create_does_not_sync_the_epic(remote):
    """The halves stay separate: cutting a branch must not push a shared one."""
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    remote.commit("dev", "newer-dev.txt")
    remote.fetch()
    epic_before = git(remote.seed, "rev-parse", "origin/ai/E-1")

    ws = remote.worktree("ws")
    rc, out = dma("checkout", ws, "T-2", "E-1", extra=["--create"])
    assert rc == 0, out
    assert branch_of(ws) == "ai/T-2"
    assert (ws / "epic.txt").exists()
    assert not (ws / "newer-dev.txt").exists(), "no sync happened, so dev's commit is absent"
    remote.fetch()
    assert git(remote.seed, "rev-parse", "origin/ai/E-1") == epic_before, "epic branch untouched"


def test_checkout_without_create_refuses_to_cut_a_missing_branch(remote):
    ws = remote.worktree("ws")
    rc, out = dma("checkout", ws, "T-7")
    assert rc == 13
    assert branch_of(ws) == "HEAD"


def test_prepare_on_a_rerun_does_not_resync_the_epic(remote):
    """The integration contract was set when the branch was cut; a later dev commit
    must not be dragged into the epic behind the user's back."""
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    ws = remote.worktree("ws")
    dma("prepare", ws, "T-2", "E-1")
    git(ws, "push", "-q", "origin", "ai/T-2")

    remote.commit("dev", "later-dev.txt")
    remote.fetch()
    epic_before = git(remote.seed, "rev-parse", "origin/ai/E-1")

    ws2 = remote.worktree("ws2")
    rc, out = dma("prepare", ws2, "T-2", "E-1")
    assert rc == 0, out
    assert "MODE=rerun" in out
    remote.fetch()
    assert git(remote.seed, "rev-parse", "origin/ai/E-1") == epic_before, "no sync on a re-run"


# ------------------------------------------------------------------ create-epic

def dma_epic(command, workspace, epic):
    args = [DMA, "branch", command, epic, "--workspace", str(workspace)]
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_create_epic_publishes_the_branch_off_dev(remote):
    """team-lead's step at decomposition: children cut from it right after."""
    ws = remote.worktree("ws")
    rc, out = dma_epic("create-epic", ws, "E-1")
    assert rc == 0, out
    assert "CREATED ai/E-1" in out
    assert remote_has(remote, "ai/E-1")
    remote.fetch()
    assert git(remote.seed, "rev-parse", "origin/ai/E-1") == git(remote.seed, "rev-parse", "origin/dev")


def test_create_epic_leaves_an_existing_branch_alone(remote):
    """Recovery re-runs the same step; an epic branch with work on it must survive."""
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    remote.fetch()
    before = git(remote.seed, "rev-parse", "origin/ai/E-1")

    ws = remote.worktree("ws")
    rc, out = dma_epic("create-epic", ws, "E-1")
    assert rc == 0, out
    assert "EXISTS ai/E-1" in out
    remote.fetch()
    assert git(remote.seed, "rev-parse", "origin/ai/E-1") == before


def test_create_epic_does_not_disturb_the_checkout_it_runs_in(remote):
    """It runs in the area's main checkout, which may be on any branch."""
    ws = remote.worktree("ws")
    git(ws, "checkout", "-q", "-b", "local-work")
    dma_epic("create-epic", ws, "E-1")
    assert branch_of(ws) == "local-work"


def test_a_task_can_be_cut_from_a_freshly_created_epic(remote):
    ws = remote.worktree("ws")
    dma_epic("create-epic", ws, "E-1")
    rc, out = dma("prepare", ws, "T-1", "E-1")
    assert rc == 0, out
    assert branch_of(ws) == "ai/T-1"


def test_create_epic_fails_when_the_push_did_not_land(remote, monkeypatch):
    """decompose.md verifies the branch on the remote after pushing it: a push that
    reports success but leaves no ref would send every child into EPIC_MISSING.
    Plain git cannot produce that, so this pins the guard at the function level."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import task_branch

    ws = remote.worktree("ws")
    monkeypatch.setattr(task_branch, "on_remote", lambda *args: False)
    settings = type("S", (), {"remote": "origin", "dev_branch": "dev",
                              "branch": staticmethod(lambda key: f"ai/{key}")})()

    with pytest.raises(task_branch.Stop) as raised:
        task_branch.create_epic(str(ws), settings, "E-1")
    assert raised.value.code == 12
    assert "PUSH_NOT_LANDED" in str(raised.value)


# ------------------------------------------------------------------ verify-remote

def dma_key(command, workspace, key, extra=()):
    args = [DMA, "branch", command, key, "--workspace", str(workspace), *extra]
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_verify_remote_passes_when_the_remote_holds_the_reviewed_head(remote):
    ws = remote.worktree("ws")
    dma("prepare", ws, "T-1")
    git(ws, "push", "-q", "origin", "ai/T-1")
    rc, out = dma_key("verify-remote", ws, "T-1")
    assert rc == 0, out
    assert "MATCH" in out


def test_verify_remote_refuses_an_unpushed_commit(remote):
    """The reviewed tree is not the tree that would merge, so no PR may be opened."""
    ws = remote.worktree("ws")
    dma("prepare", ws, "T-1")
    git(ws, "push", "-q", "origin", "ai/T-1")
    (ws / "later.txt").write_text("x")
    git(ws, "add", "later.txt"); git(ws, "commit", "-q", "-m", "later")

    rc, out = dma_key("verify-remote", ws, "T-1")
    assert rc == 14
    assert "REMOTE_BEHIND" in out


def test_verify_remote_refuses_a_branch_that_was_never_pushed(remote):
    ws = remote.worktree("ws")
    dma("prepare", ws, "T-1")
    rc, out = dma_key("verify-remote", ws, "T-1")
    assert rc == 14
    assert "REMOTE_MISSING" in out


# ------------------------------------------------------------------ drift

def dma_epic_cmd(command, workspace, epic):
    result = subprocess.run([DMA, "branch", command, epic, "--workspace", str(workspace)],
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_drift_reports_none_when_the_dev_branch_has_not_moved(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    ws = remote.worktree("ws")
    rc, out = dma_epic_cmd("drift", ws, "E-1")
    assert rc == 0, out
    assert "DRIFT none" in out and "DEV_AHEAD 0" in out


def test_drift_on_untouched_files_is_a_non_event(remote):
    """A plain merge handles it at PR time; the close-out only logs it."""
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic-only.txt")
    remote.commit("dev", "dev-only.txt")
    ws = remote.worktree("ws")
    rc, out = dma_epic_cmd("drift", ws, "E-1")
    assert rc == 0, out
    assert "DRIFT disjoint" in out
    assert "DEV_AHEAD 1" in out
    assert "OVERLAP" not in out


def test_drift_on_the_same_file_is_named_with_the_paths(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "shared.txt", "from the epic")
    remote.commit("dev", "shared.txt", "from dev")
    remote.commit("dev", "other.txt")
    ws = remote.worktree("ws")
    rc, out = dma_epic_cmd("drift", ws, "E-1")
    assert rc == 0, out
    assert "DRIFT overlapping" in out
    assert "shared.txt" in out.split("OVERLAP")[1]
    assert "other.txt" not in out.split("OVERLAP")[1], "only the intersection is listed"


def test_drift_without_an_epic_branch_says_so(remote):
    ws = remote.worktree("ws")
    rc, out = dma_epic_cmd("drift", ws, "E-9")
    assert rc == 10
    assert "EPIC_MISSING ai/E-9" in out
