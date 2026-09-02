"""Tracker operations for agents — one process call instead of a Skill round-trip.

    dma issue read    <KEY>                          one issue, with its comments
    dma issue claim   <KEY> | --role <r> | --any     take it, or take the next one in a queue
    dma issue comment <KEY> <body | ->               a comment ('-' = body from stdin)
    dma issue handoff <KEY> [to-role] [body | ->     label + status + comment, in one step
    dma issue create  <task|group> <summary> ...     a new issue, optionally linked
    dma issue label   <KEY> [--add a,b] [--remove c] labels only, status untouched

Project root = $CLAUDE_PROJECT_DIR, else the current directory. Reads
<project>/.claude/dma/config.yml (provider, status names, jira transition ids)
and Jira credentials from <project>/.mcp.json → mcpServers.atlassian.env
(JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN), falling back to the environment.

Providers: `jira` and `linear` (see scripts/tracker.py). A provider with no
backend exits 2; there is no other path, the agent stops and reports.

Exit codes: 0 ok · 1 error · 2 provider not supported · 3 claim rejected (already claimed)
            4 nothing to claim (queue addressing only)
"""

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

PROJECT_DIR = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
CONFIG_PATH = os.path.join(PROJECT_DIR, ".claude", "dma", "config.yml")
MCP_PATH = os.path.join(PROJECT_DIR, ".mcp.json")

# Where each handoff target lands: the status it moves to and the agent label it
# leaves behind. `done`, `awaiting_merge` and `awaiting_ops` have no agent owner.
HANDOFF_TARGETS = {
    #  target:          (status key,       new agent label or None)
    "qa":               ("qa",             "agent:qa"),
    "reviewer":         ("code_review",    "agent:reviewer"),
    "dev":              ("to_do",          "agent:dev"),
    "devops":           ("to_do",          "agent:devops"),
    "team-lead":        ("on_hold",        "agent:team-lead"),
    "awaiting_merge":   ("awaiting_merge", None),
    "awaiting_ops":     ("awaiting_ops",   None),
    "done":             ("done",           None),
}
DEFAULT_FORWARD = {"dev": "qa", "qa": "reviewer", "reviewer": "awaiting_merge", "devops": "awaiting_ops"}

# Queue priority for `claim --role` / `claim --any`, in the order commands/run.md
# walks them: (role, status key, issue type). `to_do` entries for reviewer/qa exist
# because the stuck-task pre-flight can roll a claimed task back to `to_do`.
QUEUES = [
    ("team-lead", "on_hold",     "task"),
    ("team-lead", "to_do",       "task"),
    ("sentinel",  "to_do",       "task"),
    ("team-lead", "code_review", "group"),
    ("reviewer",  "code_review", "task"),
    ("reviewer",  "to_do",       "task"),
    ("qa",        "qa",          "task"),
    ("qa",        "to_do",       "task"),
    ("dev",       "to_do",       "task"),
    ("devops",    "to_do",       "task"),
]
BLOCKED_BY = "is blocked by"

# Where a new issue starts when the caller does not say: the queue that role picks
# from, per commands/run.md "Role → queue mapping". `on_hold` and `code_review` are
# transition targets for team-lead, not create targets — ask for them with --state.
ROLE_START = {"qa": "qa", "reviewer": "code_review", "team-lead": "to_do",
              "dev": "to_do", "devops": "to_do", "sentinel": "to_do"}


def die(message, code=1):
    print(message, file=sys.stderr)
    sys.exit(code)


# ----------------------------------------------------------------- config / creds

def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_credentials():
    creds = {}
    if os.path.exists(MCP_PATH):
        with open(MCP_PATH) as f:
            servers = json.load(f).get("mcpServers", {})
        creds = servers.get("atlassian", {}).get("env", {})
    url = creds.get("JIRA_URL") or os.environ.get("JIRA_URL")
    user = creds.get("JIRA_USERNAME") or os.environ.get("JIRA_USERNAME")
    token = creds.get("JIRA_API_TOKEN") or os.environ.get("JIRA_API_TOKEN")
    if not (url and user and token):
        die(f"Jira credentials not found: need JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN in {MCP_PATH} (mcpServers.atlassian.env) or in the environment")
    return url.rstrip("/"), user, token


