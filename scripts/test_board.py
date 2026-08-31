"""Tests for `dma board` (scripts/board.py).

Offline: the Jira and Bitbucket fakes serve payloads recorded off the real APIs
(scripts/fakes.py, scripts/fixtures/). They check decision logic — which task is
touched, in what order, with what labels and status. Whether those endpoints still
exist and still answer this shape is scripts/test_contract.py.

Run:  .venv/bin/pytest scripts/
"""

import json
import os
import subprocess
import sys

import pytest

import fakes

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DMA = os.path.join(ROOT, "bin", "dma")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

APPROVED = "a" * 40
OTHER = "b" * 40
MERGE_SHA = "c" * 40
AWAITING = "Awaiting Merge"

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
vcs:
  branch_prefix: "ai/"
  dev_branch: dev
"""

TRANSITION_STATUS = {"11": "To Do", "21": "In Progress", "3": "QA", "6": "Code Review",
                     "2": "On Hold", "5": AWAITING, "7": "Awaiting Ops", "41": "Done"}


@pytest.fixture
def jira():
    fake = fakes.FakeJira()
    fake.transition_status = dict(TRANSITION_STATUS)
    yield fake
    fake.shutdown()


@pytest.fixture
def bb():
    fake = fakes.FakeBitbucket()
    yield fake
    fake.shutdown()


@pytest.fixture
def project(tmp_path, jira, bb):
    (tmp_path / ".claude" / "dma").mkdir(parents=True)
    (tmp_path / ".claude" / "dma" / "config.yml").write_text(CONFIG)
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"atlassian": {"env": {
        "JIRA_URL": jira.url, "JIRA_USERNAME": "u", "JIRA_API_TOKEN": "t",
        "BITBUCKET_URL": bb.url, "BITBUCKET_USERNAME": "bu", "BITBUCKET_APP_PASSWORD": "bp",
    }}}}))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@bitbucket.org:testws/testrepo.git"],
                   cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def dma(project):
    def run():
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
        return subprocess.run([DMA, "board", "reconcile"], capture_output=True, text=True, env=env)
    return run


def merged_pr(bb, pr_id, key, source_tip=APPROVED, **kwargs):
    """A merged PR whose merge commit landed `source_tip` from the task branch."""
    merge_sha = kwargs.pop("merge_sha", MERGE_SHA)
    pr = bb.add_pr(pr_id, f"ai/{key}", "MERGED", merge_sha=merge_sha, **kwargs)
    bb.add_commit(merge_sha, [OTHER, source_tip] if source_tip else [OTHER])
    return pr


# ------------------------------------------------------------------ merged

def test_merged_at_approved_tip_goes_to_done(dma, jira, bb):
    jira.add_issue("T-1", AWAITING, labels=["area:api"], comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"
    assert jira.labels_of("T-1") == ["area:api"]
    assert f"merged into dev at {APPROVED}" in jira.comments_of("T-1")[-1]


def test_merged_at_a_different_tip_is_flagged_not_closed(dma, jira, bb):
    jira.add_issue("T-1", AWAITING, labels=["area:api"], comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1", source_tip=OTHER)

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == AWAITING, "a stale merge must not close the task"
    assert "stale-merge" in jira.labels_of("T-1") and "area:api" in jira.labels_of("T-1")
    assert "stale tip" in jira.comments_of("T-1")[-1]


def test_merge_without_recorded_tip_closes_with_a_note(dma, jira, bb):
    jira.add_issue("T-1", AWAITING, comments=["some earlier comment"])
    merged_pr(bb, 1, "T-1")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"
    assert "no approved-tip recorded" in jira.comments_of("T-1")[-1]


def test_newest_approved_tip_wins(dma, jira, bb):
    """A task bounced by the user is reviewed again — the later approval is the one
    that must be verified."""
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {OTHER}", f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1", source_tip=APPROVED)

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"


def test_squash_merge_cannot_be_verified_and_says_so(dma, jira, bb):
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1", source_tip=None)      # single-parent commit

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"
    assert "could not be determined" in jira.comments_of("T-1")[-1]


# ------------------------------------------------------------------ declined

def test_declined_returns_the_task_to_dev_with_the_reason(dma, jira, bb):
    jira.add_issue("T-2", AWAITING, labels=["area:api"])
    bb.add_pr(2, "ai/T-2", "DECLINED", description="needs rework")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-2") == "To Do"
    assert jira.labels_of("T-2") == ["area:api", "agent:dev"]
    comment = jira.comments_of("T-2")[-1]
    assert comment.startswith("🤖 user (decline) via PR") and "needs rework" in comment


def test_declined_carries_inline_comments_with_file_and_line(dma, jira, bb):
    jira.add_issue("T-2", AWAITING)
    bb.add_pr(2, "ai/T-2", "DECLINED", description="see inline",
              comments=[{"raw": "wrong guard", "inline": {"path": "api/routes.py", "to": 42}},
                        {"raw": "general note", "inline": None}])

    result = dma()
    assert result.returncode == 0, result.stderr
    comment = jira.comments_of("T-2")[-1]
    assert "[api/routes.py:42] wrong guard" in comment and "general note" in comment


def test_declined_without_any_text_is_left_for_the_user(dma, jira, bb):
    jira.add_issue("T-2", AWAITING, labels=["area:api"])
    bb.add_pr(2, "ai/T-2", "DECLINED", description="")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert "NEEDS-INPUT T-2" in result.stdout
    assert jira.status_of("T-2") == AWAITING and jira.wrote_to("T-2") == []


# ------------------------------------------------------------------ which PR decides

def test_a_stale_declined_pr_does_not_bounce_a_resubmitted_task(dma, jira, bb):
    """The task was declined once, reworked, and merged through a second PR. The old
    DECLINED PR stays declined in Bitbucket forever and must not win."""
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    bb.add_pr(1, "ai/T-1", "DECLINED", description="first attempt rejected",
              updated="2026-08-01T10:00:00+00:00")
    merged_pr(bb, 2, "T-1", updated="2026-08-09T10:00:00+00:00")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"
    assert "agent:dev" not in jira.labels_of("T-1")


def test_an_open_pr_after_a_decline_is_left_alone(dma, jira, bb):
    jira.add_issue("T-1", AWAITING)
    bb.add_pr(1, "ai/T-1", "DECLINED", description="first attempt rejected",
              updated="2026-08-01T10:00:00+00:00")
    bb.add_pr(2, "ai/T-1", "OPEN", updated="2026-08-09T10:00:00+00:00")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert "waiting T-1" in result.stdout
    assert jira.status_of("T-1") == AWAITING and jira.wrote_to("T-1") == []


def test_task_without_a_pull_request_is_reported_not_touched(dma, jira, bb):
    jira.add_issue("T-1", AWAITING)
    result = dma()
    assert result.returncode == 0, result.stderr
    assert "waiting T-1: no pull request on ai/T-1" in result.stdout
    assert jira.wrote_to("T-1") == []


def test_only_tasks_in_awaiting_merge_are_visited(dma, jira, bb):
    jira.add_issue("T-1", "In Progress")
    jira.add_issue("T-2", "Done")
    merged_pr(bb, 1, "T-1")
    merged_pr(bb, 2, "T-2", merge_sha="e" * 40)

    result = dma()
    assert result.returncode == 0, result.stderr
    assert "0 task(s)" in result.stdout
    assert jira.writes() == [], "the pre-flight must not walk the merge history"


def test_task_transitioned_between_the_query_and_the_visit_is_skipped(dma, jira, bb):
    """The JQL index lags: a task can leave awaiting_merge between the search and
    the per-task fetch."""
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1")
    # emulate the lag: the search still lists T-1, the issue itself is already Done
    original = jira.search_payload

    def stale_search(jql, limit=50):
        payload = original(jql, limit)
        if AWAITING in jql:
            payload["issues"] = [{"key": "T-1", "fields": {"status": {"name": AWAITING}}}]
            jira.issues["T-1"]["status"] = "Done"
        return payload

    jira.search_payload = stale_search

    result = dma()
    assert result.returncode == 0, result.stderr
    assert "skip T-1" in result.stdout
    assert jira.wrote_to("T-1") == []


# ------------------------------------------------------------------ group close-out

def test_last_child_merged_promotes_the_group(dma, jira, bb):
    jira.add_issue("E-1", "In Progress", labels=["area:api"])
    jira.add_issue("T-1", AWAITING, parent=("E-1", "Epic"), comments=[f"Approved tip: {APPROVED}"])
    jira.add_issue("T-9", "Done", parent=("E-1", "Epic"))
    merged_pr(bb, 1, "T-1")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("E-1") == "Code Review"
    assert jira.labels_of("E-1") == ["area:api", "agent:team-lead"]


def test_group_stays_open_while_a_sibling_is_unfinished(dma, jira, bb):
    jira.add_issue("E-1", "In Progress")
    jira.add_issue("T-1", AWAITING, parent=("E-1", "Epic"), comments=[f"Approved tip: {APPROVED}"])
    jira.add_issue("T-9", "In Progress", parent=("E-1", "Epic"))
    merged_pr(bb, 1, "T-1")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"
    assert jira.status_of("E-1") == "In Progress" and jira.wrote_to("E-1") == []


def test_close_out_survives_the_index_still_listing_the_merged_child(dma, jira, bb):
    """The child is transitioned to Done and the sibling query runs a moment later;
    Jira's index can still report the child as open. The query excludes it by key."""
    jira.add_issue("E-1", "In Progress")
    jira.add_issue("T-1", AWAITING, parent=("E-1", "Epic"), comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1")
    original = jira.search_payload

    def lagging_search(jql, limit=50):
        if "parent = E-1" in jql:
            jira.issues["T-1"]["status"] = AWAITING      # index has not caught up
            payload = original(jql, limit)
            jira.issues["T-1"]["status"] = "Done"
            return payload
        return original(jql, limit)

    jira.search_payload = lagging_search

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("E-1") == "Code Review", "close-out must not lose to index lag"


def test_parent_that_is_not_a_group_is_not_promoted(dma, jira, bb):
    jira.add_issue("T-0", "In Progress")
    jira.add_issue("T-1", AWAITING, parent=("T-0", "Task"), comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.wrote_to("T-0") == []


# ------------------------------------------------------------------ failures / environment

def test_one_failing_task_does_not_stop_the_others(dma, jira, bb):
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    jira.add_issue("T-2", AWAITING, labels=["area:api"])
    merged_pr(bb, 1, "T-1")
    bb.add_pr(2, "ai/T-2", "DECLINED", description="needs rework")
    jira.reject_transitions.add("41")            # the Done transition is refused

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == AWAITING, "failed task stays put for the next pre-flight"
    assert jira.status_of("T-2") == "To Do", "the other task is still reconciled"


def test_a_transport_failure_on_one_task_does_not_stop_the_others(dma, jira, bb):
    """Not every failure is a tracker rejection — a 500 from the VCS host on one
    task must still leave the rest of the pre-flight running."""
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    jira.add_issue("T-2", AWAITING, labels=["area:api"])
    merged_pr(bb, 1, "T-1")
    bb.add_pr(2, "ai/T-2", "DECLINED", description="needs rework")
    bb.fail_paths["/commit/"] = 500

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == AWAITING, "unverifiable task stays put"
    assert jira.status_of("T-2") == "To Do", "the other task is still reconciled"


def test_missing_done_transition_id_skips_without_writing(dma, jira, bb, project):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("done: 41", "done: 0"))
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    merged_pr(bb, 1, "T-1")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert "transitions.done" in result.stdout
    assert jira.status_of("T-1") == AWAITING and jira.wrote_to("T-1") == []


def test_a_linear_project_without_a_key_says_where_to_put_one(dma, jira, bb, project):
    """Linear is supported now; reconcile needs a key and a team key to reach it."""
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("provider: jira", "provider: linear") + "\n  team_key: T\n")
    result = dma()
    assert result.returncode == 1
    assert "LINEAR_API_KEY" in result.stderr
    assert jira.requests == [] and bb.requests == []


