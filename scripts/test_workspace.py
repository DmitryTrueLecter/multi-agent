"""Tests for `dma workspace` (scripts/workspace.py) — the work area of a task.

`prepare` composes the worktree and the branch, so these tests check the seam:
that both halves ran, that neither half is left standing when the other fails,
and that `--create` is what separates the roles that produce a branch from the
roles that read it.

Run:  .venv/bin/pytest scripts/
"""

import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DMA = os.path.join(ROOT, "bin", "dma")

GIT_ENV = {
    "GIT_CONFIG_COUNT": "4",
    "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "test@test",
    "GIT_CONFIG_KEY_2": "user.name", "GIT_CONFIG_VALUE_2": "test",
    "GIT_CONFIG_KEY_3": "init.defaultBranch", "GIT_CONFIG_VALUE_3": "dev",
}

CONFIG = """
tasks:
  provider: jira
  project_key: T
vcs:
  dev_branch: dev
  branch_prefix: "ai/"
"""


@pytest.fixture(autouse=True)
def git_env(monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result.stdout.strip()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A clone with a remote — the shape the main session prepares from."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    checkout = tmp_path / "project"
    subprocess.run(["git", "clone", "-q", str(bare), str(checkout)], check=True, capture_output=True)
    (checkout / ".claude" / "dma").mkdir(parents=True)
    (checkout / ".claude" / "dma" / "config.yml").write_text(CONFIG)
    git(checkout, "checkout", "-q", "-b", "dev")
    (checkout / "file.txt").write_text("x")
    git(checkout, "add", "file.txt")
    git(checkout, "commit", "-q", "-m", "init")
    git(checkout, "push", "-q", "origin", "dev")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(checkout))
    return checkout


