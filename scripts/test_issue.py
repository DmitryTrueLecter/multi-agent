"""Tests for `dma issue` (scripts/issue.py).

Offline: the Jira fake serves payloads recorded off the real API (scripts/fakes.py,
scripts/fixtures/) and applies the writes it receives, so each test asserts both
the calls made and the resulting issue state. Whether the endpoints still exist
and still answer this shape is scripts/test_contract.py.

Run:  .venv/bin/pytest scripts/
"""

import json
import os
import subprocess

import pytest

import fakes

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DMA = os.path.join(ROOT, "bin", "dma")

CONFIG = """
tasks:
  provider: jira
  project_key: T
  workflow:
    statuses:
      to_do: "To Do"
      in_progress: "In Progress"
      qa: "QA"
      code_review: "Code Review"
      on_hold: "On Hold"
      awaiting_merge: "Awaiting Merge"
      awaiting_ops: "Awaiting Ops"
      done: "Done"
  jira:
    transitions:
      to_do: 11
      in_progress: 21
      qa: 3
      code_review: 6
      on_hold: 2
      awaiting_merge: 5
      awaiting_ops: 7
      done: 41
"""

TRANSITION_STATUS = {"11": "To Do", "21": "In Progress", "3": "QA", "6": "Code Review",
                     "2": "On Hold", "5": "Awaiting Merge", "7": "Awaiting Ops", "41": "Done"}


@pytest.fixture
def jira():
    fake = fakes.FakeJira()
    fake.transition_status = dict(TRANSITION_STATUS)
    fake.add_issue("T-1", "To Do", labels=["area:backend", "agent:dev", "needs-decision"],
                   parent=("E-1", "Epic"),
                   comments=["first comment", "🤖 reviewer (backend): handoff → dev"])
    yield fake
    fake.shutdown()


@pytest.fixture
def project(tmp_path, jira):
    (tmp_path / ".claude" / "dma").mkdir(parents=True)
    (tmp_path / ".claude" / "dma" / "config.yml").write_text(CONFIG)
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"atlassian": {"env": {
        "JIRA_URL": jira.url, "JIRA_USERNAME": "u", "JIRA_API_TOKEN": "t"}}}}))
    return tmp_path


@pytest.fixture
def dma(project):
    def run(*args, stdin=None):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
        return subprocess.run([DMA, "issue", *args], input=stdin, capture_output=True, text=True, env=env)
    return run


# ------------------------------------------------------------------ read

def test_read_prints_the_fields_an_agent_works_from(dma, jira):
    result = dma("read", "T-1")
    assert result.returncode == 0, result.stderr
    assert "title:" in result.stdout
    assert "status: To Do" in result.stdout
    assert "parent: E-1 (group)" in result.stdout
    assert "labels: area:backend, agent:dev, needs-decision" in result.stdout


def test_read_requests_the_parent_field_explicitly(dma, jira):
    """fields=*all omits parent, which silently breaks base-branch selection."""
    dma("read", "T-1")
    assert "parent" in jira.requests[0][1]


def test_read_lists_comments_newest_first(dma):
    out = dma("read", "T-1").stdout
    assert out.index("handoff → dev") < out.index("first comment")


def test_read_of_a_task_without_a_parent(dma, jira):
    jira.add_issue("T-7", "To Do")
    assert "parent: null" in dma("read", "T-7").stdout


# ------------------------------------------------------------------ claim

def test_claim_transitions_to_in_progress_and_returns_the_issue(dma, jira):
    result = dma("claim", "T-1")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "In Progress"
    assert "CLAIMED T-1" in result.stdout and "labels:" in result.stdout


def test_claim_refused_by_the_workflow_exits_3_without_retrying(dma, jira):
    jira.reject_transitions.add("21")
    result = dma("claim", "T-1")
    assert result.returncode == 3
    assert "CLAIM_FAILED T-1" in result.stdout
    assert [m for (m, p, b) in jira.writes()] == ["POST"], "no retry, no follow-up read"


# ------------------------------------------------------------------ comment

def test_comment_posts_the_body_verbatim(dma, jira):
    result = dma("comment", "T-1", "🤖 dev (backend): progress")
    assert result.returncode == 0, result.stderr
    assert jira.comments_of("T-1")[-1] == "🤖 dev (backend): progress"


def test_comment_from_stdin_keeps_line_breaks(dma, jira):
    result = dma("comment", "T-1", "-", stdin="line1\nline2\n")
    assert result.returncode == 0, result.stderr
    assert jira.comments_of("T-1")[-1] == "line1\nline2"


def test_comment_does_not_change_status_or_labels(dma, jira):
    dma("comment", "T-1", "note")
    assert jira.status_of("T-1") == "To Do"
    assert jira.labels_of("T-1") == ["area:backend", "agent:dev", "needs-decision"]


# ------------------------------------------------------------------ handoff

def test_handoff_defaults_to_the_next_role_in_the_pipeline(dma, jira):
    result = dma("handoff", "T-1")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "QA"
    assert jira.labels_of("T-1") == ["area:backend", "agent:qa"], "area kept, needs-decision dropped"
    assert jira.comments_of("T-1")[-1].startswith("🤖 dev (backend): handoff → qa\n\n")


def test_handoff_to_team_lead_adds_needs_decision(dma, jira):
    result = dma("handoff", "T-1", "team-lead", "Epic branch missing on remote.")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "On Hold"
    assert jira.labels_of("T-1") == ["area:backend", "agent:team-lead", "needs-decision"]
    assert jira.comments_of("T-1")[-1].endswith("Epic branch missing on remote.")


def test_handoff_single_argument_that_is_not_a_role_is_the_comment(dma, jira):
    result = dma("handoff", "T-1", "tests added for X")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "QA"
    assert jira.comments_of("T-1")[-1].endswith("tests added for X")


def test_handoff_to_awaiting_merge_leaves_no_agent_owner(dma, jira):
    result = dma("handoff", "T-1", "awaiting_merge", "approved")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Awaiting Merge"
    assert jira.labels_of("T-1") == ["area:backend"]


def test_handoff_body_from_stdin(dma, jira):
    result = dma("handoff", "T-1", "qa", "-", stdin="line1\nline2\n")
    assert result.returncode == 0, result.stderr
    assert jira.comments_of("T-1")[-1].endswith("line1\nline2")


def test_handoff_to_an_unknown_target_changes_nothing(dma, jira):
    result = dma("handoff", "T-1", "nowhere", "x")
    assert result.returncode == 1
    assert jira.writes() == []


def test_handoff_with_a_missing_transition_id_writes_nothing(dma, jira, project):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("qa: 3", "qa: 0"))
    result = dma("handoff", "T-1", "qa", "x")
    assert result.returncode == 1
    assert "transitions.qa" in result.stderr
    assert jira.writes() == [], "labels must not move before the transition is known"


# ------------------------------------------------------------------ environment

def test_provider_linear_exits_2_without_http(dma, jira, project):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("provider: jira", "provider: linear"))
    result = dma("read", "T-1")
    assert result.returncode == 2
    assert jira.requests == []


def test_missing_credentials_names_the_variables(dma, project):
    (project / ".mcp.json").unlink()
    result = dma("read", "T-1")
    assert result.returncode == 1
    assert "JIRA_URL" in result.stderr


def test_missing_config_names_the_path(dma, project):
    (project / ".claude" / "dma" / "config.yml").unlink()
    result = dma("read", "T-1")
    assert result.returncode == 1
    assert "config not found" in result.stderr