def test_an_unknown_provider_exits_2_so_the_agent_falls_back(dma, jira, bb, project):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("provider: jira", "provider: youtrack"))
    result = dma()
    assert result.returncode == 2
    assert jira.requests == [] and bb.requests == []


def test_pagination_is_followed(dma, jira, bb):
    """Bitbucket answers 50 PRs per page and the branch may carry more than one."""
    bb.page_size = 1
    jira.add_issue("T-1", AWAITING, comments=[f"Approved tip: {APPROVED}"])
    bb.add_pr(1, "ai/T-1", "DECLINED", description="old", updated="2026-08-01T10:00:00+00:00")
    merged_pr(bb, 2, "T-1", updated="2026-08-09T10:00:00+00:00")

    result = dma()
    assert result.returncode == 0, result.stderr
    assert jira.status_of("T-1") == "Done"
    assert sum(1 for r in bb.requests if "pullrequests?" in r) >= 2, "second page must be fetched"


# ------------------------------------------------------------------ list

@pytest.fixture
def board(jira):
    jira.issues.clear()
    return jira


def dma_list(project, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run([DMA, "board", "list", *args], capture_output=True, text=True, env=env)


def test_list_filters_by_status_and_label(project, board):
    board.add_issue("T-1", "To Do", labels=["agent:dev", "area:api"])
    board.add_issue("T-2", "To Do", labels=["agent:qa"])
    board.add_issue("T-3", "Done", labels=["agent:dev"])

    result = dma_list(project, "--status", "To Do", "--label", "agent:dev")
    assert result.returncode == 0, result.stderr
    assert "1 issue(s)" in result.stdout
    assert "T-1" in result.stdout and "T-2" not in result.stdout and "T-3" not in result.stdout


def test_list_shows_status_labels_and_summary(project, board):
    board.add_issue("T-1", "QA", labels=["agent:qa", "area:api"])
    out = dma_list(project, "--status", "QA").stdout
    assert "T-1" in out and "QA" in out and "agent:qa" in out and "area:api" in out


def test_list_by_type_group_returns_only_epics(project, board):
    board.add_issue("T-1", "Code Review", labels=["agent:team-lead"], kind="Epic")
    board.add_issue("T-2", "Code Review", labels=["agent:reviewer"])
    result = dma_list(project, "--type", "group")
    assert result.returncode == 0, result.stderr
    assert "T-1" in result.stdout and "T-2" not in result.stdout


def test_list_by_parent_returns_the_children(project, board):
    board.add_issue("T-9", "In Progress", kind="Epic")
    board.add_issue("T-1", "Done", parent=("T-9", "Epic"))
    board.add_issue("T-2", "To Do")
    result = dma_list(project, "--parent", "T-9")
    assert result.returncode == 0, result.stderr
    assert "T-1" in result.stdout and "T-2" not in result.stdout


def test_list_of_an_empty_selection_says_so(project, board):
    result = dma_list(project, "--status", "On Hold")
    assert result.returncode == 0, result.stderr
    assert "0 issue(s)" in result.stdout


def test_list_rejects_an_unknown_filter(project, board):
    result = dma_list(project, "--assignee", "me")
    assert result.returncode == 1
    assert "usage:" in result.stderr


def test_list_on_a_linear_project_needs_a_key(project, board):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("provider: jira", "provider: linear") + "\n  team_key: T\n")
    result = dma_list(project, "--status", "To Do")
    assert result.returncode == 1
    assert "LINEAR_API_KEY" in result.stderr
    assert board.requests == []


