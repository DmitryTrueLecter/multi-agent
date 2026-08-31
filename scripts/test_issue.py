"""Tests for `dma issue` (scripts/issue.py) against a fake Jira.

The fake is a local HTTP server that records every request. Each test runs
bin/dma as a subprocess with CLAUDE_PROJECT_DIR pointing at a throwaway project
(config.yml + .mcp.json) and asserts on exit code, stdout and the HTTP calls.

Run:  .venv/bin/pytest scripts/
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DMA = os.path.join(ROOT, "bin", "dma")

ISSUE = {
    "key": "T-1",
    "fields": {
        "summary": "Do the thing",
        "status": {"name": "To Do"},
        "labels": ["area:backend", "agent:dev", "needs-decision"],
        "parent": {"key": "E-1", "fields": {"summary": "Big epic", "issuetype": {"name": "Epic"}}},
        "description": "Purpose\nRequirements",
        "comment": {"comments": [
            {"author": {"displayName": "old"}, "created": "2026-01-01", "body": "first comment"},
            {"author": {"displayName": "new"}, "created": "2026-01-02", "body": "🤖 reviewer (backend): handoff → dev"},
        ]},
    },
}

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


class FakeJira:
    """Records (method, path, json body) for every request; can reject transitions."""

    def __init__(self):
        self.requests = []
        self.reject_transition = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length)) if length else None

            def _reply(self, code, payload=None):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload is not None:
                    self.wfile.write(json.dumps(payload).encode())

            def do_GET(self):
                fake.requests.append(("GET", self.path, None))
                self._reply(200, ISSUE)

            def do_POST(self):
                body = self._body()
                fake.requests.append(("POST", self.path, body))
                if self.path.endswith("/transitions") and fake.reject_transition:
                    self._reply(400, {"errorMessages": ["transition not valid"]})
                else:
                    self._reply(201 if self.path.endswith("/comment") else 204)

            def do_PUT(self):
                fake.requests.append(("PUT", self.path, self._body()))
                self._reply(204)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    @property
    def methods(self):
        return [r[0] for r in self.requests]

    def body(self, index):
        return self.requests[index][2]


@pytest.fixture
def jira():
    fake = FakeJira()
    yield fake
    fake.server.shutdown()


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

def test_read_prints_normalized_issue(dma, jira):
    result = dma("read", "T-1")
    assert result.returncode == 0, result.stderr
    assert jira.methods == ["GET"]
    assert "parent" in jira.requests[0][1], "parent must be requested explicitly (fields=*all omits it)"
    assert "title: Do the thing" in result.stdout
    assert "parent: E-1 (group)" in result.stdout
    assert "labels: area:backend, agent:dev, needs-decision" in result.stdout


def test_read_lists_comments_newest_first(dma):
    out = dma("read", "T-1").stdout
    assert out.index("handoff → dev") < out.index("first comment")


# ------------------------------------------------------------------ claim

def test_claim_transitions_to_in_progress_then_reads(dma, jira):
    result = dma("claim", "T-1")
    assert result.returncode == 0, result.stderr
    assert [(r[0], r[2]) for r in jira.requests] == [("POST", {"transition": {"id": "21"}}), ("GET", None)]
    assert "CLAIMED T-1" in result.stdout
    assert "title: Do the thing" in result.stdout


def test_claim_rejected_exits_3_without_retry(dma, jira):
    jira.reject_transition = True
    result = dma("claim", "T-1")
    assert result.returncode == 3
    assert "CLAIM_FAILED T-1" in result.stdout
    assert jira.methods == ["POST"]


# ------------------------------------------------------------------ comment

def test_comment_posts_body(dma, jira):
    result = dma("comment", "T-1", "🤖 dev (backend): progress")
    assert result.returncode == 0, result.stderr
    assert jira.requests == [("POST", "/rest/api/2/issue/T-1/comment", {"body": "🤖 dev (backend): progress"})]


def test_comment_body_from_stdin_keeps_newlines(dma, jira):
    result = dma("comment", "T-1", "-", stdin="line1\nline2\n")
    assert result.returncode == 0, result.stderr
    assert jira.body(0) == {"body": "line1\nline2"}


# ------------------------------------------------------------------ handoff

def test_handoff_default_forward_dev_to_qa(dma, jira):
    result = dma("handoff", "T-1")
    assert result.returncode == 0, result.stderr
    assert jira.methods == ["GET", "PUT", "POST", "POST"]
    assert jira.body(1) == {"fields": {"labels": ["area:backend", "agent:qa"]}}, "area kept, agent swapped, needs-decision dropped"
    assert jira.body(2) == {"transition": {"id": "3"}}
    assert jira.body(3)["body"].startswith("🤖 dev (backend): handoff → qa\n\n")
    assert "Manual handoff via /dma:handoff." in jira.body(3)["body"]


def test_handoff_to_team_lead_adds_needs_decision(dma, jira):
    result = dma("handoff", "T-1", "team-lead", "Epic branch missing on remote.")
    assert result.returncode == 0, result.stderr
    assert jira.body(1) == {"fields": {"labels": ["area:backend", "agent:team-lead", "needs-decision"]}}
    assert jira.body(2) == {"transition": {"id": "2"}}
    assert jira.body(3)["body"].endswith("Epic branch missing on remote.")


def test_handoff_single_non_role_argument_is_the_body(dma, jira):
    result = dma("handoff", "T-1", "tests added for X")
    assert result.returncode == 0, result.stderr
    assert jira.body(2) == {"transition": {"id": "3"}}, "default target qa"
    assert jira.body(3)["body"].endswith("tests added for X")


def test_handoff_to_awaiting_merge_drops_agent_label(dma, jira):
    result = dma("handoff", "T-1", "awaiting_merge", "approved")
    assert result.returncode == 0, result.stderr
    assert jira.body(1) == {"fields": {"labels": ["area:backend"]}}
    assert jira.body(2) == {"transition": {"id": "5"}}


def test_handoff_unknown_target_mutates_nothing(dma, jira):
    result = dma("handoff", "T-1", "nowhere", "x")
    assert result.returncode == 1
    assert jira.methods == ["GET"]


def test_handoff_missing_transition_id_fails_before_any_write(dma, jira, project):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("qa: 3", "qa: 0"))
    result = dma("handoff", "T-1", "qa", "x")
    assert result.returncode == 1
    assert "transitions.qa" in result.stderr
    assert jira.methods == ["GET"]


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
