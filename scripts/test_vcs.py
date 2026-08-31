"""Tests for `scripts/vcs.py` — one pull-request shape over two hosts.

The Bitbucket half runs against the fake built from recorded payloads. The GitHub
half is exercised through `gh api`, replaced here by a stub on PATH that answers
from a file: it is the same code path production takes when `gh` is installed,
without a network or a token.

Run:  .venv/bin/pytest scripts/
"""

import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
import sys
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import fakes
import vcs


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def add_remote(repo, url):
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)


# ------------------------------------------------------------------ bitbucket

@pytest.fixture
def bitbucket(repo):
    fake = fakes.FakeBitbucket()
    add_remote(repo, "git@bitbucket.org:testws/testrepo.git")
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"atlassian": {"env": {
        "BITBUCKET_URL": fake.url, "BITBUCKET_USERNAME": "u", "BITBUCKET_APP_PASSWORD": "p"}}}}))
    host = vcs.open_vcs(str(repo), str(repo / ".mcp.json"))
    yield fake, host
    fake.shutdown()


def test_bitbucket_pull_requests_come_back_in_the_common_shape(bitbucket):
    fake, host = bitbucket
    fake.add_pr(1, "ai/T-1", "MERGED", dest="dev", merge_sha="c" * 40, description="why")
    pr = host.pull_requests_for_branch("ai/T-1")[0]
    assert pr["id"] == 1 and pr["state"] == "MERGED"
    assert pr["branch"] == "ai/T-1" and pr["destination"] == "dev"
    assert pr["description"] == "why" and pr["url"].startswith("http")


def test_bitbucket_newest_pull_request_comes_first(bitbucket):
    fake, host = bitbucket
    fake.add_pr(1, "ai/T-1", "DECLINED", updated="2026-08-01T10:00:00+00:00")
    fake.add_pr(2, "ai/T-1", "MERGED", updated="2026-08-09T10:00:00+00:00", merge_sha="c" * 40)
    assert [pr["id"] for pr in host.pull_requests_for_branch("ai/T-1")] == [2, 1]


def test_bitbucket_merge_source_tip_is_the_second_parent(bitbucket):
    fake, host = bitbucket
    fake.add_pr(1, "ai/T-1", "MERGED", merge_sha="c" * 40)
    fake.add_commit("c" * 40, ["b" * 40, "a" * 40])
    assert host.merge_source_tip(host.pull_requests_for_branch("ai/T-1")[0]) == "a" * 40


def test_bitbucket_squash_merge_has_no_source_tip(bitbucket):
    fake, host = bitbucket
    fake.add_pr(1, "ai/T-1", "MERGED", merge_sha="c" * 40)
    fake.add_commit("c" * 40, ["b" * 40])
    assert host.merge_source_tip(host.pull_requests_for_branch("ai/T-1")[0]) is None


def test_bitbucket_comments_keep_the_inline_location(bitbucket):
    fake, host = bitbucket
    fake.add_pr(1, "ai/T-1", "DECLINED", comments=[
        {"raw": "wrong guard", "inline": {"path": "api/routes.py", "to": 42}},
        {"raw": "general note", "inline": None}])
    comments = host.comments(host.pull_requests_for_branch("ai/T-1")[0])
    assert comments[0]["inline"]["path"] == "api/routes.py"
    assert comments[1]["inline"] is None


def test_bitbucket_opens_a_pull_request(bitbucket):
    fake, host = bitbucket
    url = host.create_pull_request("ai/T-1", "dev", "T-1 title", "body")
    assert url.startswith("http")
    assert fake.created[0]["source"]["branch"]["name"] == "ai/T-1"
    assert fake.created[0]["destination"]["branch"]["name"] == "dev"


# --------------------------------------------------------------------- github

@pytest.fixture
def github(repo, monkeypatch):
    """A stub `gh` on PATH that answers from files — the same path production
    takes when the real `gh` is installed."""
    bin_dir = repo / "bin"
    bin_dir.mkdir()
    answers = repo / "answers"
    answers.mkdir()
    (bin_dir / "gh").write_text(
        "#!/bin/sh\n"
        'shift 2\n'                       # drop "api -X"
        'method=$1; shift\n'
        'path=$(echo "$1" | tr "/?=&:" "_____")\n'
        f'if [ "$method" != GET ]; then cat > {answers}/last_body.json; fi\n'
        f'cat {answers}/"$path".json\n')
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    add_remote(repo, "git@github.com:xvpn/some-repo.git")
    (repo / ".mcp.json").write_text("{}")
    return repo, answers, vcs.open_vcs(str(repo), str(repo / ".mcp.json"))


