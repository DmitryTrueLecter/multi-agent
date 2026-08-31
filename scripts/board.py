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

Trackers: jira and linear (scripts/tracker.py). Hosts: Bitbucket and GitHub
(scripts/vcs.py). A tracker or a host with no backend exits 2 and says so — there
is no other path, so the run stops rather than pretending the board is clean.

Failure policy from the skill: one task that fails is logged and skipped, the run
continues, the next pre-flight retries. A declined PR with no rejection text is
surfaced (NEEDS-INPUT) and left untouched — asking the user is not the script's call.

Exit codes: 0 ok · 1 error · 2 provider/remote not supported
"""

import json
import os
import re
import subprocess
import sys

import issue

APPROVED_TIP_RE = re.compile(r"^Approved tip: ([0-9a-f]{40})$", re.MULTILINE)
TEXT_CAP = 3000
# Every state a decided or pending PR can be in; the newest one wins.
PR_STATES = ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")


# ----------------------------------------------------------------- coordinates / helpers

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


def rejection_text(vcs, pr):
    """PR description plus its comments, inline ones prefixed [path:line]."""
    parts = []
    if pr["description"].strip():
        parts.append(pr["description"].strip())
    for comment in vcs.comments(pr):
        inline = comment.get("inline")
        if inline and inline.get("path"):
            parts.append(f"[{inline['path']}:{inline.get('to') or '?'}] {comment['body']}")
        else:
            parts.append(comment["body"])
    return "\n\n".join(parts)[:TEXT_CAP]


def add_label(labels, label):
    return labels if label in labels else labels + [label]


# ----------------------------------------------------------------- reconciliation

class Context:
    """Everything the per-task handlers need, resolved once."""

    def __init__(self, tracker, vcs, config):
        self.tracker = tracker
        self.vcs = vcs
        self.config = config
        self.branch_prefix = (config.get("vcs") or {}).get("branch_prefix", "")
        self.awaiting = status_name(config, "awaiting_merge")


def reconcile_task(ctx, key):
    branch = f"{ctx.branch_prefix}{key}"
    prs = ctx.vcs.pull_requests_for_branch(branch)
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
    text = rejection_text(ctx.vcs, pr)
    if not text.strip():
        print(f"NEEDS-INPUT {key}: declined PR {pr["url"]} has no rejection text — ask the user, then re-run")
        return

    unreachable = reachable(ctx, "to_do")
    if unreachable:
        print(f"skip {key}: {unreachable}")
        return

    ctx.tracker.set_labels(key, add_label(list(data["labels"]), "agent:dev"))
    ctx.tracker.set_status(key, "to_do")
    ctx.tracker.add_comment(key, f"🤖 user (decline) via PR {pr["url"]}:\n\n{text}")
    print(f"DECLINED {key} → dev (to_do)")


def reconcile_merged(ctx, key, data, pr):
    url = pr["url"]
    destination = pr["destination"] or "?"
    merged_tip = ctx.vcs.merge_source_tip(pr)
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
    ctx.tracker.add_comment(parent_key, "🤖 board reconcile: all children merged — group ready for close-out.")
    print(f"CLOSEOUT {parent_key} → team-lead (code_review)")


# ----------------------------------------------------------------- main

def cmd_list(argv):
    """dma board list [--status S] [--label L] [--parent KEY] [--type task|group]

    Tracker-agnostic filters, translated to whatever the provider speaks."""
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
        issue.die(str(e), 2)
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
        issue.die(str(e), 2)
    except tracker_module.TrackerError as e:
        issue.die(str(e))

    import vcs as vcs_module

    remote = ((config.get("workspace") or {}) or {}).get("remote", "origin")
    try:
        host = vcs_module.open_vcs(issue.PROJECT_DIR, issue.MCP_PATH, remote)
    except vcs_module.Unsupported as e:
        issue.die(str(e), 2)
    except vcs_module.VcsError as e:
        issue.die(str(e))
    ctx = Context(tracker, host, config)

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
