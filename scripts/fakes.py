"""Fake Jira / Bitbucket servers for the offline test suites.

Every payload is built from a response recorded off the real API
(scripts/fixtures/, see record_fixtures.py) — the tests override only the fields
they exercise, so the shape around them stays whatever the API actually sends.
The fakes behave as small stores, not as scripted replies: they apply the writes
they receive, so a test can assert on the resulting state as well as on the calls.

What they cannot prove is that the real endpoints still exist and still answer
this shape — that is scripts/test_contract.py.
"""

import copy
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

FIXTURES = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


# --------------------------------------------------------------------- jira

JQL_CLAUSE = re.compile(r'(\w+)\s*(!=|=)\s*"?([^"]+?)"?(?:\s+AND\s+|$)', re.IGNORECASE)


def jql_matches(clauses, key, record):
    """Evaluate the JQL shapes the code emits: project / status / parent / key /
    issuetype compared with = or !=, `labels = "x"` as membership, joined by AND."""
    for field, op, value in clauses:
        field = field.lower()
        if field == "labels":
            present = value in record["labels"]
            if (op == "=") != present:
                return False
            continue
        actual = {
            "project": key.split("-")[0],
            "status": record["status"],
            "parent": (record["parent"] or (None,))[0],
            "key": key,
            "issuetype": record["kind"],
        }.get(field)
        if op == "=" and actual != value:
            return False
        if op == "!=" and actual == value:
            return False
    return True


