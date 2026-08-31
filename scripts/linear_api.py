"""Linear GraphQL client — the Linear half of what `dma issue` and `dma board` do.

Linear differs from Jira in ways that shape this file:

* No transition ids. A status is a workflow state, its id is per team, and the
  name is free text — so every status change resolves `name → id` for the issue's
  team first (`config.yml` names the statuses; the team key comes from
  `tasks.team_key`).
* No epics. `Issue.parent` is a sub-issue link and `Issue.project` is the
  epic-shaped grouping. The tracker-agnostic prompts call an epic a "group", and
  this system has always mapped a Linear parent to that — kept as is.
* Labels are ids too, and one name can exist twice: once for the team, once for
  the workspace (`team: null`). The team's own label wins.
* Errors arrive with HTTP 200 and an `errors` array; rate limiting arrives as
  HTTP 400 with `extensions.code == "RATELIMITED"`.

Credentials: `LINEAR_API_KEY`, or the file named by `LINEAR_API_KEY_FILE`, or
`mcpServers.linear.env.LINEAR_API_KEY` in the project's `.mcp.json`. A personal
API key goes in the `Authorization` header verbatim — no `Bearer` prefix; an
OAuth access token does take the prefix, so one is added when the value looks
like an OAuth token rather than `lin_api_…`.
"""

import json
import os
import urllib.error
import urllib.request

ENDPOINT = "https://api.linear.app/graphql"
PAGE = 50


class LinearError(Exception):
    pass


def load_key(mcp_path):
    key = os.environ.get("LINEAR_API_KEY")
    if not key and os.environ.get("LINEAR_API_KEY_FILE"):
        with open(os.path.expanduser(os.environ["LINEAR_API_KEY_FILE"])) as f:
            key = f.read().strip()
    if not key and os.path.exists(mcp_path):
        with open(mcp_path) as f:
            servers = json.load(f).get("mcpServers", {})
        key = (servers.get("linear", {}).get("env") or {}).get("LINEAR_API_KEY")
    return key


