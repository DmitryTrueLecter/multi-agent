---
name: pr-open
description: Open a pull request from a source branch to a destination branch. Routes by VCS host (GitHub / Bitbucket) derived from the git remote URL, not by the issue tracker. Returns the PR URL on success or an error on failure. Invocation: /dma:pr-open <source-branch> <destination-branch> <title> [workspace-path:<path>] [remote:<name>] [description:<text>].
tools: Bash, mcp__atlassian__bitbucket_create_pull_request
---

# pr-open

Open a pull request for a branch.

## Usage

`/dma:pr-open <source-branch> <destination-branch> <title> [options]`

| Argument | Description |
|----------|-------------|
| `<source-branch>` | Branch with the changes (e.g. `ai/PROJ-123`) |
| `<destination-branch>` | Target branch (e.g. `ai/PROJ-EPIC-50` or `develop`) |
| `<title>` | PR title |
| `workspace-path:<path>` | Absolute path to the git workspace (default: cwd) |
| `remote:<name>` | Git remote name (default: `origin`) |
| `description:<text>` | PR description body (optional) |

## Steps

1. Resolve the remote URL in the workspace (subshell — do not change cwd):
   ```
   ( cd <workspace-path> && git remote get-url <remote> )
   ```
2. Branch on the **host** in that URL: `bitbucket.org` → the `## bitbucket` section; `github.com` → the `## github` section. PR routing follows the repository host, never the issue tracker.

---

## bitbucket

Uses Bitbucket MCP.

1. From the remote URL (`git@bitbucket.org:<workspace>/<repo>.git` or `https://bitbucket.org/<workspace>/<repo>.git`), strip `.git` and read the two trailing segments: `<bitbucket-workspace>` and `<repo-slug>`.
2. Call `mcp__atlassian__bitbucket_create_pull_request`:
   - `workspace`: `<bitbucket-workspace>`
   - `repo_slug`: `<repo-slug>`
   - `source_branch`: `<source-branch>`
   - `destination_branch`: `<destination-branch>`
   - `title`: `<title>`
   - `description`: `<description>` if provided
3. Return the PR URL from the response, or the error. Do not handle errors — caller decides.

---

## github

Uses GitHub CLI. Pass the body on stdin via `--body-file -`, not inline `--body`: a multi-line markdown body containing `|` (tables) is tokenized as shell pipes by the Bash allowlist and the call is refused. The heredoc keeps the body off the command line.

1. In the workspace (subshell — do not change cwd):
   ```
   ( cd <workspace-path> && gh pr create \
       --title "<title>" \
       --base <destination-branch> \
       --head <source-branch> \
       --body-file - <<'PR_BODY_EOF'
   <description or empty>
   PR_BODY_EOF
   )
   ```
2. Capture the PR URL from stdout.
3. Return the PR URL, or the error (non-zero exit). Do not handle errors — caller decides.
