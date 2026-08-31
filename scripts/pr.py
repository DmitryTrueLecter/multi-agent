"""Pull requests: `dma pr open`.

    dma pr open <source-branch> <destination-branch> <title>
                [--body <text> | --body -] [--workspace <path>]

Routes by the host in the git remote — Bitbucket or GitHub (scripts/vcs.py) —
not by which tracker the project uses. Prints the PR URL, or the host's error.
Errors are not handled here: the caller decides, because a failed PR must leave
the task where it is rather than being handed on.

Exit codes: 0 ok · 1 error · 2 the remote is on a host with no backend
"""

import os
import sys

import issue


def main(argv):
    if len(argv) < 4 or argv[0] != "open":
        print(__doc__.strip(), file=sys.stderr)
        return 1
    source, destination, title = argv[1], argv[2], argv[3]

    body, workspace, rest = "", None, argv[4:]
    while rest:
        if rest[0] not in ("--body", "--workspace") or len(rest) < 2:
            issue.die(__doc__.strip())
        if rest[0] == "--body":
            body = sys.stdin.read().rstrip("\n") if rest[1] == "-" else rest[1]
        else:
            workspace = rest[1]
        rest = rest[2:]

    import vcs as vcs_module

    config = issue.load_config() if os.path.exists(issue.CONFIG_PATH) else {}
    remote = ((config.get("workspace") or {}) or {}).get("remote", "origin")
    workspace = workspace or issue.PROJECT_DIR
    try:
        host = vcs_module.open_vcs(workspace, issue.MCP_PATH, remote)
        url = host.create_pull_request(source, destination, title, body)
    except vcs_module.Unsupported as e:
        issue.die(str(e), 2)
    except vcs_module.VcsError as e:
        issue.die(str(e))
    print(url)
    return 0
