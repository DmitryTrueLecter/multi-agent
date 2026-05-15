---
name: pr-open
description: Open a pull request from a source branch to a destination branch. Derives repo coordinates from the git remote URL. Returns the PR URL on success or an error on failure. Invocation: /pr-open <source-branch> <destination-branch> <title> [workspace-path:<path>] [remote:<name>] [description:<text>].
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

1. Read `.claude/config.yml` → `tasks.provider`.
2. Follow the section for your provider.

---

## jira

Uses Bitbucket MCP.

1. In the workspace (subshell — do not change cwd):
   ```
   ( cd <workspace-path> && git remote get-url <remote> )
   # → git@bitbucket.org:<bitbucket-workspace>/<repo>.git
   #   or https://bitbucket.org/<bitbucket-workspace>/<repo>.git
   ```
   Strip `.git`, read the two trailing segments: `<bitbucket-workspace>` and `<repo-slug>`.
2. Call `mcp__atlassian__bitbucket_create_pull_request`:
   - `workspace`: `<bitbucket-workspace>`
   - `repo_slug`: `<repo-slug>`
   - `source_branch`: `<source-branch>`
   - `destination_branch`: `<destination-branch>`
   - `title`: `<title>`
   - `description`: `<description>` if provided
3. Return the PR URL from the response, or the error. Do not handle errors — caller decides.

---

## linear

Uses GitHub CLI.

1. In the workspace (subshell — do not change cwd):
   ```
   ( cd <workspace-path> && \
     gh pr create \
       --title "<title>" \
       --body "<description or empty>" \
       --base <destination-branch> \
       --head <source-branch> )
   ```
2. Capture the PR URL from stdout.
3. Return the PR URL, or the error (non-zero exit). Do not handle errors — caller decides.
