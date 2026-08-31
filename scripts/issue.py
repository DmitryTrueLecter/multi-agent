"""Tracker operations for agents — one process call instead of a Skill round-trip.

    dma issue read    <KEY>                          skills/task-read
    dma issue claim   <KEY> | --role <r> | --any     skills/issue-claim
    dma issue comment <KEY> <body | ->               skills/issue-comment   ('-' = body from stdin)
    dma issue handoff <KEY> [to-role] [body | ->     skills/handoff

Project root = $CLAUDE_PROJECT_DIR, else the current directory. Reads
<project>/.claude/dma/config.yml (provider, status names, jira transition ids)
and Jira credentials from <project>/.mcp.json → mcpServers.atlassian.env
(JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN), falling back to the environment.

Only provider "jira" is implemented. For "linear" the command exits 2 and the
agent falls back to the /dma:* skills.

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

# Copied from skills/handoff/SKILL.md → "Target → status key / label changes".
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


# ----------------------------------------------------------------- output (same shape as skills/task-read)

def open_blockers(data, done_status):
    """Keys of the issues this one is blocked by that are not done yet."""
    blocked = []
    for link in data["fields"].get("issuelinks") or []:
        inward = link.get("inwardIssue")
        if inward and (link.get("type") or {}).get("inward") == BLOCKED_BY:
            if inward["fields"]["status"]["name"] != done_status:
                blocked.append(f"{inward['key']} ({inward['fields']['status']['name']})")
    return blocked


def print_issue(issue):
    fields = issue["fields"]
    parent = fields.get("parent")
    print(f"key: {issue['key']}")
    print(f"title: {fields.get('summary', '')}")
    print(f"status: {fields['status']['name']}")
    print(f"labels: {', '.join(fields.get('labels') or [])}")
    if parent:
        parent_type = "group" if parent["fields"]["issuetype"]["name"] == "Epic" else "task"
        print(f"parent: {parent['key']} ({parent_type}) — {parent['fields'].get('summary', '')}")
    else:
        print("parent: null")
    blockers = [f"{l['inwardIssue']['key']} ({l['inwardIssue']['fields']['status']['name']})"
                for l in fields.get("issuelinks") or []
                if l.get("inwardIssue") and (l.get("type") or {}).get("inward") == BLOCKED_BY]
    print(f"blocked by: {', '.join(blockers) if blockers else '-'}")
    print()
    print("## description")
    print(fields.get("description") or "(empty)")
    print()
    comments = (fields.get("comment") or {}).get("comments") or []
    print(f"## comments ({len(comments)}, newest first)")
    for c in reversed(comments):
        author = (c.get("author") or {}).get("displayName", "?")
        print(f"--- {author} · {c.get('created', '')}")
        print(c.get("body") or "")


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

def cmd_read(jira, config, key):
    print_issue(jira.get_issue(key))


def cmd_claim(jira, config, key):
    """Claim a named issue. The transition to in_progress is the atomic claim: the
    tracker refuses the second runner, and that refusal is not retried."""
    try:
        jira.transition(key, transition_id(config, "in_progress"))
    except JiraError as e:
        print(f"CLAIM_FAILED {key}: {e}")
        sys.exit(3)
    data = jira.get_issue(key)
    print(f"CLAIMED {key}")
    print_role_and_area(data)
    print()
    print_issue(data)


def print_role_and_area(data):
    labels = data["fields"].get("labels") or []
    role = next((l[len("agent:"):] for l in labels if l.startswith("agent:")), "-")
    area = next((l[len("area:"):] for l in labels if l.startswith("area:")), "-")
    print(f"role: {role}")
    print(f"area: {area}")


def cmd_claim_from_queue(jira, config, role_filter):
    """Claim the next available issue instead of a named one: walk the queues in
    priority order, skip what is blocked, and move on when another runner wins the
    race. `role_filter` is None (any queue), a role, or `<area>/<role>`."""
    area = None
    if role_filter and "/" in role_filter:
        area, role_filter = role_filter.split("/", 1)
    if role_filter and role_filter not in {role for role, _, _ in QUEUES}:
        die(f"unknown role '{role_filter}'; one of: {', '.join(sorted({r for r, _, _ in QUEUES}))}")

    project = config["tasks"]["project_key"]
    statuses = config["tasks"]["workflow"]["statuses"]
    done = statuses["done"]
    contended, blocked = [], []

    for role, status_key, kind in QUEUES:
        if role_filter and role != role_filter:
            continue
        clauses = [f"project = {project}", f'status = "{statuses[status_key]}"', f'labels = "agent:{role}"',
                   f"issuetype {'=' if kind == 'group' else '!='} Epic"]
        if area:
            clauses.append(f'labels = "area:{area}"')
        for row in jira.search(" AND ".join(clauses) + " ORDER BY created ASC", fields="summary"):
            key = row["key"]
            data = jira.get_issue(key)
            if status_key == "to_do":
                open_ = open_blockers(data, done)
                if open_:
                    blocked.append(f"{key} blocked by {', '.join(open_)}")
                    continue
            try:
                jira.transition(key, transition_id(config, "in_progress"))
            except JiraError:
                contended.append(key)          # another runner claimed it first
                continue
            print(f"CLAIMED {key}")
            print(f"queue: {role} / {statuses[status_key]}")
            print_role_and_area(jira.get_issue(key))
            print()
            print_issue(data)
            return

    for line in blocked:
        print(f"skipped: {line}")
    if contended:
        print(f"board contended, nothing else to take (lost the race on {', '.join(contended)})")
    else:
        print(f"nothing to claim in {role_filter or 'any'} queue" + (f" for area {area}" if area else ""))
    sys.exit(4)


def cmd_comment(jira, config, key, body):
    jira.add_comment(key, read_body(body))
    print(f"COMMENTED {key}")


def cmd_handoff(jira, config, key, to_role, body):
    issue = jira.get_issue(key)
    labels = list(issue["fields"].get("labels") or [])

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
    status_name = config["tasks"]["workflow"]["statuses"][status_key]
    tid = transition_id(config, status_key)   # resolve before any write, so a bad config mutates nothing

    # Labels: drop agent:<from> and needs-decision, add agent:<to>; team-lead also gets needs-decision.
    new_labels = [l for l in labels if not l.startswith("agent:") and l != "needs-decision"]
    if new_agent_label:
        new_labels.append(new_agent_label)
    if to_role == "team-lead":
        new_labels.append("needs-decision")

    comment = f"🤖 {from_role or 'agent'} ({area}): handoff → {to_role}\n\n"
    comment += read_body(body) if body else "Manual handoff via /dma:handoff."

    jira.set_labels(key, new_labels)
    jira.transition(key, tid)
    jira.add_comment(key, comment)

    print(f"HANDOFF {key}: {from_role} → {to_role}")
    print(f"status: {issue['fields']['status']['name']} → {status_name}")
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

    config = load_config()
    provider = (config.get("tasks") or {}).get("provider")
    if provider != "jira":
        die(f"provider '{provider}' is not supported by `dma issue` — use the /dma:* skills", 2)

    jira = Jira(*load_credentials())
    try:
        if command == "read":
            cmd_read(jira, config, key)
        elif command == "claim":
            if key in ("--any", "--role"):
                cmd_claim_from_queue(jira, config, rest[0] if key == "--role" and rest else None)
            else:
                cmd_claim(jira, config, key)
        elif command == "comment":
            if len(rest) != 1:
                die("usage: dma issue comment <KEY> <body | ->")
            cmd_comment(jira, config, key, rest[0])
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
            cmd_handoff(jira, config, key, to_role, body)
        else:
            die(__doc__.strip())
    except JiraError as e:
        die(str(e))
    return 0