def dma(*args):
    result = subprocess.run([DMA, "workspace", *[str(a) for a in args]], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def branch_of(path):
    return git(path, "rev-parse", "--abbrev-ref", "HEAD")


def push_branch(project, name, base="dev"):
    """Publish a branch as another runner would have."""
    git(project, "checkout", "-q", "-b", name, base)
    git(project, "push", "-q", "origin", name)
    git(project, "checkout", "-q", "dev")


# ------------------------------------------------------------------ prepare

def test_prepare_with_create_makes_both_the_worktree_and_the_branch(project):
    rc, out = dma("prepare", "T-1", "--workspace", project, "--create")
    assert rc == 0, out
    path = project / ".worktrees" / "T-1"
    assert path.is_dir(), "the worktree half ran"
    assert branch_of(path) == "ai/T-1", "the branch half ran"
    assert f"workspace: {path}" in out, "the path the spawn prompt needs"


def test_prepare_runs_the_setup_commands_of_a_new_worktree(project):
    (project / ".claude" / "dma" / "config.yml").write_text(
        CONFIG + "worktree:\n  setup_commands:\n    - touch installed.txt\n")
    rc, out = dma("prepare", "T-1", "--workspace", project, "--create")
    assert rc == 0, out
    assert (project / ".worktrees" / "T-1" / "installed.txt").exists()


def test_prepare_without_create_checks_out_an_existing_branch(project):
    push_branch(project, "ai/T-1")
    rc, out = dma("prepare", "T-1", "--workspace", project, "--no-create")
    assert rc == 0, out
    assert branch_of(project / ".worktrees" / "T-1") == "ai/T-1"


def test_prepare_without_create_refuses_a_missing_branch(project):
    """qa and reviewer have nothing to review if dev never pushed."""
    rc, out = dma("prepare", "T-1", "--workspace", project, "--no-create")
    assert rc == 13
    assert "REF_ABSENT" in out


def test_prepare_stops_before_the_spawn_when_the_epic_branch_is_missing(project):
    rc, out = dma("prepare", "T-1", "--workspace", project, "--epic", "E-1", "--create")
    assert rc == 10
    assert "EPIC_MISSING ai/E-1" in out
    assert branch_of(project / ".worktrees" / "T-1") == "HEAD", "no branch was cut"


def test_prepare_cuts_an_epic_task_from_the_epic_branch(project):
    push_branch(project, "ai/E-1")
    git(project, "checkout", "-q", "ai/E-1")
    (project / "epic.txt").write_text("e")
    git(project, "add", "epic.txt")
    git(project, "commit", "-q", "-m", "epic")
    git(project, "push", "-q", "origin", "ai/E-1")
    git(project, "checkout", "-q", "dev")

    rc, out = dma("prepare", "T-1", "--workspace", project, "--epic", "E-1", "--create")
    assert rc == 0, out
    assert (project / ".worktrees" / "T-1" / "epic.txt").exists()


def test_prepare_is_idempotent_across_the_roles_of_one_task(project):
    """dev prepares with --create, qa and reviewer then get the same area back."""
    dma("prepare", "T-1", "--workspace", project, "--create")
    worktree = project / ".worktrees" / "T-1"
    git(worktree, "push", "-q", "origin", "ai/T-1")

    rc, out = dma("prepare", "T-1", "--workspace", project, "--no-create")
    assert rc == 0, out
    assert branch_of(worktree) == "ai/T-1"
    assert "reused" in out


def test_prepare_reports_a_failing_setup_command_and_cuts_no_branch(project):
    (project / ".claude" / "dma" / "config.yml").write_text(
        CONFIG + "worktree:\n  setup_commands:\n    - exit 3\n")
    rc, out = dma("prepare", "T-1", "--workspace", project, "--create")
    assert rc == 1
    assert "exit 3" in out
    assert branch_of(project / ".worktrees" / "T-1") == "HEAD", "the branch half must not run"


# ------------------------------------------------------------------ remove

def test_remove_gives_the_work_area_back(project):
    dma("prepare", "T-1", "--workspace", project, "--create")
    rc, out = dma("remove", "T-1")
    assert rc == 0, out
    assert not (project / ".worktrees" / "T-1").exists()


def test_remove_says_so_when_there_is_nothing_to_give_back(project):
    rc, out = dma("remove", "T-404")
    assert rc == 0, out
    assert "no worktree for T-404" in out


def test_remove_keeps_a_work_area_holding_uncommitted_changes(project):
    dma("prepare", "T-1", "--workspace", project, "--create")
    (project / ".worktrees" / "T-1" / "wip.txt").write_text("unsaved")
    git(project / ".worktrees" / "T-1", "add", "wip.txt")

    rc, out = dma("remove", "T-1")
    assert rc == 0, out
    assert (project / ".worktrees" / "T-1").is_dir()
    assert "WARNING" in out and "uncommitted" in out


# ------------------------------------------------------------------ resolution from the issue

def test_role_and_parent_come_from_the_issue_when_not_given(project, monkeypatch):
    """`dma workspace prepare <KEY>` is the whole call: area, base and the
    create decision are one read of the issue away."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import workspace

    class FakeJira:
        def get_issue(self, key):
            return {"fields": {"labels": ["area:backend", "agent:qa"],
                               "parent": {"key": "T-9", "fields": {"issuetype": {"name": "Epic"}}}}}

    assert workspace.resolve("T-1", FakeJira()) == ("backend", "T-9", "qa")


def test_a_parent_that_is_not_a_group_is_not_a_base(project):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import workspace

    class FakeJira:
        def get_issue(self, key):
            return {"fields": {"labels": ["agent:dev"],
                               "parent": {"key": "T-9", "fields": {"issuetype": {"name": "Task"}}}}}

    area, epic, role = workspace.resolve("T-1", FakeJira())
    assert epic is None, "only a group parent means an epic branch"
    assert role == "dev"


def test_the_role_decides_whether_the_branch_may_be_cut(project):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import workspace

    assert "dev" in workspace.BRANCH_AUTHORS and "devops" in workspace.BRANCH_AUTHORS
    assert "qa" not in workspace.BRANCH_AUTHORS and "reviewer" not in workspace.BRANCH_AUTHORS
