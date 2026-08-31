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

import issue
import board

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
def bitbucket():
    return board.Bitbucket(*board.load_bitbucket_credentials())


@pytest.fixture(scope="module")
def coords(config):
    remote = ((config.get("workspace") or {}) or {}).get("remote", "origin")
    return board.derive_coords(board.git_remote_url(remote))


@pytest.fixture(scope="module")
def merged_pr(bitbucket, coords, config):
    """A real merged PR produced by this system — the input every pre-flight walks."""
    workspace, repo = coords
    prefix = f"{config['vcs']['branch_prefix']}{config['tasks']['project_key']}-"
    for pr in bitbucket.list_pull_requests(workspace, repo, "MERGED"):
        if board.is_managed(pr, prefix) and (pr.get("merge_commit") or {}).get("hash"):
            return pr
    pytest.skip("no managed merged PR in this repository")


# ------------------------------------------------------------------ jira

def test_get_issue_returns_the_fields_the_code_reads(jira, merged_pr, config):
    key = board.key_from_branch(merged_pr["source"]["branch"]["name"], config["vcs"]["branch_prefix"])
    fields = jira.get_issue(key)["fields"]
    assert isinstance(fields["status"]["name"], str)
    assert isinstance(fields.get("labels"), list)
    assert "comment" in fields and isinstance(fields["comment"]["comments"], list)
    parent = fields.get("parent")
    if parent:
        assert parent["fields"]["issuetype"]["name"], "close_out_parent reads parent.fields.issuetype.name"


def test_comments_endpoint_supports_newest_first_ordering(jira, merged_pr, config):
    key = board.key_from_branch(merged_pr["source"]["branch"]["name"], config["vcs"]["branch_prefix"])
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
    assert merged_pr["source"]["branch"]["name"]
    assert merged_pr["destination"]["branch"]["name"]
    assert board.pr_url(merged_pr).startswith("http"), "links.html.href"
    # rejection_text() reads the description straight off the listing payload
    assert "summary" in merged_pr or "description" in merged_pr


def test_merge_commit_parents_are_full_shas(bitbucket, coords, merged_pr):
    """merge_source_tip() compares parents[1] against a 40-char 'Approved tip:'
    line. Short hashes here would flag every clean merge as stale."""
    workspace, repo = coords
    commit = bitbucket.get_commit(workspace, repo, merged_pr["merge_commit"]["hash"])
    parents = commit.get("parents") or []
    assert len(parents) == 2, "the merge strategy must produce two parents"
    for parent in parents:
        assert SHA40.match(parent["hash"]), f"expected a 40-char sha, got {parent['hash']}"


def test_listing_paginates_beyond_one_page(bitbucket, coords):
    """Production has several pages of merged PRs; the fake never returns `next`,
    so this loop is otherwise unexercised."""
    workspace, repo = coords
    everything = bitbucket.list_pull_requests(workspace, repo, "MERGED")
    assert len(everything) > 0
    first_page = bitbucket.call(
        f"/repositories/{workspace}/{repo}/pullrequests?state=MERGED&sort=-updated_on&pagelen=50")
    if not first_page.get("next"):
        pytest.skip("repository has a single page of merged PRs")
    assert len(everything) > len(first_page["values"]), "pagination must follow `next`"