# ----------------------------------------------------------------- jira http

class Jira:
    def __init__(self, url, user, token):
        self.url = url
        self.auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + "/rest/api/2/" + path, data=data, method=method)
        request.add_header("Authorization", self.auth)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            raise JiraError(e.code, e.read().decode(errors="replace"))
        return json.loads(raw) if raw else None

    def get_issue(self, key):
        return self.call(
            "GET",
            f"issue/{key}?fields=summary,status,labels,parent,description,comment,issuetype,issuelinks")

    def transition(self, key, transition_id):
        self.call("POST", f"issue/{key}/transitions", {"transition": {"id": str(transition_id)}})

    def set_labels(self, key, labels):
        self.call("PUT", f"issue/{key}", {"fields": {"labels": labels}})

    def add_comment(self, key, body):
        self.call("POST", f"issue/{key}/comment", {"body": body})

    def get_comments(self, key, limit=50):
        data = self.call("GET", f"issue/{key}/comment?maxResults={limit}&orderBy=-created")
        return (data or {}).get("comments") or []

    def search_raw(self, jql, fields="summary,status", max_results=50):
        """POST-free JQL search. /rest/api/2/search was removed by Atlassian
        (HTTP 410) — /search/jql is the replacement; it answers {issues, isLast}
        and no longer carries a `total`."""
        query = urllib.parse.urlencode({"jql": jql, "fields": fields, "maxResults": max_results})
        return self.call("GET", f"search/jql?{query}") or {}

    def search(self, jql, fields="summary,status", max_results=50):
        return self.search_raw(jql, fields, max_results).get("issues") or []


class JiraError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Jira HTTP {status}: {body[:500]}")
        self.status = status


# ----------------------------------------------------------------- output

def print_issue(issue):
    print(f"key: {issue['key']}")
    print(f"title: {issue['title']}")
    print(f"status: {issue['status']}")
    print(f"labels: {', '.join(issue['labels'])}")
    parent = issue["parent"]
    print(f"parent: {parent['key']} ({parent['type']})" if parent else "parent: null")
    blockers = [f"{b['key']} ({b['status']})" for b in issue["blockers"]]
    print(f"blocked by: {', '.join(blockers) if blockers else '-'}")
    print()
    print("## description")
    print(issue["description"] or "(empty)")
    print()
    print(f"## comments ({len(issue['comments'])}, newest first)")
    for comment in issue["comments"]:
        print(f"--- {comment['author']} · {comment['created']}")
        print(comment["body"])


def open_blockers(issue, done_status):
    """The issues this one is blocked by that are not done yet."""
    return [f"{b['key']} ({b['status']})" for b in issue["blockers"] if b["status"] != done_status]


def transition_id(config, status_key):
    tid = ((config.get("tasks", {}).get("jira") or {}).get("transitions") or {}).get(status_key)
    if not tid:
        die(f"tasks.jira.transitions.{status_key} is missing or 0 in {CONFIG_PATH} — run /dma:sentinel-bootstrap-jira")
    return tid


def read_body(arg):
    if arg == "-":
        return sys.stdin.read().rstrip("\n")
    return arg


# ----------------------------------------------------------------- commands

def cmd_read(tracker, config, key):
    print_issue(tracker.read(key))


def cmd_claim(tracker, config, key):
    claimed, reason = tracker.claim(key)
    if not claimed:
        print(f"CLAIM_FAILED {key}: {reason}")
        sys.exit(3)
    issue = tracker.read(key)
    print(f"CLAIMED {key}")
    print_role_and_area(issue)
    print()
    print_issue(issue)


def print_role_and_area(issue):
    labels = issue["labels"]
    role = next((l[len("agent:"):] for l in labels if l.startswith("agent:")), "-")
    area = next((l[len("area:"):] for l in labels if l.startswith("area:")), "-")
    print(f"role: {role}")
    print(f"area: {area}")


