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


def test_read_lists_the_blockers_and_their_status(dma, jira):
    """The orchestrator must not dispatch a task whose blockers are unfinished."""
    jira.add_issue("T-7", "To Do", blocked_by=[("T-4", "QA"), ("T-3", "Done")])
    out = dma("read", "T-7").stdout
    assert "blocked by: T-4 (QA), T-3 (Done)" in out


def test_read_of_an_unblocked_task_says_so(dma, jira):
    assert "blocked by: -" in dma("read", "T-1").stdout


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


# ------------------------------------------------------------------ claim from a queue

def test_claim_by_role_takes_the_task_and_names_role_and_area(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["area:backend", "agent:dev"])
    result = dma("claim", "--role", "dev")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-5") == "In Progress"
    assert "CLAIMED T-5" in result.stdout
    assert "role: dev" in result.stdout and "area: backend" in result.stdout


def test_claim_by_role_skips_a_blocked_task(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["agent:dev"], blocked_by=[("T-4", "In Progress")])
    jira.add_issue("T-6", "To Do", labels=["agent:dev"])
    result = dma("claim", "--role", "dev")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-5") == "To Do", "a task with an unfinished blocker must not be claimed"
    assert jira.status_of("T-6") == "In Progress"


def test_claim_by_role_accepts_a_task_whose_blockers_are_done(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["agent:dev"], blocked_by=[("T-4", "Done")])
    result = dma("claim", "--role", "dev")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-5") == "In Progress"


def test_claim_any_respects_the_queue_priority(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["agent:dev"])
    jira.add_issue("T-6", "On Hold", labels=["agent:team-lead"])
    result = dma("claim", "--any")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-6") == "In Progress", "on_hold team-lead outranks a to_do dev task"
    assert jira.status_of("T-5") == "To Do"


def test_claim_by_role_moves_on_when_another_runner_wins_the_race(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["agent:dev"])
    jira.add_issue("T-6", "To Do", labels=["agent:dev"])
    original = jira.issue_payload
    lost = {"done": False}

    def steal(key):                     # the first candidate is claimed elsewhere mid-flight
        if key == "T-5" and not lost["done"]:
            lost["done"] = True
            jira.reject_transitions.add("21")
        elif key == "T-6":
            jira.reject_transitions.discard("21")
        return original(key)

    jira.issue_payload = steal
    result = dma("claim", "--role", "dev")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-6") == "In Progress"


def test_claim_by_role_filtered_to_one_area(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["area:frontend", "agent:qa"])
    jira.add_issue("T-6", "To Do", labels=["area:backend", "agent:qa"])
    result = dma("claim", "--role", "backend/qa")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-6") == "In Progress" and jira.status_of("T-5") == "To Do"


def test_claim_of_a_group_queue_picks_the_epic(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "Code Review", labels=["agent:team-lead"])          # Task, older
    jira.add_issue("T-8", "Code Review", labels=["agent:team-lead"], kind="Epic")
    result = dma("claim", "--role", "team-lead")
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-8") == "In Progress", "the group queue is issuetype = Epic"
    assert jira.status_of("T-5") == "Code Review", "the Task in the same status belongs to reviewer"


def test_claim_with_an_empty_queue_exits_4(dma, jira):
    jira.issues.clear()
    result = dma("claim", "--role", "devops")
    assert result.returncode == 4
    assert "nothing to claim" in result.stdout


def test_claim_reports_the_blocked_task_it_skipped(dma, jira):
    jira.issues.clear()             # the queue tests start from an empty board
    jira.add_issue("T-5", "To Do", labels=["agent:dev"], blocked_by=[("T-4", "QA")])
    result = dma("claim", "--role", "dev")
    assert result.returncode == 4
    assert "T-5 blocked by T-4" in result.stdout


def test_claim_with_an_unknown_role_is_refused(dma, jira):
    jira.issues.clear()
    result = dma("claim", "--role", "designer")
    assert result.returncode == 1
    assert "unknown role" in result.stderr


def test_reviewer_queue_never_picks_a_group(dma, jira):
    """`code_review` is shared: Epics belong to team-lead, Tasks to the reviewer."""
    jira.issues.clear()
    jira.add_issue("T-8", "Code Review", labels=["agent:reviewer"], kind="Epic")
    result = dma("claim", "--role", "reviewer")
    assert result.returncode == 4
    assert jira.status_of("T-8") == "Code Review"
