"""One shape for a pull request, whichever host it lives on.

`dma board reconcile` reads the user's merge/decline decision, and `dma pr open`
publishes a branch for review. Both used to exist only for Bitbucket, while the
GitHub half lived in prompt prose — so a Jira project on GitHub had no path at
all. Each backend answers in the same shape:

    {"id", "state", "url", "branch", "destination", "updated", "description"}

`state` is normalized to OPEN / MERGED / DECLINED / SUPERSEDED: GitHub calls a
declined pull request CLOSED, Bitbucket calls it DECLINED, and the reconciliation
rules are written once against the normalized word.

GitHub is reached through `gh` when it is on PATH — it carries the user's own
credentials — and through the REST API with `GITHUB_TOKEN` / `GH_TOKEN` otherwise.
"""

import base64
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

PR_STATES = ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")


class VcsError(Exception):
    pass


class Unsupported(Exception):
    """The remote is on a host with no backend here; the caller falls back."""


def git_remote_url(repo_path, remote="origin"):
    result = subprocess.run(["git", "-C", repo_path, "remote", "get-url", remote],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise VcsError(f"could not read git remote '{remote}': {result.stderr.strip()}")
    return result.stdout.strip()


def split_remote(remote_url, host):
    """`git@host:owner/repo.git`, `https://host/owner/repo`, and the
    credential-bearing `https://x-token-auth:…@host/owner/repo.git` all reduce to
    (owner, repo)."""
    tail = remote_url.split(host, 1)[1].lstrip(":/")
    if tail.endswith(".git"):
        tail = tail[:-4]
    parts = tail.split("/")
    if len(parts) < 2:
        raise VcsError(f"could not parse owner/repo from remote '{remote_url}'")
    return parts[0], parts[1]


# ---------------------------------------------------------------- bitbucket

class Bitbucket:
    host = "bitbucket.org"
    name = "bitbucket"

    def __init__(self, remote_url, mcp_path):
        self.workspace, self.repo = split_remote(remote_url, self.host)
        creds = {}
        if os.path.exists(mcp_path):
            with open(mcp_path) as f:
                creds = json.load(f).get("mcpServers", {}).get("atlassian", {}).get("env", {})
        url = creds.get("BITBUCKET_URL") or os.environ.get("BITBUCKET_URL") or "https://bitbucket.org"
        user = creds.get("BITBUCKET_USERNAME") or os.environ.get("BITBUCKET_USERNAME")
        token = creds.get("BITBUCKET_APP_PASSWORD") or os.environ.get("BITBUCKET_APP_PASSWORD")
        if not (user and token):
            raise VcsError("Bitbucket credentials not found: need BITBUCKET_USERNAME and "
                           f"BITBUCKET_APP_PASSWORD in {mcp_path} (mcpServers.atlassian.env) "
                           "or in the environment")
        self.base = api_base(url)
        self.auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

    # -- transport ------------------------------------------------------

    def call(self, path, method="GET", body=None):
        url = path if path.startswith("http") else self.base + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", self.auth)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            raise VcsError(f"Bitbucket HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
        return json.loads(raw) if raw else None

    def paginate(self, path, max_pages=20):
        results, pages = [], 0
        while path and pages < max_pages:
            page = self.call(path)
            results.extend(page.get("values") or [])
            path = page.get("next")
            pages += 1
        return results

    def _repo(self, suffix):
        return f"/repositories/{self.workspace}/{self.repo}{suffix}"

    # -- reads ----------------------------------------------------------

    def _normalize(self, pr):
        return {
            "id": pr["id"],
            "state": pr.get("state"),
            "url": ((pr.get("links") or {}).get("html") or {}).get("href", ""),
            "branch": (pr.get("source") or {}).get("branch", {}).get("name", ""),
            "destination": (pr.get("destination") or {}).get("branch", {}).get("name", ""),
            "updated": pr.get("updated_on") or "",
            "description": ((pr.get("summary") or {}).get("raw")) or pr.get("description") or "",
            "_merge_commit": (pr.get("merge_commit") or {}).get("hash"),
        }

    def pull_requests_for_branch(self, branch):
        params = [("q", f'source.branch.name="{branch}"')]
        params += [("state", state) for state in ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")]
        params += [("sort", "-updated_on"), ("pagelen", 50)]
        found = self.paginate(self._repo(f"/pullrequests?{urllib.parse.urlencode(params)}"))
        return sorted((self._normalize(pr) for pr in found), key=lambda pr: pr["updated"], reverse=True)

    def merge_source_tip(self, pr):
        """parents[1] of the merge commit is what landed from the source branch.
        A squash or fast-forward merge has one parent and no reliable tip."""
        sha = pr.get("_merge_commit")
        if not sha:
            return None
        parents = self.call(self._repo(f"/commit/{sha}")).get("parents") or []
        return parents[1].get("hash") if len(parents) > 1 else None

    def comments(self, pr):
        out = []
        for comment in self.paginate(self._repo(f"/pullrequests/{pr['id']}/comments?pagelen=50"), max_pages=10):
            raw = ((comment.get("content") or {}).get("raw") or "").strip()
            if raw:
                out.append({"body": raw, "inline": comment.get("inline")})
        return out

    # -- writes ---------------------------------------------------------

    def create_pull_request(self, source, destination, title, description=""):
        created = self.call(self._repo("/pullrequests"), method="POST", body={
            "title": title,
            "source": {"branch": {"name": source}},
            "destination": {"branch": {"name": destination}},
            "description": description or "",
        })
        return ((created.get("links") or {}).get("html") or {}).get("href", "")


def api_base(bitbucket_url):
    """Cloud REST lives on api.bitbucket.org/2.0; the configured URL is the web
    host. A non-Cloud base (a test server) is used verbatim with /2.0 appended."""
    base = bitbucket_url.rstrip("/")
    if "bitbucket.org" in base and "api." not in base:
        return "https://api.bitbucket.org/2.0"
    return base if base.endswith("/2.0") else base + "/2.0"


# ------------------------------------------------------------------- github

GITHUB_STATE = {"OPEN": "OPEN", "MERGED": "MERGED", "CLOSED": "DECLINED"}


class GitHub:
    host = "github.com"
    name = "github"

    def __init__(self, remote_url, mcp_path, repo_path="."):
        self.owner, self.repo = split_remote(remote_url, self.host)
        self.repo_path = repo_path
        self.gh = shutil.which("gh")
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not self.gh and not self.token:
            raise VcsError("GitHub needs either the `gh` CLI on PATH or GITHUB_TOKEN / GH_TOKEN "
                           "in the environment")

    # -- transport ------------------------------------------------------

    def api(self, path, method="GET", body=None):
        """`gh api` when it is there — it already holds the user's credentials —
        otherwise the REST endpoint with a token."""
        if self.gh:
            command = [self.gh, "api", "-X", method, f"repos/{self.owner}/{self.repo}{path}"]
            if body is not None:
                command += ["--input", "-"]
            result = subprocess.run(command, cwd=self.repo_path, capture_output=True, text=True,
                                    input=json.dumps(body) if body is not None else None)
            if result.returncode != 0:
                raise VcsError(f"gh api {path}: {result.stderr.strip()[:500]}")
            return json.loads(result.stdout) if result.stdout.strip() else None

        url = f"https://api.github.com/repos/{self.owner}/{self.repo}{path}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            raise VcsError(f"GitHub HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
        return json.loads(raw) if raw else None

    # -- reads ----------------------------------------------------------

    def _normalize(self, pr):
        state = "MERGED" if pr.get("merged_at") else GITHUB_STATE.get(pr.get("state", "").upper(), "OPEN")
        return {
            "id": pr["number"],
            "state": state,
            "url": pr.get("html_url", ""),
            "branch": (pr.get("head") or {}).get("ref", ""),
            "destination": (pr.get("base") or {}).get("ref", ""),
            "updated": pr.get("updated_at") or "",
            "description": pr.get("body") or "",
            "_merge_commit": pr.get("merge_commit_sha"),
        }

    def pull_requests_for_branch(self, branch):
        query = urllib.parse.urlencode({"head": f"{self.owner}:{branch}", "state": "all",
                                        "sort": "updated", "direction": "desc", "per_page": 50})
        found = self.api(f"/pulls?{query}") or []
        return [self._normalize(pr) for pr in found]

    def merge_source_tip(self, pr):
        sha = pr.get("_merge_commit")
        if not sha:
            return None
        parents = (self.api(f"/commits/{sha}") or {}).get("parents") or []
        return parents[1].get("sha") if len(parents) > 1 else None

    def comments(self, pr):
        out = []
        for comment in self.api(f"/issues/{pr['id']}/comments?per_page=100") or []:
            body = (comment.get("body") or "").strip()
            if body:
                out.append({"body": body, "inline": None})
        for comment in self.api(f"/pulls/{pr['id']}/comments?per_page=100") or []:
            body = (comment.get("body") or "").strip()
            if body:
                out.append({"body": body,
                            "inline": {"path": comment.get("path"), "to": comment.get("line")}})
        return out

    # -- writes ---------------------------------------------------------

    def create_pull_request(self, source, destination, title, description=""):
        created = self.api("/pulls", method="POST", body={
            "title": title, "head": source, "base": destination, "body": description or ""})
        return (created or {}).get("html_url", "")


# ------------------------------------------------------------------ factory

BACKENDS = (Bitbucket, GitHub)


def open_vcs(repo_path, mcp_path, remote="origin"):
    remote_url = git_remote_url(repo_path, remote)
    for backend in BACKENDS:
        if backend.host in remote_url:
            return backend(remote_url, mcp_path) if backend is Bitbucket \
                else backend(remote_url, mcp_path, repo_path)
    raise Unsupported(f"remote '{remote_url}' is on no host this CLI knows "
                      f"({', '.join(b.host for b in BACKENDS)})")