def cmd_claim_from_queue(tracker, config, role_filter):
    """Claim the next available issue instead of a named one: walk the queues in
    priority order, skip what is blocked, and move on when another runner wins the
    race. `role_filter` is None (any queue), a role, or `<area>/<role>`."""
    area = None
    if role_filter and "/" in role_filter:
        area, role_filter = role_filter.split("/", 1)
    if role_filter and role_filter not in {role for role, _, _ in QUEUES}:
        die(f"unknown role '{role_filter}'; one of: {', '.join(sorted({r for r, _, _ in QUEUES}))}")

    done = config["tasks"]["workflow"]["statuses"]["done"]
    contended, blocked = [], []

    for role, status_key, kind in QUEUES:
        if role_filter and role != role_filter:
            continue
        wanted = [f"agent:{role}"] + ([f"area:{area}"] if area else [])
        for row in tracker.search(status=tracker.status_name(status_key), labels=wanted,
                                  kind=kind, oldest_first=True):
            key = row["key"]
            issue = tracker.read(key)
            if status_key == "to_do":
                open_ = open_blockers(issue, done)
                if open_:
                    blocked.append(f"{key} blocked by {', '.join(open_)}")
                    continue
            claimed, _ = tracker.claim(key)
            if not claimed:
                contended.append(key)          # another runner claimed it first
                continue
            print(f"CLAIMED {key}")
            print(f"queue: {role} / {tracker.status_name(status_key)}")
            print_role_and_area(issue)
            print()
            print_issue(issue)
            return

    for line in blocked:
        print(f"skipped: {line}")
    if contended:
        print(f"board contended, nothing else to take (lost the race on {', '.join(contended)})")
    else:
        print(f"nothing to claim in {role_filter or 'any'} queue" + (f" for area {area}" if area else ""))
    sys.exit(4)


def cmd_create(tracker, config, argv):
    """dma issue create <task|group> <summary> [--parent K] [--labels a,b]
                        [--blocks K1,K2] [--description <text> | -] [--state <key>]"""
    if len(argv) < 2 or argv[0] not in ("task", "group"):
        die("usage: dma issue create <task|group> <summary> [--parent K] [--labels a,b] "
            "[--blocks K1,K2] [--description <text> | -] [--state <key>]")
    kind, summary, options, rest = argv[0], argv[1], {}, argv[2:]
    while rest:
        if rest[0] not in ("--parent", "--labels", "--blocks", "--description", "--state") or len(rest) < 2:
            die("usage: dma issue create <task|group> <summary> [--parent K] [--labels a,b] "
                "[--blocks K1,K2] [--description <text> | -] [--state <key>]")
        options[rest[0][2:]] = rest[1]
        rest = rest[2:]

    labels = [l for l in (options.get("labels") or "").split(",") if l]
    blocks = [b for b in (options.get("blocks") or "").split(",") if b]
    description = read_body(options["description"]) if "description" in options else None

    statuses = config["tasks"]["workflow"]["statuses"]
    state_key = options.get("state")
    if not state_key:
        role = next((l[len("agent:"):] for l in labels if l.startswith("agent:")), None)
        state_key = ROLE_START.get(role, "to_do")
    if state_key not in statuses:
        die(f"state key '{state_key}' not in tasks.workflow.statuses")
    tracker.validate_status(state_key)          # before anything is created

    key = tracker.create(kind, summary, description, labels, options.get("parent"), state_key)
    print(f"CREATED {key}")
    print(f"status: {statuses[state_key]}")
    if labels:
        print(f"labels: {', '.join(labels)}")
    if options.get("parent"):
        print(f"parent: {options['parent']}")
    if blocks:
        # after creation: a failure here leaves an issue the caller can still see
        tracker.add_blocks(key, blocks)
        print(f"blocks: {', '.join(blocks)}")


def cmd_label(tracker, config, key, argv):
    """dma issue label <KEY> [--add a,b] [--remove c,d] — labels only, no status."""
    options, rest = {}, argv
    while rest:
        if rest[0] not in ("--add", "--remove") or len(rest) < 2:
            die("usage: dma issue label <KEY> [--add a,b] [--remove c,d]")
        options[rest[0][2:]] = rest[1]
        rest = rest[2:]
    if not options:
        die("nothing to do: pass --add and/or --remove")

    current = tracker.read(key)["labels"]
    removed = [l for l in (options.get("remove") or "").split(",") if l]
    added = [l for l in (options.get("add") or "").split(",") if l]
    new = [l for l in current if l not in removed]
    new += [l for l in added if l not in new]
    tracker.set_labels(key, new)
    print(f"LABELS {key}: {', '.join(new) if new else '(none)'}")
    if removed:
        print(f"removed: {', '.join(l for l in removed if l in current)}")
    if added:
        print(f"added: {', '.join(l for l in added if l not in current)}")