class FakeJira:
    """Issues live in `self.issues`; every request is recorded in `self.requests`."""

    def __init__(self):
        self.requests = []          # (method, path, body)
        self.issues = {}            # key -> {status, labels, parent, comments}
        self.reject_transitions = set()   # transition ids the workflow refuses
        self.issue_template = fixture("jira_issue.json")
        self.comments_template = fixture("jira_comments.json")
        self.search_template = fixture("jira_search.json")
        self.transition_status = {}       # transition id -> resulting status name
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _read(self):
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length)) if length else None

            def _reply(self, code, payload=None):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload is not None:
                    self.wfile.write(json.dumps(payload).encode())

            def do_GET(self):
                fake.requests.append(("GET", self.path, None))
                path = urlparse(self.path).path
                if path.startswith("/rest/api/2/search/jql"):
                    query = parse_qs(urlparse(self.path).query)
                    jql = query.get("jql", [""])[0]
                    limit = int(query.get("maxResults", ["50"])[0])
                    return self._reply(200, fake.search_payload(jql, limit))
                if path.endswith("/comment"):
                    key = path.split("/issue/")[1].split("/comment")[0]
                    return self._reply(200, fake.comments_payload(key))
                key = path.split("/issue/")[1]
                if key not in fake.issues:
                    return self._reply(404, {"errorMessages": [f"Issue does not exist: {key}"]})
                self._reply(200, fake.issue_payload(key))

            def do_POST(self):
                body = self._read()
                fake.requests.append(("POST", self.path, body))
                path = urlparse(self.path).path
                key = path.split("/issue/")[1].split("/")[0]
                if path.endswith("/transitions"):
                    tid = str(body["transition"]["id"])
                    if tid in fake.reject_transitions:
                        return self._reply(400, {"errorMessages": ["Transition is not valid"]})
                    fake.issues[key]["status"] = fake.transition_status.get(tid, fake.issues[key]["status"])
                    return self._reply(204)
                fake.issues[key]["comments"].append({"body": body["body"], "created": fake.next_timestamp()})
                self._reply(201)

            def do_PUT(self):
                body = self._read()
                fake.requests.append(("PUT", self.path, body))
                key = urlparse(self.path).path.split("/issue/")[1]
                fake.issues[key]["labels"] = body["fields"]["labels"]
                self._reply(204)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self._clock = 0

    # -- state ----------------------------------------------------------

    def next_timestamp(self):
        self._clock += 1
        return f"2026-08-17T19:{self._clock:02d}:00.000+0800"

    def add_issue(self, key, status, labels=None, parent=None, comments=None,
                  kind="Task", blocked_by=None):
        """comments: bodies, oldest first (the order Jira stores them in).
        blocked_by: [(key, status)] rendered as "is blocked by" issue links."""
        self.issues[key] = {
            "status": status,
            "labels": list(labels or []),
            "parent": parent,               # (parent_key, issuetype) or None
            "comments": [{"body": b, "created": self.next_timestamp()} for b in (comments or [])],
            "kind": kind,
            "blocked_by": list(blocked_by or []),
        }

    def labels_of(self, key):
        return self.issues[key]["labels"]

    def status_of(self, key):
        return self.issues[key]["status"]

    def comments_of(self, key):
        return [c["body"] for c in self.issues[key]["comments"]]

    def writes(self):
        return [(m, urlparse(p).path, b) for (m, p, b) in self.requests if m in ("POST", "PUT")]

    def wrote_to(self, key):
        return [(m, p, b) for (m, p, b) in self.writes() if f"/issue/{key}" in p]

    # -- payloads built off the recorded shapes ---------------------------

    def issue_payload(self, key):
        record = self.issues[key]
        payload = copy.deepcopy(self.issue_template)
        payload["key"] = key
        fields = payload["fields"]
        fields["status"]["name"] = record["status"]
        fields["labels"] = list(record["labels"])
        fields["comment"]["comments"] = self._comment_objects(record)
        fields["comment"]["total"] = len(record["comments"])
        fields["issuetype"] = dict(fields.get("issuetype") or {}, name=record["kind"])
        fields["issuelinks"] = [
            {"type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
             "inwardIssue": {"key": blocker, "fields": {"status": {"name": status}}}}
            for blocker, status in record["blocked_by"]
        ]
        if record["parent"]:
            parent_key, issue_type = record["parent"]
            template_parent = copy.deepcopy(self.issue_template["fields"].get("parent") or {
                "key": "E-1", "fields": {"summary": "REDACTED TEXT", "issuetype": {"name": "Epic"}}})
            template_parent["key"] = parent_key
            template_parent.setdefault("fields", {}).setdefault("issuetype", {})["name"] = issue_type
            fields["parent"] = template_parent
        else:
            fields.pop("parent", None)
        return payload

    def _comment_objects(self, record):
        template = (self.comments_template["comments"] or [{}])[0]
        objects = []
        for comment in record["comments"]:
            obj = copy.deepcopy(template)
            obj["body"] = comment["body"]
            obj["created"] = comment["created"]
            objects.append(obj)
        return objects

    def comments_payload(self, key):
        """The endpoint the code calls with orderBy=-created — newest first."""
        objects = self._comment_objects(self.issues[key])
        return {"comments": list(reversed(objects)), "maxResults": 50, "startAt": 0, "total": len(objects)}

    def search_payload(self, jql, limit=50):
        """Truncates like the real endpoint: a filter left out of the query is a
        filter applied to a page the server already cut short."""
        clauses = JQL_CLAUSE.findall(jql.split(" ORDER BY ")[0])
        payload = copy.deepcopy(self.search_template)
        matched = [
            {"key": key, "fields": {"status": {"name": record["status"]},
                                    "labels": list(record["labels"]),
                                    "summary": f"summary of {key}",
                                    "parent": {"key": record["parent"][0]} if record["parent"] else None}}
            for key, record in self.issues.items()
            if jql_matches(clauses, key, record)
        ]
        payload["issues"] = matched[:limit]
        payload["isLast"] = len(matched) <= limit
        return payload

    def shutdown(self):
        self.server.shutdown()


# ---------------------------------------------------------------- bitbucket

