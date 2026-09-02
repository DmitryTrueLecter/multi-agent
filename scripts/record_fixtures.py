#!/usr/bin/env python3
"""Redact raw Jira / Bitbucket responses into scripts/fixtures/ for the fake servers.

The fakes in the test suite must not be shaped by guesswork — a hand-written
payload encodes the same assumptions as the code it is meant to check. So the
fixtures are real responses, captured from a live project and redacted: the
structure stays exactly as the API returned it, every identifying or free-text
value becomes a placeholder.

Capture is a separate step, with any HTTP client, so this script does not
depend on scripts/vcs.py or scripts/issue.py and survives their refactors. Put
the raw responses in one directory under the fixture names, then run:

    python3 scripts/record_fixtures.py <raw-dir>

Expected files — pick a MERGED pull request this system opened (branch
`<vcs.branch_prefix><ISSUE-KEY>`) with a real merge commit, and capture:

    jira_issue.json             GET /rest/api/2/issue/<KEY>?fields=summary,status,labels,parent,description,comment,issuetype,issuelinks
    jira_comments.json          GET /rest/api/2/issue/<KEY>/comment?maxResults=50&orderBy=-created
    jira_search.json            GET /rest/api/2/search/jql?jql=project%20%3D%20<PROJECT>&fields=summary,status,labels,parent&maxResults=2
    bitbucket_pullrequests.json GET /2.0/repositories/<ws>/<repo>/pullrequests?q=source.branch.name%3D%22<branch>%22&state=MERGED
    bitbucket_commit.json       GET /2.0/repositories/<ws>/<repo>/commit/<merge_commit.hash>
    bitbucket_pr_comments.json  GET /2.0/repositories/<ws>/<repo>/pullrequests/<id>/comments?pagelen=5

A file that is missing is skipped, so one API can be re-recorded on its own.
The placeholders are derived from the payloads themselves: the issue key becomes
T-1, its parent E-1, the task branch `<prefix>T-1`, the merge commit c…, its two
parents b… (destination) and a… (source); every other commit hash becomes d….
Re-run when an API changes shape; scripts/test_contract.py is what tells you it did.
"""

import copy
import json
import os
import re
import sys

FIXTURES = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures")
NAMES = ("jira_issue.json", "jira_comments.json", "jira_search.json",
         "bitbucket_pullrequests.json", "bitbucket_commit.json", "bitbucket_pr_comments.json")

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


def redact(node, replacements):
    """Keep every key and container type; replace identifying leaf values.
    `replacements` maps real strings (issue keys, branch names, hashes) to
    their placeholders; any commit hash not in it becomes d…"""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "links":
                out[key] = {"html": {"href": "https://bitbucket.org/testws/testrepo/pull-requests/1"}}
            elif key in ("summary", "description", "raw", "body", "title") and isinstance(value, str):
                out[key] = "REDACTED TEXT"
            elif key in ("summary", "description") and isinstance(value, dict):
                out[key] = redact(value, replacements)
            elif key in REDACT_KEYS and isinstance(value, str):
                out[key] = "REDACTED"
            elif key in REDACT_KEYS and isinstance(value, (dict, list)):
                out[key] = {"display_name": "REDACTED"} if isinstance(value, dict) else []
            else:
                out[key] = redact(value, replacements)
        return out
    if isinstance(node, list):
        return [redact(item, replacements) for item in node]
    if isinstance(node, str):
        for real, fake in replacements.items():
            if not SHA_RE.fullmatch(real):
                node = node.replace(real, fake)
        # Hashes go in one pass: a placeholder like c… is itself hex, and a
        # second scan would turn it into d… along with the unmapped ones.
        return SHA_RE.sub(lambda m: replacements.get(m.group(0), "d" * len(m.group(0))), node)
    return node


def placeholders(raw):
    """Stable placeholders read off the payloads: real ids never reach the
    repository. Longer strings first, so a branch is replaced before the key
    inside it."""
    out = {}
    issue = raw.get("jira_issue.json")
    key = issue["key"] if issue else None
    if key:
        out[key] = "T-1"
        parent = (issue["fields"].get("parent") or {}).get("key")
        if parent:
            out[parent] = "E-1"
    prs = (raw.get("bitbucket_pullrequests.json") or {}).get("values") or []
    if prs:
        pr = prs[0]
        branch = pr["source"]["branch"]["name"]
        if key and branch.endswith(key):
            out[branch] = branch[: -len(key)] + "T-1"
        merge = (pr.get("merge_commit") or {}).get("hash")
        if merge:
            out[merge] = "c" * 40
    commit = raw.get("bitbucket_commit.json")
    if commit:
        out[commit["hash"]] = "c" * 40
        parents = [p["hash"] for p in commit.get("parents") or []]
        if len(parents) > 1:
            out[parents[0]] = "b" * 40
            out[parents[1]] = "a" * 40
    return dict(sorted(out.items(), key=lambda kv: -len(kv[0])))


def write(name, payload):
    os.makedirs(FIXTURES, exist_ok=True)
    path = os.path.join(FIXTURES, name)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {path}")


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    raw = {}
    for name in NAMES:
        path = os.path.join(argv[1], name)
        if os.path.exists(path):
            with open(path) as f:
                raw[name] = json.load(f)
        else:
            print(f"skip (absent): {name}")
    if not raw:
        print(f"no fixture-named files in {argv[1]}", file=sys.stderr)
        return 1
    replacements = placeholders(raw)
    for name, payload in raw.items():
        write(name, redact(copy.deepcopy(payload), replacements))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
