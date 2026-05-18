---
name: sentinel-flag
description: Record a prompt/process problem for sentinel to review. Writes a file in .claude/sentinel-inbox/. Async; does not block the caller. Invocation: /sentinel-flag <type> "<problem>" where:<file:section> [originating:<KEY>] [details:<text>].
tools: Write
---

# sentinel-flag

Write a file in `<abs-project-root>/.claude/sentinel-inbox/` describing a defect in an agent prompt, skill, or process step. Sentinel reads the inbox when invoked.

## Usage

`/sentinel-flag <type> "<problem>" where:<file:section> [originating:<KEY>] [details:<text>]`

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

1. Reject if `<type>` not in the table or `where:` missing.
2. Filename: `<UTC-ISO>-<reporter>-<type>.md`, replacing `:` in the timestamp with `-`.
3. Build body — frontmatter (`type`, `reporter`, `where`, `created_at`, `originating_task` if given) + `## Problem` + optional `## Details`.
4. Write to `<abs-project-root>/.claude/sentinel-inbox/<filename>`. Create directory if missing.
5. Return `flagged → <filename>`.
