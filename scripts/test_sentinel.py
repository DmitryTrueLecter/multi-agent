"""Tests for `dma sentinel flag` — a prompt defect filed for sentinel.

A flag is worth nothing if it lands in the project's default status instead of
the Sentinel queue: nobody reads it there. These check that the queue is where it
ends up, and that a flag with no location or no known type is refused before
anything is created.

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
      sentinel_inbox: "Sentinel"
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
      sentinel_inbox: 8
      done: 41
"""

TRANSITION_STATUS = {"11": "To Do", "21": "In Progress", "3": "QA", "6": "Code Review",
                     "2": "On Hold", "5": "Awaiting Merge", "7": "Awaiting Ops",
                     "8": "Sentinel", "41": "Done"}


@pytest.fixture
def jira():
    fake = fakes.FakeJira()
    fake.transition_status = dict(TRANSITION_STATUS)
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
        return subprocess.run([DMA, "sentinel", *args], input=stdin,
                              capture_output=True, text=True, env=env)
    return run


def created_key(result):
    return result.stdout.split()[1]


def test_a_flag_lands_in_the_sentinel_queue(dma, jira):
    """The project creates issues in On Hold; a flag left there is unread."""
    result = dma("flag", "PROMPT-UNCLEAR", "step 2 can be read two ways",
                 "--where", "agents/dev.md / ## Task workflow", "--reporter", "dev")
    assert result.returncode == 0, result.stderr
    key = created_key(result)
    assert jira.status_of(key) == "Sentinel"
    assert jira.labels_of(key) == ["sentinel-flag", "flag-type:prompt-unclear", "agent:sentinel"]


def test_the_summary_carries_the_type_and_the_problem(dma, jira):
    result = dma("flag", "ENV-FRICTION", "hook blocks the prescribed command",
                 "--where", "hooks/bash_safety.py", "--reporter", "qa")
    key = created_key(result)
    created = [b for (m, p, b) in jira.writes() if p == "/rest/api/2/issue"][0]
    assert created["fields"]["summary"] == "[ENV-FRICTION] hook blocks the prescribed command"
    assert "**Where:** hooks/bash_safety.py" in created["fields"]["description"]
    assert "**Reporter:** qa" in created["fields"]["description"]


def test_optional_context_is_included_when_given(dma, jira):
    dma("flag", "PATTERN-REPEAT", "same bounce twice", "--where", "agents/dev.md",
        "--reporter", "reviewer", "--originating", "T-77", "--details", "both times on step 5")
    created = [b for (m, p, b) in jira.writes() if p == "/rest/api/2/issue"][0]
    body = created["fields"]["description"]
    assert "**Originating:** T-77" in body and "**Details:** both times on step 5" in body


def test_details_can_come_on_stdin(dma, jira):
    dma("flag", "PROMPT-INCOMPLETE", "no path for this case", "--where", "agents/qa.md",
        "--reporter", "qa", "--details", "-", stdin="line one\nline two")
    created = [b for (m, p, b) in jira.writes() if p == "/rest/api/2/issue"][0]
    assert "line one\nline two" in created["fields"]["description"]


def test_an_unknown_type_is_refused_before_anything_is_created(dma, jira):
    result = dma("flag", "PROMPT-WEIRD", "something", "--where", "agents/dev.md")
    assert result.returncode == 1
    assert "unknown flag type" in result.stderr
    assert jira.writes() == []


def test_a_flag_without_a_location_is_refused(dma, jira):
    """A defect report that does not say where the defect is cannot be triaged."""
    result = dma("flag", "PROMPT-UNCLEAR", "something is off", "--reporter", "dev")
    assert result.returncode == 1
    assert "--where is required" in result.stderr
    assert jira.writes() == []


def test_a_project_without_a_sentinel_queue_is_told_so(dma, jira, project):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace('      sentinel_inbox: "Sentinel"\n', ""))
    result = dma("flag", "PROMPT-UNCLEAR", "x", "--where", "agents/dev.md")
    assert result.returncode == 1
    assert "sentinel_inbox" in result.stderr
    assert jira.writes() == []


def test_a_flag_that_cannot_reach_the_queue_reports_the_key_it_made(dma, jira):
    """The issue exists by then, so the caller is told which one to look at."""
    jira.reject_transitions.add("8")
    result = dma("flag", "PROMPT-UNCLEAR", "x", "--where", "agents/dev.md", "--reporter", "dev")
    assert result.returncode == 1
    assert "T-900" in result.stderr and "Sentinel" in result.stderr