class FakeBitbucket:
    """Pull requests filtered the way Bitbucket filters them: by `q` on the source
    branch and by repeated `state` parameters, newest first."""

    def __init__(self, page_size=50):
        self.requests = []
        self.prs = []
        self.commits = {}
        self.comments = {}
        self.fail_paths = {}                # path fragment -> status code, for transport failures
        self.page_size = page_size          # small value exercises pagination
        self.pr_template = fixture("bitbucket_pullrequests.json")["values"][0]
        self.created = []
        self.commit_template = fixture("bitbucket_commit.json")
        self.comment_template = (fixture("bitbucket_pr_comments.json")["values"] or [{
            "content": {"raw": "REDACTED TEXT"}, "inline": None}])[0]
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code, payload=None):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload is not None:
                    self.wfile.write(json.dumps(payload).encode())

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else {}
                fake.requests.append(self.path)
                if self.path.endswith("/pullrequests"):
                    pr = fake.add_pr(900 + len(fake.created),
                                     body["source"]["branch"]["name"], "OPEN",
                                     dest=body["destination"]["branch"]["name"],
                                     description=body.get("description", ""))
                    fake.created.append(body)
                    return self._reply(201, pr)
                self._reply(404, {})

            def do_GET(self):
                fake.requests.append(self.path)
                for fragment, code in fake.fail_paths.items():
                    if fragment in self.path:
                        return self._reply(code, {"error": {"message": "boom"}})
                parsed = urlparse(self.path)
                path, query = parsed.path, parse_qs(parsed.query)
                if "/commit/" in path:
                    sha = path.split("/commit/")[1]
                    return self._reply(200, fake.commit_payload(sha))
                if path.endswith("/comments"):
                    pr_id = int(path.split("/pullrequests/")[1].split("/")[0])
                    return self._reply(200, {"values": fake.comment_objects(pr_id)})
                if path.endswith("/pullrequests"):
                    return self._reply(200, fake.listing(query, self.path))
                self._reply(404, {})

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def add_pr(self, pr_id, branch, state, updated="2026-08-17T11:00:00+00:00",
               dest="dev", merge_sha=None, description="", comments=None):
        pr = copy.deepcopy(self.pr_template)
        pr["id"] = pr_id
        pr["state"] = state
        pr["source"]["branch"]["name"] = branch
        pr["destination"]["branch"]["name"] = dest
        pr["updated_on"] = updated
        pr["description"] = description
        pr["summary"] = {"raw": description, "type": "rendered"}
        pr["links"] = {"html": {"href": f"https://bitbucket.org/testws/testrepo/pull-requests/{pr_id}"}}
        if merge_sha:
            pr["merge_commit"] = {"hash": merge_sha, "type": "commit"}
        else:
            pr.pop("merge_commit", None)
        self.prs.append(pr)
        if comments:
            self.comments[pr_id] = comments
        return pr

    def add_commit(self, sha, parents):
        self.commits[sha] = parents

    def commit_payload(self, sha):
        payload = copy.deepcopy(self.commit_template)
        payload["hash"] = sha
        payload["parents"] = [{"hash": p, "type": "commit"} for p in self.commits.get(sha, [])]
        return payload

    def comment_objects(self, pr_id):
        objects = []
        for entry in self.comments.get(pr_id, []):
            obj = copy.deepcopy(self.comment_template)
            obj["content"] = {"raw": entry["raw"], "type": "rendered"}
            obj["inline"] = entry.get("inline")
            objects.append(obj)
        return objects

    def listing(self, query, full_path):
        """Applies the `q` source-branch filter, the repeated `state` filter and
        `-updated_on` sort, then paginates like the real API does."""
        matched = self.prs
        q = (query.get("q") or [""])[0]
        branch = re.search(r'source\.branch\.name\s*=\s*"([^"]+)"', q)
        if branch:
            matched = [pr for pr in matched if pr["source"]["branch"]["name"] == branch.group(1)]
        states = query.get("state") or []
        if states:
            matched = [pr for pr in matched if pr["state"] in states]
        matched = sorted(matched, key=lambda pr: pr["updated_on"], reverse=True)
        page = int((query.get("page") or ["1"])[0])
        start = (page - 1) * self.page_size
        window = matched[start:start + self.page_size]
        payload = {"values": window, "pagelen": self.page_size, "page": page, "size": len(matched)}
        if start + self.page_size < len(matched):
            separator = "&" if "?" in full_path else "?"
            base = full_path.split("&page=")[0]
            payload["next"] = f"{self.url}{base}{separator}page={page + 1}"
        return payload

    def shutdown(self):
        self.server.shutdown()
