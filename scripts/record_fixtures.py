#!/usr/bin/env python3
"""Record real Jira / Bitbucket responses into scripts/fixtures/ for the fake servers.

The fakes in the test suite must not be shaped by guesswork — a hand-written
payload encodes the same assumptions as the code it is meant to check. These
fixtures are captured from a live project, then redacted: the structure is real,
every identifying or free-text value is replaced with a placeholder.

    DMA_CONTRACT_PROJECT=~/work/some-project python3 scripts/record_fixtures.py

Read-only (GET requests). Re-run when an API changes; scripts/test_contract.py is
what tells you that it did.
"""

import copy
import json
import os
import re
import sys
import urllib.parse

import issue
import board

FIXTURES = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures")

# Values that identify a person, a repository, or carry free text. The key
# structure around them is kept exactly as the API returned it.
REDACT_KEYS = {
    "summary", "description", "title", "raw", "html", "body", "markup",
    "display_name", "displayName", "nickname", "emailAddress", "account_id",
    "accountId", "uuid", "avatarUrls", "avatar", "links", "self", "href",
    "author", "user", "closed_by", "updateAuthor", "reason", "rendered",
    "participants", "reviewers", "repository", "workspace", "project", "iconUrl",
}
SHA_RE = re.compile(r"\b[0-9a-f]{12,40}\b")


def redact(node, issue_keys, shas):
    """Keep every key and container type; replace identifying leaf values."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in ("links",):
                out[key] = {"html": {"href": "https://bitbucket.org/testws/testrepo/pull-requests/1"}}
            elif key in ("summary", "description", "raw", "body", "title") and isinstance(value, str):
                out[key] = "REDACTED TEXT"
            elif key in ("summary", "description") and isinstance(value, dict):
                out[key] = redact(value, issue_keys, shas)
            elif key in REDACT_KEYS and isinstance(value, str):
                out[key] = "REDACTED"
            elif key in REDACT_KEYS and isinstance(value, (dict, list)):
                out[key] = {"display_name": "REDACTED"} if isinstance(value, dict) else []
            else:
                out[key] = redact(value, issue_keys, shas)
        return out
    if isinstance(node, list):
        return [redact(item, issue_keys, shas) for item in node]
    if isinstance(node, str):
        for real, fake in issue_keys.items():
            node = node.replace(real, fake)
        for real, fake in shas.items():
            node = node.replace(real, fake)
        # any commit hash not explicitly mapped above still leaves the repository
        return SHA_RE.sub(lambda m: "d" * len(m.group(0)), node)
    return node


def write(name, payload):
    os.makedirs(FIXTURES, exist_ok=True)
    path = os.path.join(FIXTURES, name)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {path}")


def main():
    project = os.path.expanduser(os.environ.get("DMA_CONTRACT_PROJECT", ""))
    if not project:
        print("set DMA_CONTRACT_PROJECT=<path to a live project>", file=sys.stderr)
        return 1
    issue.PROJECT_DIR = project
    issue.CONFIG_PATH = os.path.join(project, ".claude", "dma", "config.yml")
    issue.MCP_PATH = os.path.join(project, ".mcp.json")

    config = issue.load_config()
    prefix = config["vcs"]["branch_prefix"]
    project_key = config["tasks"]["project_key"]
    jira = issue.Jira(*issue.load_credentials())
    bb = board.Bitbucket(*board.load_bitbucket_credentials())
    remote = ((config.get("workspace") or {}) or {}).get("remote", "origin")
    workspace, repo = board.derive_coords(board.git_remote_url(remote))

    # A merged PR produced by this system, with a real merge commit.
    merged = None
    for pr in bb.list_pull_requests(workspace, repo, "MERGED"):
        if board.is_managed(pr, f"{prefix}{project_key}-") and (pr.get("merge_commit") or {}).get("hash"):
            merged = pr
            break
    if not merged:
        print("no managed merged PR to record from", file=sys.stderr)
        return 1

    key = board.key_from_branch(merged["source"]["branch"]["name"], prefix)
    issue_payload = jira.get_issue(key)
    parent = (issue_payload["fields"].get("parent") or {}).get("key")
    commit = bb.get_commit(workspace, repo, merged["merge_commit"]["hash"])
    parents = [p["hash"] for p in commit.get("parents", [])]

    # Stable placeholders: real ids never reach the repository.
    issue_keys = {key: "T-1"}
    if parent:
        issue_keys[parent] = "E-1"
    shas = {}
    if len(parents) > 1:
        shas[parents[0]] = "b" * 40
        shas[parents[1]] = "a" * 40
    shas[commit["hash"]] = "c" * 40
    shas[merged["merge_commit"]["hash"]] = "c" * 40
    branch_map = {merged["source"]["branch"]["name"]: f"{prefix}T-1"}

    def clean(payload):
        out = redact(copy.deepcopy(payload), issue_keys, shas)
        text = json.dumps(out)
        for real, fake in branch_map.items():
            text = text.replace(real, fake)
        return json.loads(text)

    write("jira_issue.json", clean(issue_payload))
    write("jira_comments.json", clean({"comments": jira.get_comments(key)}))
    write("jira_search.json", clean(jira.search_raw(f"project = {project_key} ORDER BY created DESC", max_results=2)))
    write("bitbucket_pullrequests.json", clean({"values": [merged], "pagelen": 50, "page": 1}))
    write("bitbucket_commit.json", clean(commit))
    comments = bb.list_pull_request_comments(workspace, repo, merged["id"])
    write("bitbucket_pr_comments.json", clean({"values": comments[:5]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
