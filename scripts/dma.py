#!/usr/bin/env python3
"""dma — plugin CLI for the agents. Run via bin/dma (plugin venv).

    dma issue      <read|claim|comment|handoff> ...   see scripts/issue.py
    dma branch     <dev-start|checkout> ...            see scripts/task_branch.py
    dma pr-feedback                                    see scripts/pr_feedback.py
"""

import sys

import issue
import pr_feedback
import task_branch


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    group, rest = argv[1], argv[2:]
    if group == "issue":
        return issue.main(rest)
    if group == "branch":
        return task_branch.main(rest)
    if group == "pr-feedback":
        return pr_feedback.main(rest)
    print(__doc__.strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
