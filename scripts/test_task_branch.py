"""Tests for `dma branch` (scripts/task_branch.py) against a throwaway bare remote.

Fixture: a bare remote with a `dev` branch, a `seed` clone used to push scenario
branches, and helper clones detached at origin/dev — the shape /dma:run creates.

Run:  .venv/bin/pytest scripts/
"""

import os
import subprocess

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


def dma(*args):
    result = subprocess.run([DMA, "branch", *[str(a) for a in args]], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


# ------------------------------------------------------------------ dev-start, standalone

def test_fresh_standalone_cuts_branch_from_origin_dev(remote):
    ws = remote.worktree("ws")
    rc, out = dma("dev-start", ws, "origin", "dev", "ai/", "T-1")
    assert rc == 0, out
    assert "MODE=fresh" in out
    assert branch_of(ws) == "ai/T-1"
    assert (ws / "base.txt").exists()


def test_rerun_checks_out_existing_branch_and_keeps_commits(remote):
    ws1 = remote.worktree("ws1")
    dma("dev-start", ws1, "origin", "dev", "ai/", "T-1")
    (ws1 / "work1.txt").write_text("w")
    git(ws1, "add", "work1.txt"); git(ws1, "commit", "-q", "-m", "work1.txt"); git(ws1, "push", "-q", "origin", "ai/T-1")

    ws2 = remote.worktree("ws2")
    rc, out = dma("dev-start", ws2, "origin", "dev", "ai/", "T-1")
    assert rc == 0, out
    assert "MODE=rerun" in out
    assert "work1.txt" in out, "prior commits are listed"
    assert (ws2 / "work1.txt").exists()


def test_rerun_pulls_when_local_branch_is_behind_remote(remote):
    ws1 = remote.worktree("ws1")
    dma("dev-start", ws1, "origin", "dev", "ai/", "T-1")
    git(ws1, "push", "-q", "origin", "ai/T-1")
    ws2 = remote.worktree("ws2")
    dma("dev-start", ws2, "origin", "dev", "ai/", "T-1")          # local ai/T-1 now exists in ws2

    (ws1 / "work2.txt").write_text("w")
    git(ws1, "add", "work2.txt"); git(ws1, "commit", "-q", "-m", "work2.txt"); git(ws1, "push", "-q", "origin", "ai/T-1")

    rc, out = dma("dev-start", ws2, "origin", "dev", "ai/", "T-1")
    assert rc == 0, out
    assert (ws2 / "work2.txt").exists(), "remote commit pulled into the existing local branch"


# ------------------------------------------------------------------ dev-start, epic

def test_epic_missing_on_remote_exits_10_and_cuts_nothing(remote):
    ws = remote.worktree("ws")
    rc, out = dma("dev-start", ws, "origin", "dev", "ai/", "T-2", "E-1")
    assert rc == 10
    assert "EPIC_MISSING ai/E-1" in out
    assert branch_of(ws) == "HEAD", "still detached"


def test_epic_sync_merges_dev_into_epic_pushes_and_cuts_from_epic(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "epic.txt")
    remote.commit("dev", "newer-dev.txt")

    ws = remote.worktree("ws")
    rc, out = dma("dev-start", ws, "origin", "dev", "ai/", "T-2", "E-1")
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
    rc, out = dma("dev-start", wt, "origin", "dev", "ai/", "T-4", "E-1")
    assert rc == 0, out
    assert branch_of(wt) == "ai/T-4"
    assert (wt / "newer-dev.txt").exists()


def test_epic_sync_conflict_aborts_exits_11_pushes_nothing(remote):
    remote.new_branch("ai/E-1")
    remote.commit("ai/E-1", "same.txt", "A")
    remote.commit("dev", "same.txt", "B")

    ws = remote.worktree("ws")
    rc, out = dma("dev-start", ws, "origin", "dev", "ai/", "T-3", "E-1")
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
    dma("dev-start", ws1, "origin", "dev", "ai/", "T-1")
    (ws1 / "work.txt").write_text("w")
    git(ws1, "add", "work.txt"); git(ws1, "commit", "-q", "-m", "work"); git(ws1, "push", "-q", "origin", "ai/T-1")

    ws3 = remote.worktree("ws3")
    rc, out = dma("checkout", ws3, "origin", "dev", "ai/", "T-1")
    assert rc == 0, out
    assert branch_of(ws3) == "ai/T-1"
    assert (ws3 / "work.txt").exists()


def test_checkout_of_local_only_task_branch_is_allowed(remote):
    remote.new_branch("ai/T-5")
    (remote.seed / "local.txt").write_text("l")
    git(remote.seed, "add", "local.txt"); git(remote.seed, "commit", "-q", "-m", "local")
    git(remote.seed, "checkout", "-q", "dev")

    wt = remote.seed_worktree("T-5")
    rc, out = dma("checkout", wt, "origin", "dev", "ai/", "T-5")
    assert rc == 0, out
    assert branch_of(wt) == "ai/T-5"
    assert (wt / "local.txt").exists()


def test_checkout_missing_task_branch_exits_13(remote):
    ws = remote.worktree("ws")
    rc, out = dma("checkout", ws, "origin", "dev", "ai/", "T-404")
    assert rc == 13
    assert "REF_ABSENT ai/T-404" in out


def test_checkout_missing_base_exits_13(remote):
    ws = remote.worktree("ws")
    rc, out = dma("checkout", ws, "origin", "no-such-branch", "ai/", "T-1")
    assert rc == 13
    assert "REF_ABSENT no-such-branch" in out