def test_list_on_an_unknown_provider_exits_2(project, board):
    config = project / ".claude" / "dma" / "config.yml"
    config.write_text(config.read_text().replace("provider: jira", "provider: youtrack"))
    result = dma_list(project, "--status", "To Do")
    assert result.returncode == 2
    assert board.requests == []


def test_list_says_when_the_result_is_truncated(project, board):
    """A capped listing that looks complete would hide half the board."""
    for n in range(50):
        board.add_issue(f"T-{n}", "To Do")
    result = dma_list(project, "--status", "To Do")
    assert result.returncode == 0, result.stderr
    assert "truncated" in result.stdout


# ------------------------------------------------------------------ remote URL forms

@pytest.mark.parametrize("url", [
    "git@bitbucket.org:officejet/some-repo.git",
    "https://bitbucket.org/officejet/some-repo.git",
    "https://user@bitbucket.org/officejet/some-repo.git",
    "https://x-token-auth:ATCTT3xFfGN0vMi6UVMrpE_TzTeFKSE@bitbucket.org/officejet/some-repo.git",
    "https://bitbucket.org/officejet/some-repo",
])
def test_bitbucket_coordinates_are_read_from_every_url_form(url):
    """Including the credential-bearing form a token-authenticated clone carries."""
    import vcs
    assert vcs.split_remote(url, "bitbucket.org") == ("officejet", "some-repo")


@pytest.mark.parametrize("url", [
    "git@github.com:xvpn/some-repo.git",
    "https://github.com/xvpn/some-repo.git",
    "https://x-access-token:ghs_abc123@github.com/xvpn/some-repo.git",
    "https://github.com/xvpn/some-repo",
])
def test_github_coordinates_are_read_from_every_url_form(url):
    import vcs
    assert vcs.split_remote(url, "github.com") == ("xvpn", "some-repo")


def test_a_remote_on_an_unknown_host_is_declined_not_guessed(tmp_path):
    import vcs
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin",
                    "git@gitlab.com:group/repo.git"], check=True)
    with pytest.raises(vcs.Unsupported):
        vcs.open_vcs(str(tmp_path), str(tmp_path / ".mcp.json"))