def answer(answers, path, payload):
    """Names the file exactly as the stub `gh` will: the client's own path, with
    the separators flattened."""
    name = path
    for char in "/?=&:":
        name = name.replace(char, "_")
    (answers / f"{name}.json").write_text(json.dumps(payload))


PULLS = ("repos/xvpn/some-repo/pulls?head=xvpn%3Aai%2FT-1&state=all&sort=updated"
         "&direction=desc&per_page=50")


def test_github_closed_pull_request_reads_as_declined(github):
    repo, answers, host = github
    answer(answers, PULLS,
           [{"number": 7, "state": "closed", "merged_at": None, "html_url": "https://github.com/x/7",
             "head": {"ref": "ai/T-1"}, "base": {"ref": "main"}, "updated_at": "2026-08-01T10:00:00Z",
             "body": "no", "merge_commit_sha": None}])
    pr = host.pull_requests_for_branch("ai/T-1")[0]
    assert pr["state"] == "DECLINED", "GitHub says CLOSED; the rules are written against DECLINED"
    assert pr["id"] == 7 and pr["destination"] == "main"


def test_github_merged_pull_request_reads_as_merged(github):
    repo, answers, host = github
    answer(answers, PULLS,
           [{"number": 8, "state": "closed", "merged_at": "2026-08-09T10:00:00Z",
             "html_url": "https://github.com/x/8", "head": {"ref": "ai/T-1"}, "base": {"ref": "main"},
             "updated_at": "2026-08-09T10:00:00Z", "body": "", "merge_commit_sha": "c" * 40}])
    assert host.pull_requests_for_branch("ai/T-1")[0]["state"] == "MERGED", \
        "a closed pull request that was merged is not a decline"


def test_github_merge_source_tip_is_the_second_parent(github):
    repo, answers, host = github
    answer(answers, f"repos/xvpn/some-repo/commits/{'c' * 40}",
           {"parents": [{"sha": "b" * 40}, {"sha": "a" * 40}]})
    assert host.merge_source_tip({"_merge_commit": "c" * 40}) == "a" * 40


# ------------------------------------------------------------------ dma pr open

DMA = os.path.join(ROOT, "bin", "dma")


def run_dma(repo, *args, **env):
    return subprocess.run([DMA, "pr", *args], capture_output=True, text=True,
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(repo), **env})


def test_pr_open_prints_the_url_the_caller_needs(bitbucket, repo):
    fake, _ = bitbucket
    (repo / ".claude" / "dma").mkdir(parents=True)
    (repo / ".claude" / "dma" / "config.yml").write_text("tasks:\n  provider: jira\n  project_key: T\n")
    result = run_dma(repo, "open", "ai/T-1", "dev", "T-1 title", "--body", "why")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("http")
    assert fake.created[0]["title"] == "T-1 title"
    assert fake.created[0]["description"] == "why"


def test_pr_open_takes_a_multi_line_body_on_stdin(bitbucket, repo):
    """A review summary carries tables and pipes; passing it inline would be
    tokenized by the shell."""
    fake, _ = bitbucket
    (repo / ".claude" / "dma").mkdir(parents=True)
    (repo / ".claude" / "dma" / "config.yml").write_text("tasks:\n  provider: jira\n  project_key: T\n")
    body = "| col | col |\n|---|---|\n| a | b |"
    result = subprocess.run([DMA, "pr", "open", "ai/T-1", "dev", "T-1", "--body", "-"],
                            input=body, capture_output=True, text=True,
                            env={**os.environ, "CLAUDE_PROJECT_DIR": str(repo)})
    assert result.returncode == 0, result.stderr
    assert fake.created[0]["description"] == body


def test_pr_open_on_an_unknown_host_exits_2(repo):
    add_remote(repo, "git@gitlab.com:group/repo.git")
    (repo / ".claude" / "dma").mkdir(parents=True)
    (repo / ".claude" / "dma" / "config.yml").write_text("tasks:\n  provider: jira\n  project_key: T\n")
    result = run_dma(repo, "open", "ai/T-1", "dev", "T-1")
    assert result.returncode == 2
    assert "gitlab" in result.stderr
