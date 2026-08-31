"""One shape for an issue, whichever tracker it came from.

`dma issue` and `dma board` used to read Jira's payload directly —
`data["fields"]["status"]["name"]`, JQL strings, numeric transition ids. That
tied every command to one tracker. Here each backend answers in the same shape,
so the commands are written once:

    {"key", "title", "status", "labels", "parent": {"key", "type"} | None,
     "description", "blockers": [{"key", "status"}],
     "comments": [{"author", "created", "body"}]}   # newest first

`status` and the `status_key` arguments are two different things: a status_key is
a semantic name from `config.yml` (`to_do`, `code_review`), and the backend turns
it into whatever that project's tracker calls it — a display name plus, for Jira,
the numeric transition id it insists on.
"""

import issue as issue_module

BLOCKED_BY = "is blocked by"


class TrackerError(Exception):
    pass


class Unsupported(Exception):
    """The configured provider has no backend here; the caller falls back."""


# --------------------------------------------------------------------- jira

class JiraTracker:
    provider = "jira"

    def __init__(self, config):
        self.config = config
        self.api = issue_module.Jira(*issue_module.load_credentials())
        self.statuses = config["tasks"]["workflow"]["statuses"]
        self.project = config["tasks"]["project_key"]

    # -- naming ---------------------------------------------------------

    def status_name(self, status_key):
        return self.statuses[status_key]

    def validate_status(self, status_key):
        """Fail before any write when the target status is not reachable."""
        self.transition_id(status_key)

    def transition_id(self, status_key):
        tid = ((self.config.get("tasks", {}).get("jira") or {}).get("transitions") or {}).get(status_key)
        if not tid:
            raise TrackerError(f"tasks.jira.transitions.{status_key} is missing or 0 — "
                               f"run /dma:sentinel-bootstrap-jira")
        return tid

    # -- reads ----------------------------------------------------------

    def read(self, key):
        return self._normalize(self.api.get_issue(key))

    def _normalize(self, data):
        fields = data["fields"]
        parent = fields.get("parent")
        blockers = []
        for link in fields.get("issuelinks") or []:
            inward = link.get("inwardIssue")
            if inward and (link.get("type") or {}).get("inward") == BLOCKED_BY:
                blockers.append({"key": inward["key"], "status": inward["fields"]["status"]["name"]})
        comments = [{"author": (c.get("author") or {}).get("displayName", "?"),
                     "created": c.get("created", ""), "body": c.get("body") or ""}
                    for c in reversed(((fields.get("comment") or {}).get("comments") or []))]
        return {
            "key": data["key"],
            "title": fields.get("summary", ""),
            "status": fields["status"]["name"],
            "labels": list(fields.get("labels") or []),
            "parent": {"key": parent["key"],
                       "type": "group" if parent["fields"]["issuetype"]["name"] == "Epic" else "task"}
            if parent else None,
            "description": fields.get("description") or "",
            "blockers": blockers,
            "comments": comments,
        }

    def comments(self, key):
        return [{"author": (c.get("author") or {}).get("displayName", "?"),
                 "created": c.get("created", ""), "body": c.get("body") or ""}
                for c in self.api.get_comments(key)]

    def search(self, status=None, status_not=None, label=None, labels=None, parent=None,
               kind=None, exclude_key=None, oldest_first=False):
        """Every filter is part of the query. Keeping one of them client-side would
        mean filtering a page that the server already truncated."""
        clauses = [f'parent = "{parent}"'] if parent else [f"project = {self.project}"]
        if status:
            clauses.append(f'status = "{status}"')
        if status_not:
            clauses.append(f'status != "{status_not}"')
        for name in ([label] if label else []) + list(labels or []):
            clauses.append(f'labels = "{name}"')
        if kind:
            clauses.append(f"issuetype {'=' if kind == 'group' else '!='} Epic")
        if exclude_key:
            clauses.append(f"key != {exclude_key}")
        jql = " AND ".join(clauses) + (" ORDER BY created ASC" if oldest_first else "")
        rows = self.api.search(jql, fields="summary,status,labels,parent")
        return [{"key": r["key"],
                 "title": r["fields"].get("summary", ""),
                 "status": r["fields"]["status"]["name"],
                 "labels": list(r["fields"].get("labels") or []),
                 "parent": (r["fields"].get("parent") or {}).get("key")}
                for r in rows]

    # -- writes ---------------------------------------------------------

    def set_status(self, key, status_key):
        self.api.transition(key, self.transition_id(status_key))

    def set_labels(self, key, labels):
        self.api.set_labels(key, labels)

    def add_comment(self, key, body):
        self.api.add_comment(key, body)

    def claim(self, key):
        """The transition to in_progress is the claim: the workflow refuses the
        second runner, and that refusal is not retried."""
        try:
            self.api.transition(key, self.transition_id("in_progress"))
        except issue_module.JiraError as e:
            return False, str(e)
        return True, ""