def cmd_comment(tracker, config, key, body):
    tracker.add_comment(key, read_body(body))
    print(f"COMMENTED {key}")


def cmd_handoff(tracker, config, key, to_role, body):
    issue = tracker.read(key)
    labels = issue["labels"]

    from_labels = [l for l in labels if l.startswith("agent:")]
    from_role = from_labels[0][len("agent:"):] if from_labels else None
    area_labels = [l for l in labels if l.startswith("area:")]
    area = area_labels[0][len("area:"):] if area_labels else "-"

    if to_role is None:
        to_role = DEFAULT_FORWARD.get(from_role)
        if to_role is None:
            die(f"no default forward target for label agent:{from_role} — pass the target explicitly")
    if to_role not in HANDOFF_TARGETS:
        die(f"unknown handoff target '{to_role}'; one of: {', '.join(HANDOFF_TARGETS)}")

    status_key, new_agent_label = HANDOFF_TARGETS[to_role]
    tracker.validate_status(status_key)        # before any write

    new_labels = [l for l in labels if not l.startswith("agent:") and l != "needs-decision"]
    if new_agent_label:
        new_labels.append(new_agent_label)
    if to_role == "team-lead":
        new_labels.append("needs-decision")

    comment = f"🤖 {from_role or 'agent'} ({area}): handoff → {to_role}\n\n"
    comment += read_body(body) if body else "Manual handoff."

    tracker.set_labels(key, new_labels)
    tracker.set_status(key, status_key)
    tracker.add_comment(key, comment)

    print(f"HANDOFF {key}: {from_role} → {to_role}")
    print(f"status: {issue['status']} → {tracker.status_name(status_key)}")
    print(f"labels: {', '.join(new_labels)}")

    if to_role == "done":
        remove_worktrees(key)


def remove_worktrees(key):
    """A closed task gives its work area back."""
    import workspace

    workspace.remove(key)


# ----------------------------------------------------------------- main

def main(argv):
    if len(argv) < 2:
        die(__doc__.strip())
    command, key = argv[0], argv[1]
    rest = argv[2:]
    if not os.path.exists(CONFIG_PATH):
        die(f"config not found: {CONFIG_PATH} (set CLAUDE_PROJECT_DIR or run from the project root)")

    import tracker as tracker_module

    config = load_config()
    try:
        tracker = tracker_module.open_tracker(config)
    except tracker_module.Unsupported as e:
        die(str(e), 2)
    except tracker_module.TrackerError as e:
        die(str(e))

    try:
        if command == "read":
            cmd_read(tracker, config, key)
        elif command == "claim":
            if key in ("--any", "--role"):
                cmd_claim_from_queue(tracker, config, rest[0] if key == "--role" and rest else None)
            else:
                cmd_claim(tracker, config, key)
        elif command == "create":
            cmd_create(tracker, config, [key] + rest)
        elif command == "label":
            cmd_label(tracker, config, key, rest)
        elif command == "comment":
            if len(rest) != 1:
                die("usage: dma issue comment <KEY> <body | ->")
            cmd_comment(tracker, config, key, rest[0])
        elif command == "handoff":
            # handoff <KEY>                → default target, default body
            # handoff <KEY> <to-role>      → explicit target
            # handoff <KEY> <body>         → default target (single arg that is not a role)
            # handoff <KEY> <to-role> <body>
            to_role, body = None, None
            if len(rest) == 1:
                if rest[0] in HANDOFF_TARGETS:
                    to_role = rest[0]
                else:
                    body = rest[0]
            elif len(rest) == 2:
                to_role, body = rest
            elif len(rest) > 2:
                die("usage: dma issue handoff <KEY> [to-role] [body | -]")
            cmd_handoff(tracker, config, key, to_role, body)
        else:
            die(__doc__.strip())
    except (JiraError, tracker_module.TrackerError) as e:
        die(str(e))
    except Exception as e:                       # a backend's own transport error
        if type(e).__name__ == "LinearError":
            die(str(e))
        raise
    return 0
