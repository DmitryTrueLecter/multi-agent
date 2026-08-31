"""Board-wide operations: everything that searches the board instead of naming one issue.

    dma board reconcile          apply the user's merge/decline decisions to the tracker
    dma board list [filters]     search the board (status / label / parent / type)

`reconcile` is the pre-flight run before every agent dispatch.

Driven from the tracker, not from the pull-request history: the only tasks whose
state can change are the ones sitting in `awaiting_merge`, so one JQL finds them
and each is matched to the newest pull request on its branch. (Walking every
merged PR instead costs a Jira round-trip per PR ever merged — 69 of them on a
half-year-old repository — and re-processes a task's stale DECLINED pull request
every time it comes back to `awaiting_merge` on a later attempt.)

Per task, by the state of the newest PR on `<vcs.branch_prefix><KEY>`:

  · OPEN / none → nothing to do, the user has not decided yet
  · DECLINED    → label agent:dev, status → to_do, comment with the rejection text
  · MERGED      → verify the merged tip against the recorded "Approved tip:" line;
                  stale → label stale-merge, stay in awaiting_merge;
                  clean → status → done, comment; close out the parent group when
                  the last child merges (parent → agent:team-lead, code_review).

Project root = $CLAUDE_PROJECT_DIR, else the current directory. Reads
<project>/.claude/dma/config.yml and credentials from <project>/.mcp.json →
mcpServers.atlassian.env (JIRA_* and BITBUCKET_URL, BITBUCKET_USERNAME,
BITBUCKET_APP_PASSWORD), falling back to the environment.

Only provider "jira" (with a Bitbucket remote) is implemented. For "linear" the
command exits 2 and the agent falls back to the /dma:pr-feedback skill.

Failure policy from the skill: one task that fails is logged and skipped, the run
continues, the next pre-flight retries. A declined PR with no rejection text is
surfaced (NEEDS-INPUT) and left untouched — asking the user is not the script's call.

Exit codes: 0 ok · 1 error · 2 provider/remote not supported
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import issue

APPROVED_TIP_RE = re.compile(r"^Approved tip: ([0-9a-f]{40})$", re.MULTILINE)
TEXT_CAP = 3000
# Every state a decided or pending PR can be in; the newest one wins.
PR_STATES = ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")


# ----------------------------------------------------------------- bitbucket creds / http

def load_bitbucket_credentials():
    creds = {}
    if os.path.exists(issue.MCP_PATH):
        with open(issue.MCP_PATH) as f:
            creds = json.load(f).get("mcpServers", {}).get("atlassian", {}).get("env", {})
    url = creds.get("BITBUCKET_URL") or os.environ.get("BITBUCKET_URL") or "https://bitbucket.org"
    user = creds.get("BITBUCKET_USERNAME") or os.environ.get("BITBUCKET_USERNAME")
    token = creds.get("BITBUCKET_APP_PASSWORD") or os.environ.get("BITBUCKET_APP_PASSWORD")
    if not (user and token):
        issue.die(
            "Bitbucket credentials not found: need BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD "
            f"in {issue.MCP_PATH} (mcpServers.atlassian.env) or in the environment"
        )
    return api_base(url), user, token


def api_base(bitbucket_url):
    """Cloud REST lives on api.bitbucket.org/2.0; the configured URL is the web host.
    A non-Cloud base (e.g. a test server) is used verbatim with /2.0 appended."""
    base = bitbucket_url.rstrip("/")
    if "bitbucket.org" in base and "api." not in base:
        return "https://api.bitbucket.org/2.0"
    if base.endswith("/2.0"):
        return base
    return base + "/2.0"


class Bitbucket:
    def __init__(self, base, user, token):
        self.base = base
        self.auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

    def call(self, path):
        url = path if path.startswith("http") else self.base + path
        request = urllib.request.Request(url, method="GET")
        request.add_header("Authorization", self.auth)
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            raise BitbucketError(e.code, e.read().decode(errors="replace"))
        return json.loads(raw) if raw else None

    def paginate(self, path, max_pages=20):
        """Bitbucket returns `next` as an absolute URL; follow it until exhausted."""
        results, pages = [], 0
        while path and pages < max_pages:
            page = self.call(path)
            results.extend(page.get("values") or [])
            path = page.get("next")
            pages += 1
        if path:
            print(f"WARNING pull-request listing capped at {max_pages} pages", file=sys.stderr)
        return results

    def pull_requests_for_branch(self, workspace, repo, branch, states=PR_STATES):
        """Every PR opened from `branch`, newest first."""
        params = [("q", f'source.branch.name="{branch}"')]
        params += [("state", state) for state in states]
        params += [("sort", "-updated_on"), ("pagelen", 50)]
        path = f"/repositories/{workspace}/{repo}/pullrequests?{urllib.parse.urlencode(params)}"
        found = self.paginate(path)
        return sorted(found, key=lambda pr: pr.get("updated_on") or "", reverse=True)

    def list_pull_requests(self, workspace, repo, state):
        """Whole-repository listing — used by the fixture recorder and the contract
        tests, not by reconciliation."""
        query = urllib.parse.urlencode({"state": state, "sort": "-updated_on", "pagelen": 50})
        return self.paginate(f"/repositories/{workspace}/{repo}/pullrequests?{query}")

    def get_commit(self, workspace, repo, sha):
        return self.call(f"/repositories/{workspace}/{repo}/commit/{sha}")

    def list_pull_request_comments(self, workspace, repo, pr_id):
        return self.paginate(f"/repositories/{workspace}/{repo}/pullrequests/{pr_id}/comments?pagelen=50",
                             max_pages=10)


class BitbucketError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Bitbucket HTTP {status}: {body[:500]}")
        self.status = status


# ----------------------------------------------------------------- coordinates / helpers

def git_remote_url(remote):
    result = subprocess.run(
        ["git", "-C", issue.PROJECT_DIR, "remote", "get-url", remote],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        issue.die(f"could not read git remote '{remote}': {result.stderr.strip()}")
    return result.stdout.strip()


def derive_coords(remote_url):
    """git@bitbucket.org:officejet/some-repo.git or the https form → (workspace, repo)."""
    if "bitbucket.org" not in remote_url:
        issue.die(f"remote '{remote_url}' is not a Bitbucket repository — use the /dma:pr-feedback skill", 2)
    tail = remote_url.split("bitbucket.org", 1)[1].lstrip(":/")
    if tail.endswith(".git"):
        tail = tail[:-4]
    parts = tail.split("/")
    if len(parts) < 2:
        issue.die(f"could not parse workspace/repo from remote '{remote_url}'")
    return parts[0], parts[1]


def reachable(ctx, status_key):
    """Can this task be moved there at all? Checked before any write, because the
    per-task policy is log-and-skip, not abort the whole run."""
    import tracker as tracker_module
    try:
        ctx.tracker.validate_status(status_key)
    except tracker_module.TrackerError as e:
        return str(e)
    return None


def status_name(config, status_key):
    return config["tasks"]["workflow"]["statuses"][status_key]


def key_from_branch(branch, branch_prefix):
    return branch[len(branch_prefix):] if branch.startswith(branch_prefix) else branch


def is_managed(pr, managed_prefix):
    return (pr.get("source") or {}).get("branch", {}).get("name", "").startswith(managed_prefix)


def pr_url(pr):
    return ((pr.get("links") or {}).get("html") or {}).get("href", "")


def rejection_text(bb, workspace, repo, pr):
    """PR description plus inline/general comments, inline ones prefixed [path:line]."""
    parts = []
    description = ((pr.get("summary") or {}).get("raw")) or pr.get("description") or ""
    if description.strip():
        parts.append(description.strip())
    for comment in bb.list_pull_request_comments(workspace, repo, pr["id"]):
        raw = ((comment.get("content") or {}).get("raw") or "").strip()
        if not raw:
            continue
        inline = comment.get("inline")
        if inline:
            line = inline.get("to") or inline.get("from") or "?"
            parts.append(f"[{inline.get('path', '?')}:{line}] {raw}")
        else:
            parts.append(raw)
    return "\n\n".join(parts)[:TEXT_CAP]


def add_label(labels, label):
    return labels if label in labels else labels + [label]


# ----------------------------------------------------------------- reconciliation

class Context:
    """Everything the per-task handlers need, resolved once."""

    def __init__(self, tracker, bb, config, workspace, repo):
        self.tracker = tracker
        self.bb = bb
        self.config = config
        self.workspace = workspace
        self.repo = repo
        self.branch_prefix = (config.get("vcs") or {}).get("branch_prefix", "")
        self.awaiting = status_name(config, "awaiting_merge")


def reconcile_task(ctx, key):
    branch = f"{ctx.branch_prefix}{key}"
    prs = ctx.bb.pull_requests_for_branch(ctx.workspace, ctx.repo, branch)
    if not prs:
        print(f"waiting {key}: no pull request on {branch}")
        return
    pr = prs[0]
    state = pr.get("state")
    if state not in ("MERGED", "DECLINED"):
        print(f"waiting {key}: newest PR #{pr['id']} is {state}")
        return

    data = ctx.tracker.read(key)
    if data["status"] != ctx.awaiting:
        # The JQL index can lag a transition made moments ago.
        print(f"skip {key}: no longer in {ctx.awaiting} (already reconciled)")
        return

    if state == "DECLINED":
        reconcile_declined(ctx, key, data, pr)
    else:
        reconcile_merged(ctx, key, data, pr)


def reconcile_declined(ctx, key, data, pr):
    text = rejection_text(ctx.bb, ctx.workspace, ctx.repo, pr)
    if not text.strip():
        print(f"NEEDS-INPUT {key}: declined PR {pr_url(pr)} has no rejection text — ask the user, then re-run")
        return

    unreachable = reachable(ctx, "to_do")
    if unreachable:
        print(f"skip {key}: {unreachable}")
        return

    ctx.tracker.set_labels(key, add_label(list(data["labels"]), "agent:dev"))
    ctx.tracker.set_status(key, "to_do")
    ctx.tracker.add_comment(key, f"🤖 user (decline) via PR {pr_url(pr)}:\n\n{text}")
    print(f"DECLINED {key} → dev (to_do)")


def reconcile_merged(ctx, key, data, pr):
    url = pr_url(pr)
    destination = (pr.get("destination") or {}).get("branch", {}).get("name", "?")
    merged_tip = merge_source_tip(ctx.bb, ctx.workspace, ctx.repo, pr)
    approved = approved_tip(ctx.tracker, key)

    note = ""
    if approved is None:
        note = "; no approved-tip recorded on this task"
    elif merged_tip is None:
        note = "; merged tip could not be determined (no merge commit — squash or fast-forward)"
    elif merged_tip != approved:
        ctx.tracker.set_labels(key, add_label(list(data["labels"]), "stale-merge"))
        ctx.tracker.add_comment(
            key,
            f"🤖 user (merge with stale tip) via PR {url}: merged {merged_tip}, but approved tip "
            f"was {approved}. Commits between the two were orphaned and need human review before "
            f"this task is marked done.",
        )
        print(f"STALE-MERGE {key}: merged {merged_tip} != approved {approved} — left in {ctx.awaiting}")
        return

    unreachable = reachable(ctx, "done")
    if unreachable:
        print(f"skip {key}: {unreachable}")
        return
    ctx.tracker.set_status(key, "done")
    ctx.tracker.add_comment(
        key, f"🤖 user (merge) via PR {url}: merged into {destination} at {merged_tip or 'merge commit'}{note}.")
    print(f"MERGED {key} → done")

    close_out_parent(ctx, key, data)


def merge_source_tip(bb, workspace, repo, pr):
    """parents[1] of the merge commit is what landed from the source branch.
    A squash or fast-forward merge has one parent and no reliable source tip → None."""
    merge_sha = (pr.get("merge_commit") or {}).get("hash")
    if not merge_sha:
        return None
    parents = bb.get_commit(workspace, repo, merge_sha).get("parents") or []
    if len(parents) < 2:
        return None
    return parents[1].get("hash")


def approved_tip(tracker, key):
    for comment in tracker.comments(key):
        match = APPROVED_TIP_RE.search(comment.get("body") or "")
        if match:
            return match.group(1)
    return None


def close_out_parent(ctx, child_key, child):
    parent = child["parent"]
    if not parent or parent["type"] != "group":
        return
    parent_key = parent["key"]
    done = status_name(ctx.config, "done")
    # `key != child` keeps the just-transitioned child out of the answer: the JQL
    # index lags the transition made a moment ago and would report it as open.
    open_siblings = ctx.tracker.search(parent=parent_key, exclude_key=child_key, status_not=done)
    if open_siblings:
        return

    unreachable = reachable(ctx, "code_review")
    if unreachable:
        print(f"skip close-out of {parent_key}: {unreachable}")
        return
    parent_labels = add_label(list(ctx.tracker.read(parent_key)["labels"]), "agent:team-lead")
    ctx.tracker.set_labels(parent_key, parent_labels)
    try:
        ctx.tracker.set_status(parent_key, "code_review")
    except Exception as e:
        print(f"WARNING close-out of {parent_key}: label added but transition refused ({e}) — "
              f"partial promote, needs a human", file=sys.stderr)
        return
    ctx.tracker.add_comment(parent_key, "🤖 pr-feedback: all children merged — group ready for close-out.")
    print(f"CLOSEOUT {parent_key} → team-lead (code_review)")


# ----------------------------------------------------------------- main

def cmd_list(argv):
    """dma board list [--status S] [--label L] [--parent KEY] [--type task|group]

    The tracker-agnostic filters of skills/issue-search, as one call."""
    filters, i = {}, 0
    while i < len(argv):
        flag = argv[i]
        if flag not in ("--status", "--label", "--parent", "--type") or i + 1 >= len(argv):
            issue.die("usage: dma board list [--status S] [--label L] [--parent KEY] [--type task|group]")
        filters[flag[2:]] = argv[i + 1]
        i += 2

    import tracker as tracker_module

    config = issue.load_config()
    try:
        tracker = tracker_module.open_tracker(config)
    except tracker_module.Unsupported as e:
        issue.die(f"{e} — use the /dma:issue-search skill", 2)
    except tracker_module.TrackerError as e:
        issue.die(str(e))

    if filters.get("type") and filters["type"] not in ("task", "group"):
        issue.die("--type must be task or group")

    limit = 50
    rows = tracker.search(status=filters.get("status"), label=filters.get("label"),
                          parent=filters.get("parent"), kind=filters.get("type"))
    truncated = " (truncated — narrow the filters)" if len(rows) == limit else ""
    print(f"{len(rows)} issue(s){truncated}")
    for row in rows:
        labels = ",".join(row["labels"]) or "-"
        print(f"{row['key']}\t{row['status']}\t{labels}\tparent={row['parent'] or '-'}\t{row['title']}")
    return 0


def cmd_reconcile(argv):
    if not os.path.exists(issue.CONFIG_PATH):
        issue.die(f"config not found: {issue.CONFIG_PATH} (set CLAUDE_PROJECT_DIR or run from the project root)")

    import tracker as tracker_module

    config = issue.load_config()
    try:
        tracker = tracker_module.open_tracker(config)
    except tracker_module.Unsupported as e:
        issue.die(f"{e} — use the /dma:pr-feedback skill", 2)
    except tracker_module.TrackerError as e:
        issue.die(str(e))

    remote = ((config.get("workspace") or {}) or {}).get("remote", "origin")
    workspace, repo = derive_coords(git_remote_url(remote))
    ctx = Context(tracker, Bitbucket(*load_bitbucket_credentials()), config, workspace, repo)

    try:
        waiting = tracker.search(status=ctx.awaiting)
    except Exception as e:
        issue.die(str(e))

    print(f"reconcile: {len(waiting)} task(s) in {ctx.awaiting}")
    for row in waiting:
        key = row["key"]
        try:
            reconcile_task(ctx, key)
        except Exception as e:                                   # one task never sinks the run
            print(f"WARNING {key} failed, skipped ({e}) — next pre-flight retries", file=sys.stderr)
    return 0


def main(argv):
    if not argv or argv[0] not in ("reconcile", "list"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    return cmd_reconcile(argv[1:]) if argv[0] == "reconcile" else cmd_list(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