# ------------------------------------------------------------------- linear

class LinearTracker:
    provider = "linear"

    def __init__(self, config):
        import linear_api

        self.linear_api = linear_api
        key = linear_api.load_key(issue_module.MCP_PATH)
        if not key:
            raise TrackerError(
                "Linear API key not found: set LINEAR_API_KEY, or LINEAR_API_KEY_FILE, or "
                f"mcpServers.linear.env.LINEAR_API_KEY in {issue_module.MCP_PATH}")
        tasks = config["tasks"]
        if not tasks.get("team_key"):
            raise TrackerError("tasks.team_key is not set in config.yml — Linear needs the team key")
        self.api = linear_api.Linear(key, tasks["team_key"])
        self.statuses = tasks["workflow"]["statuses"]
        self.project = tasks.get("project")

    def status_name(self, status_key):
        return self.statuses[status_key]

    def validate_status(self, status_key):
        """Resolving the state name now means a typo is reported before any write,
        and the message lists what the team actually has."""
        try:
            self.api.state_id(self.status_name(status_key))
        except self.linear_api.LinearError as e:
            raise TrackerError(str(e))

    # -- reads ----------------------------------------------------------

    def read(self, key):
        data = self.api.issue(key)
        parent = data.get("parent")
        return {
            "key": data["identifier"],
            "title": data.get("title", ""),
            "status": data["state"]["name"],
            "labels": [n["name"] for n in data["labels"]["nodes"]],
            # Linear has no epics; a parent issue is this system's "group".
            "parent": {"key": parent["identifier"], "type": "group"} if parent else None,
            "description": data.get("description") or "",
            "blockers": [{"key": b["identifier"], "status": b["state"]["name"]}
                         for b in self.api.blockers(key)],
            "comments": self.comments(key),
        }

    def comments(self, key):
        return [{"author": ((c.get("user") or c.get("botActor") or {}).get("name", "?")),
                 "created": c.get("createdAt", ""), "body": c.get("body") or ""}
                for c in self.api.comments(key)]

    def search(self, status=None, status_not=None, label=None, labels=None, parent=None,
               kind=None, exclude_key=None, oldest_first=False):
        # `kind` has no counterpart: Linear has one issue type, and the grouping
        # this system calls a group is a parent issue.
        rows = self.api.search(status=status, status_not=status_not,
                               labels=([label] if label else []) + list(labels or []),
                               parent=parent, project=self.project if not parent else None,
                               exclude_key=exclude_key)
        found = [{"key": r["identifier"],
                  "title": r.get("title", ""),
                  "status": r["state"]["name"],
                  "labels": [n["name"] for n in r["labels"]["nodes"]],
                  "parent": (r.get("parent") or {}).get("identifier")}
                 for r in rows]
        return sorted(found, key=lambda r: r["key"]) if oldest_first else found

    # -- writes ---------------------------------------------------------

    def set_status(self, key, status_key):
        self.api.set_state(key, self.status_name(status_key))

    def set_labels(self, key, labels):
        self.api.set_labels(key, labels)

    def add_comment(self, key, body):
        self.api.add_comment(key, body)

    def claim(self, key):
        """Linear has no transition the workflow can refuse, so the claim is a
        write followed by a read-back: whoever the tracker reports as in progress
        after the dust settles is the one that got it."""
        wanted = self.status_name("in_progress")
        self.api.set_state(key, wanted)
        current = self.api.issue(key)["state"]["name"]
        if current.lower() != wanted.lower():
            return False, f"state is {current}, not {wanted}"
        return True, ""


# ------------------------------------------------------------------- factory

BACKENDS = {"jira": JiraTracker, "linear": LinearTracker}


def open_tracker(config):
    provider = (config.get("tasks") or {}).get("provider")
    backend = BACKENDS.get(provider)
    if not backend:
        raise Unsupported(f"provider '{provider}' has no backend — expected one of {', '.join(BACKENDS)}")
    return backend(config)
