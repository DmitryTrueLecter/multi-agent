"""Tests for `dma worktree` (scripts/worktree.py) against throwaway repositories.

The procedure this covers is commands/run.md "Worktree bootstrap": create
`.worktrees/<KEY>` in the repo that owns the workspace, link what the project
declares, run its setup commands, and reuse an existing worktree untouched.

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

BASE_CONFIG = """
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
    """A git project with config.yml — the shape /dma:run bootstraps into."""
    (tmp_path / ".claude" / "dma").mkdir(parents=True)
    (tmp_path / ".claude" / "dma" / "config.yml").write_text(BASE_CONFIG)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "file.txt").write_text("x")
    git(tmp_path, "add", "file.txt")
    git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def set_config(project, body):
    (project / ".claude" / "dma" / "config.yml").write_text(BASE_CONFIG + body)


def dma(command, workspace, key):
    result = subprocess.run([DMA, "worktree", command, "--workspace", str(workspace), "--issue", key],
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_bootstrap_creates_the_worktree_and_prints_its_path(project):
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 0, out
    path = project / ".worktrees" / "T-1"
    assert path.is_dir()
    assert str(path) in out
    assert (path / "file.txt").exists(), "the worktree is a checkout of the repo"


def test_bootstrap_detaches_head_so_no_branch_is_held(project):
    dma("bootstrap", project, "T-1")
    assert git(project / ".worktrees" / "T-1", "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"


def test_bootstrap_links_the_declared_paths(project):
    (project / ".venv").mkdir()
    (project / ".venv" / "marker").write_text("m")
    set_config(project, "worktree:\n  link_paths:\n    - .venv\n")

    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 0, out
    link = project / ".worktrees" / "T-1" / ".venv"
    assert link.is_symlink() and (link / "marker").exists()


def test_bootstrap_skips_a_declared_path_that_does_not_exist(project):
    set_config(project, "worktree:\n  link_paths:\n    - .venv\n")
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 0, out
    assert not (project / ".worktrees" / "T-1" / ".venv").exists()


def test_bootstrap_runs_the_setup_commands_in_the_worktree(project):
    set_config(project, "worktree:\n  setup_commands:\n    - touch installed.txt\n")
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 0, out
    assert (project / ".worktrees" / "T-1" / "installed.txt").exists()
    assert not (project / "installed.txt").exists(), "commands run in the worktree, not the repo root"


def test_bootstrap_runs_setup_commands_in_order(project):
    set_config(project, "worktree:\n  setup_commands:\n    - echo one >> order.txt\n    - echo two >> order.txt\n")
    dma("bootstrap", project, "T-1")
    assert (project / ".worktrees" / "T-1" / "order.txt").read_text().split() == ["one", "two"]


def test_a_failing_setup_command_aborts_and_names_itself(project):
    set_config(project, "worktree:\n  setup_commands:\n    - exit 3\n    - touch never.txt\n")
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 1
    assert "exit 3" in out
    assert not (project / ".worktrees" / "T-1" / "never.txt").exists(), "later commands must not run"


def test_an_existing_worktree_is_reused_without_reprovisioning(project):
    """Re-claiming a task must not reinstall its dependencies."""
    set_config(project, "worktree:\n  setup_commands:\n    - echo run >> installs.txt\n")
    dma("bootstrap", project, "T-1")
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 0, out
    assert "reused" in out
    assert (project / ".worktrees" / "T-1" / "installs.txt").read_text().count("run") == 1


def test_bootstrap_reports_a_git_refusal_instead_of_continuing(project):
    """Typical cause: the same path is already registered as another worktree."""
    dma("bootstrap", project, "T-1")
    subprocess.run(["rm", "-rf", str(project / ".worktrees" / "T-1")], check=True)
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 1
    assert "could not create worktree" in out


def test_bootstrap_uses_the_repo_that_owns_the_workspace(project, tmp_path):
    """In a multi-repo project the worktree belongs to the area's repo, not the
    project root."""
    area_repo = tmp_path / "area-backend"
    area_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(area_repo)], check=True)
    (area_repo / "a.txt").write_text("a")
    git(area_repo, "add", "a.txt")
    git(area_repo, "commit", "-q", "-m", "init")

    rc, out = dma("bootstrap", area_repo, "T-1")
    assert rc == 0, out
    assert (area_repo / ".worktrees" / "T-1").is_dir()
    assert not (project / ".worktrees" / "T-1").exists()


def test_remove_deletes_the_worktree(project):
    dma("bootstrap", project, "T-1")
    rc, out = dma("remove", project, "T-1")
    assert rc == 0, out
    assert not (project / ".worktrees" / "T-1").exists()


def test_remove_keeps_a_worktree_with_uncommitted_work(project):
    dma("bootstrap", project, "T-1")
    (project / ".worktrees" / "T-1" / "wip.txt").write_text("unsaved")
    git(project / ".worktrees" / "T-1", "add", "wip.txt")

    rc, out = dma("remove", project, "T-1")
    assert rc == 1
    assert (project / ".worktrees" / "T-1").is_dir(), "work in progress is never force-removed"
    assert "uncommitted" in out


def test_remove_of_a_missing_worktree_says_so(project):
    rc, out = dma("remove", project, "T-404")
    assert rc == 1
    assert "no worktree at" in out


def test_a_worktree_whose_setup_failed_is_provisioned_again(project):
    """A flaky install must not leave a half-built area that is silently reused."""
    set_config(project, "worktree:\n  setup_commands:\n    - test -f /tmp/dma-fixed && touch installed.txt\n")
    subprocess.run(["rm", "-f", "/tmp/dma-fixed"], check=True)
    rc, out = dma("bootstrap", project, "T-1")
    assert rc == 1, out
    assert not (project / ".worktrees" / "T-1" / "installed.txt").exists()

    subprocess.run(["touch", "/tmp/dma-fixed"], check=True)
    rc, out = dma("bootstrap", project, "T-1")
    subprocess.run(["rm", "-f", "/tmp/dma-fixed"], check=True)
    assert rc == 0, out
    assert "reprovisioning" in out
    assert (project / ".worktrees" / "T-1" / "installed.txt").exists(), "the retry finished the setup"


def test_a_provisioned_worktree_leaves_no_stray_file_in_the_tree(project):
    dma("bootstrap", project, "T-1")
    assert git(project / ".worktrees" / "T-1", "status", "--porcelain") == ""
