---
name: pr-open
description: Open a pull request from a source branch to a destination branch. Derives the VCS platform repo coordinates from the git remote URL. Returns the PR URL on success or the error on failure. Invocation: /pr-open <source-branch> <destination-branch> <title> [workspace-path:<path>] [remote:<name>] [description:<text>].
tools: mcp__atlassian__bitbucket_create_pull_request
---

# pr-open

Open a pull request for a branch.

## Usage

`/pr-open <source-branch> <destination-branch> <title> [options]`

| Argument | Description |
|----------|-------------|
| `<source-branch>` | Branch with the changes (e.g. `ai/PROJ-123`) |
| `<destination-branch>` | Target branch (e.g. `ai/PROJ-EPIC-50` or `develop`) |
| `<title>` | PR title |
| `workspace-path:<path>` | Absolute path to the git workspace (default: cwd) |
| `remote:<name>` | Git remote name (default: `origin`) |
| `description:<text>` | PR description body (optional) |

## Steps

1. Determine the workspace path (from `workspace-path:` argument or cwd) and the remote name (from `remote:` argument or `origin`).

2. Derive the VCS platform repo coordinates from the git remote URL. In the workspace (use a subshell — do not change cwd):
   ```
   ( cd <workspace-path> && git remote get-url <remote> )
   # → git@bitbucket.org:<bitbucket-workspace>/<repo>.git
   #   or https://bitbucket.org/<bitbucket-workspace>/<repo>.git
   ```
   Strip the `.git` suffix and read the two trailing path segments: `<bitbucket-workspace>` and `<repo-slug>`.

3. Call `mcp__atlassian__bitbucket_create_pull_request` with:
   - `workspace`: `<bitbucket-workspace>`
   - `repo_slug`: `<repo-slug>`
   - `source_branch`: `<source-branch>`
   - `destination_branch`: `<destination-branch>`
   - `title`: `<title>`
   - `description`: `<description>` if provided

4. Return the PR URL from the MCP response to the caller. If PR creation fails, return the error — do **not** handle it; the calling context decides what to do.
