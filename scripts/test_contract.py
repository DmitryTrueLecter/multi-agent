"""Contract tests: do the real Jira / Bitbucket APIs still answer what the code assumes?

The fake-server tests in test_issue.py / test_board.py check decision logic.
They cannot catch an endpoint that was removed or a payload that changed shape —
the fake was written from the same assumptions as the code. These tests call the
real APIs through the real client classes. Read-only: GET requests only, no writes.

    DMA_CONTRACT_PROJECT=~/work/data-exposure-scan .venv/bin/pytest scripts/test_contract.py

Skipped when DMA_CONTRACT_PROJECT is unset, so the default suite stays offline.
Every assertion below mirrors a field the code actually reads — when one fails,
production is already broken.
"""

import os
import re

import pytest

import board
import issue
import vcs

PROJECT = os.path.expanduser(os.environ.get("DMA_CONTRACT_PROJECT", ""))
pytestmark = pytest.mark.skipif(not PROJECT, reason="set DMA_CONTRACT_PROJECT=<path to a live project>")

SHA40 = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(scope="module", autouse=True)
def project_dir():
    """issue.py resolves config/credentials at import time from module constants."""
    issue.PROJECT_DIR = PROJECT
    issue.CONFIG_PATH = os.path.join(PROJECT, ".claude", "dma", "config.yml")
    issue.MCP_PATH = os.path.join(PROJECT, ".mcp.json")
    board.issue = issue


@pytest.fixture(scope="module")
def config():
    return issue.load_config()


@pytest.fixture(scope="module")
def jira():
    return issue.Jira(*issue.load_credentials())


@pytest.fixture(scope="module")
def bitbucket(config):
    remote = ((config.get("workspace") or {}) or {}).get("remote", "origin")
    return vcs.open_vcs(PROJECT, issue.MCP_PATH, remote)


@pytest.fixture(scope="module")
def merged_pr(bitbucket, config):
    """A real merged pull request produced by this system — the input every
    pre-flight walks. Found by asking for the branch of a task that reached done."""
    prefix = config["vcs"]["branch_prefix"]
    jira = issue.Jira(*issue.load_credentials())
    done = config["tasks"]["workflow"]["statuses"]["done"]
    rows = jira.search(f'project = {config["tasks"]["project_key"]} AND status = "{done}" '
                       f'ORDER BY updated DESC', fields="summary")
    for row in rows[:20]:
        for pr in bitbucket.pull_requests_for_branch(f"{prefix}{row['key']}"):
            if pr["state"] == "MERGED" and pr.get("_merge_commit"):
                return pr
    pytest.skip("no managed merged pull request in this repository")


# ------------------------------------------------------------------ jira

def test_get_issue_returns_the_fields_the_code_reads(jira, merged_pr, config):
    key = merged_pr["branch"][len(config["vcs"]["branch_prefix"]):]
    fields = jira.get_issue(key)["fields"]
    assert isinstance(fields["status"]["name"], str)
    assert isinstance(fields.get("labels"), list)
    assert "comment" in fields and isinstance(fields["comment"]["comments"], list)
    parent = fields.get("parent")
    if parent:
        assert parent["fields"]["issuetype"]["name"], "close_out_parent reads parent.fields.issuetype.name"


def test_comments_endpoint_supports_newest_first_ordering(jira, merged_pr, config):
    key = merged_pr["branch"][len(config["vcs"]["branch_prefix"]):]
    comments = jira.get_comments(key)
    if len(comments) < 2:
        pytest.skip("issue has fewer than two comments")
    created = [c["created"] for c in comments]
    assert created == sorted(created, reverse=True), "approved_tip() takes the first match as the newest"


def test_search_endpoint_is_reachable(jira):
    """close_out_parent's sibling query. A removed endpoint fails the whole Epic
    close-out *after* the child is already done, so the retry never revisits it."""
    assert jira.search("created >= -1d ORDER BY created DESC") is not None


# ------------------------------------------------------------------ bitbucket

def test_pull_request_listing_carries_the_fields_the_code_reads(merged_pr):
    assert merged_pr["branch"] and merged_pr["destination"]
    assert merged_pr["url"].startswith("http")
    assert "description" in merged_pr, "rejection_text reads it straight off the listing"


def test_merge_source_tip_is_a_full_sha(bitbucket, merged_pr):
    """It is compared against a 40-char 'Approved tip:' line; a short hash here
    would flag every clean merge as stale."""
    tip = bitbucket.merge_source_tip(merged_pr)
    assert tip and SHA40.match(tip), f"expected a 40-char sha, got {tip}"


def test_listing_paginates_beyond_one_page(bitbucket):
    """Production has several pages of merged pull requests; the fake never
    returns `next`, so this loop is otherwise unexercised."""
    everything = bitbucket.paginate(bitbucket._repo("/pullrequests?state=MERGED&pagelen=50"))
    first_page = bitbucket.call(bitbucket._repo("/pullrequests?state=MERGED&pagelen=50"))
    if not first_page.get("next"):
        pytest.skip("repository has a single page of merged pull requests")
    assert len(everything) > len(first_page["values"]), "pagination must follow `next`"
