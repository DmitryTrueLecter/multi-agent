---
name: sentinel-flag
description: Record a prompt/process problem for sentinel to review. Creates a Task issue in the tracker's Sentinel queue (status sentinel_inbox; labels sentinel-flag + flag-type:<type> + agent:sentinel). Runs alongside the caller's task; invoke once per defect — creation and the Sentinel-queue transition are one unit the skill completes internally. Invocation: /dma:sentinel-flag <type> "<problem>" where:<file:section> [originating:<KEY>] [details:<text>].
tools: Read, mcp__atlassian__jira_create_issue, mcp__atlassian__jira_transition_issue, mcp__linear__save_issue
---

# sentinel-flag

Create a Task issue in the tracker's Sentinel queue describing a defect in an agent prompt, skill, or process step. Sentinel triages the queue when invoked.

## Usage

`/dma:sentinel-flag <type> "<problem>" where:<file:section> [originating:<KEY>] [details:<text>]`

| Argument | Required | Description |
|----------|----------|-------------|
| `<type>` | yes | One of the types below |
| `<problem>` | yes | One-line description of the **problem**, not the task. English. |
| `where:<file:section>` | yes | Prompt/skill location of the defect (e.g. `agents/dev.md / ## Task workflow step 2a`). |
| `originating:<KEY>` | optional | Task during which it surfaced — context only. |
| `details:<text>` | optional | What you tried, what blocked, what you suspect. |

## Types

| Type | Trigger |
|------|---------|
| `PROMPT-UNCLEAR` | Instruction unfollowable without guessing. |
| `PROMPT-INCOMPLETE` | Workflow has no path for a case that actually occurred. |
| `PROMPT-CONTRADICTION` | Two instructions can't both be true. |
| `PROMPT-FRAGMENTED` | Rule extended by appending; voices conflict. |
| `PROMPT-SCOPE-LEAK` | Agent instructed into another agent's territory. |
| `RULE-CONTRADICTION` | Rule vs its detection method, or two rules vs same fragment. |
| `ARCH-ROLE-GAP` | No agent owns a needed responsibility. |
| `ARCH-ROLE-OVERLAP` | Two agents handle the same thing, no delegation declared. |
| `ENV-FRICTION` | Hook/credential/binary blocks a prescribed command, no fallback. |
| `PATTERN-REPEAT` | Same mistake across unrelated tasks; prescribed steps produce it. |

## Steps

1. Reject if `<type>` is not in the Types table or `where:` is missing.
2. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks.provider`, `tasks.workflow.statuses.sentinel_inbox` (display name). For jira also read `tasks.project_key` and `tasks.jira.transitions.sentinel_inbox`; for linear also read `tasks.team_key`.
3. Set `reporter` to your own agent role (e.g. `dev`, `qa`, `reviewer`, `architect`, `devops`).
4. Build the summary `[<TYPE>] <problem>` and the description (Markdown):
   - `**Where:** <file:section>`
   - `**Reporter:** <reporter>`
   - `**Originating:** <KEY>` — only if `originating:` given
   - `**Details:** <text>` — only if `details:` given
5. Build the label set: `sentinel-flag`, `flag-type:<type>` (lowercase the type, e.g. `PROMPT-UNCLEAR` → `flag-type:prompt-unclear`), `agent:sentinel`.
6. Create the issue per provider:
   - **jira:** call `mcp__atlassian__jira_create_issue` with `project_key`, `issue_type="Task"`, `summary`, `description`, `additional_fields={"labels": [<labels>]}`. Capture the new key. A new issue's birth status is set by the project's workflow and varies across projects, so drive and verify against the target `sentinel_inbox` status only. Read `tasks.jira.transitions.sentinel_inbox`: if missing or `0`, fail with `jira transition id for 'sentinel_inbox' not configured; run /dma:sentinel-bootstrap-jira` and return the new key for cleanup. Otherwise call `mcp__atlassian__jira_transition_issue(issue_key=<new-key>, transition_id=<id>)` and re-read the issue. If its status equals the `sentinel_inbox` display name, the flag is placed. If its status equals any other value, call the transition once more and re-read; a status still not equal to the `sentinel_inbox` display name after that second attempt is failure — return `flag <new-key> created but stuck in <current-status> — transition to Sentinel failed` so the caller surfaces it.
   - **linear:** call `mcp__linear__save_issue` (omit `id`) with `team=<team_key>`, `title=<summary>`, `description`, `labels=[<labels>]`, `state=<sentinel_inbox display name>`. If the returned status does not match, call `mcp__linear__save_issue(id=<new-key>, state=<sentinel_inbox display name>)` once to correct it.
7. Verify by re-reading the key you already created, never by re-invoking this skill. Re-read `<new-key>`: a status equal to the `sentinel_inbox` display name returns `flagged → <new-key>`. A status not equal to it seconds after a successful transition may be read-after-write lag — re-read the same key once. Return step 6's failure string only when its two-attempt transition is exhausted. Once step 6 returns a key, this invocation carries it to completion and never creates again.