class Linear:
    def __init__(self, key, team_key, endpoint=ENDPOINT):
        self.key = key
        self.team_key = team_key
        self.endpoint = endpoint
        self._states = None
        self._team_id = None

    # ------------------------------------------------------------ transport

    def call(self, query, variables=None):
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        request = urllib.request.Request(self.endpoint, data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        # A personal key is sent as-is; an OAuth access token needs "Bearer".
        request.add_header("Authorization", self.key if self.key.startswith("lin_api_") else f"Bearer {self.key}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if '"RATELIMITED"' in raw:
                raise LinearError(f"Linear rate limit reached: {raw[:300]}")
            raise LinearError(f"Linear HTTP {e.code}: {raw[:500]}")
        if body.get("errors"):
            # A GraphQL request can fail with HTTP 200 and report it here.
            raise LinearError("; ".join(e.get("message", str(e)) for e in body["errors"])[:500])
        return body["data"]

    def paginate(self, query, variables, path):
        """Follow pageInfo until exhausted. `path` names the connection in the
        response, e.g. ("issues",) or ("issue", "comments")."""
        nodes, after = [], None
        while True:
            data = self.call(query, {**variables, "after": after})
            connection = data
            for step in path:
                connection = connection[step]
            nodes.extend(connection["nodes"])
            info = connection.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                return nodes
            after = info["endCursor"]

    # ------------------------------------------------------------ lookups

    def team_id(self):
        if self._team_id is None:
            data = self.call(
                "query Team($key: String!) { teams(filter: {key: {eq: $key}}, first: 1) { nodes { id key } } }",
                {"key": self.team_key})
            nodes = data["teams"]["nodes"]
            if not nodes:
                raise LinearError(f"no team with key {self.team_key}")
            self._team_id = nodes[0]["id"]
        return self._team_id

    def states(self):
        """name → id for this team. Names are free text, so match case-insensitively."""
        if self._states is None:
            data = self.call(
                "query States($key: String!) { workflowStates(filter: {team: {key: {eq: $key}}}, first: 100)"
                " { nodes { id name type } } }", {"key": self.team_key})
            self._states = {n["name"].lower(): n["id"] for n in data["workflowStates"]["nodes"]}
        return self._states

    def state_id(self, name):
        state = self.states().get(name.lower())
        if not state:
            raise LinearError(f"team {self.team_key} has no workflow state named '{name}' "
                              f"(has: {', '.join(sorted(self.states()))})")
        return state

    def label_ids(self, names):
        """Resolve label names to ids, creating the ones this team does not have.
        A name can exist twice — team-scoped and workspace-wide; the team's wins."""
        if not names:
            return []
        data = self.call(
            "query Labels($names: [String!]!) { issueLabels(filter: {name: {in: $names}}, first: 250)"
            " { nodes { id name team { key } } } }", {"names": list(names)})
        found = {}
        for node in data["issueLabels"]["nodes"]:
            name = node["name"]
            team = (node.get("team") or {}).get("key")
            if name not in found or team == self.team_key:
                found[name] = node["id"]
        ids = []
        for name in names:
            if name in found:
                ids.append(found[name])
                continue
            created = self.call(
                "mutation MakeLabel($input: IssueLabelCreateInput!) { issueLabelCreate(input: $input)"
                " { success issueLabel { id name } } }",
                {"input": {"name": name, "teamId": self.team_id()}})
            ids.append(created["issueLabelCreate"]["issueLabel"]["id"])
        return ids

    # ------------------------------------------------------------ reads

    ISSUE_FIELDS = """
        id identifier title description
        state { name }
        labels(first: 50) { nodes { name } }
        parent { identifier title }
        project { name }
    """

    def issue(self, key):
        data = self.call(
            "query Issue($id: String!) { issue(id: $id) { " + self.ISSUE_FIELDS + " } }", {"id": key})
        return data["issue"]

    def comments(self, key):
        """Newest first. The connection takes no sort direction, so order here."""
        query = ("query Comments($id: String!, $after: String) { issue(id: $id) {"
                 " comments(first: 100, after: $after, orderBy: createdAt) {"
                 " nodes { body createdAt user { name } botActor { name } }"
                 " pageInfo { hasNextPage endCursor } } } }")
        nodes = self.paginate(query, {"id": key}, ("issue", "comments"))
        return sorted(nodes, key=lambda c: c.get("createdAt") or "", reverse=True)

    def blockers(self, key):
        """Issues this one is blocked by: the inverse side of a `blocks` relation."""
        data = self.call(
            "query Blockers($id: String!) { issue(id: $id) { inverseRelations(first: 50)"
            " { nodes { type issue { identifier state { name } } } } } }", {"id": key})
        return [n["issue"] for n in data["issue"]["inverseRelations"]["nodes"] if n["type"] == "blocks"]

    def search(self, status=None, status_not=None, labels=None, parent=None, project=None, exclude_key=None):
        conditions = {"team": {"key": {"eq": self.team_key}}}
        if status:
            conditions["state"] = {"name": {"eqIgnoreCase": status}}
        if status_not:
            conditions["state"] = {"name": {"neqIgnoreCase": status_not}}
        if labels:
            # one `labels` key cannot carry two names, so AND them explicitly
            conditions["and"] = [{"labels": {"name": {"eq": name}}} for name in labels]
        if parent:
            conditions["parent"] = {"identifier": {"eq": parent}}
        if project:
            conditions["project"] = {"name": {"eq": project}}
        query = ("query Issues($filter: IssueFilter, $after: String) {"
                 " issues(filter: $filter, first: 50, after: $after) {"
                 " nodes { identifier title state { name } labels(first: 50) { nodes { name } }"
                 " parent { identifier } } pageInfo { hasNextPage endCursor } } }")
        rows = self.paginate(query, {"filter": conditions}, ("issues",))
        return [r for r in rows if r["identifier"] != exclude_key]

    # ------------------------------------------------------------ writes

    def set_state(self, key, status_name):
        self.call(
            "mutation SetState($id: String!, $stateId: String!) {"
            " issueUpdate(id: $id, input: {stateId: $stateId}) { success } }",
            {"id": key, "stateId": self.state_id(status_name)})

    def set_labels(self, key, names):
        self.call(
            "mutation SetLabels($id: String!, $labelIds: [String!]!) {"
            " issueUpdate(id: $id, input: {labelIds: $labelIds}) { success } }",
            {"id": key, "labelIds": self.label_ids(names)})

    def add_comment(self, key, body):
        # commentCreate takes the issue's UUID, not its identifier.
        issue_id = self.call("query Id($id: String!) { issue(id: $id) { id } }", {"id": key})["issue"]["id"]
        self.call(
            "mutation AddComment($input: CommentCreateInput!) { commentCreate(input: $input) { success } }",
            {"input": {"issueId": issue_id, "body": body}})
