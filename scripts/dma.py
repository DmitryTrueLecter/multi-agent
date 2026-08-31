#!/usr/bin/env python3
"""dma — plugin CLI for the agents. Run via bin/dma (plugin venv).

    dma issue  <read|claim|comment|handoff> ...   one named issue      — scripts/issue.py
    dma board  <reconcile|list> ...               searches the board   — scripts/board.py
    dma branch <prepare|sync-epic|checkout> ...   a task branch        — scripts/task_branch.py
    dma worktree <bootstrap|remove> ...           a task worktree      — scripts/worktree.py
    dma workspace <prepare|remove> ...            worktree + branch    — scripts/workspace.py
    dma pr open ...                               a pull request       — scripts/pr.py
    dma sentinel flag ...                         a prompt defect      — scripts/sentinel.py
"""

import sys

import board
import issue
import pr
import sentinel
import task_branch
import workspace
import worktree


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    group, rest = argv[1], argv[2:]
    if group == "issue":
        return issue.main(rest)
    if group == "branch":
        return task_branch.main(rest)
    if group == "worktree":
        return worktree.main(rest)
    if group == "workspace":
        return workspace.main(rest)
    if group == "pr":
        return pr.main(rest)
    if group == "sentinel":
        return sentinel.main(rest)
    if group == "board":
        return board.main(rest)
    print(__doc__.strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
