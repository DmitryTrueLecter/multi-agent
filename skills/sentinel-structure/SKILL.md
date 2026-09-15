---
name: sentinel-structure
description: "Sentinel structure procedure: sync intake from team-lead for create / modify / delete on project-local area and arch files — four gates, polish on pass, rejection block on fail. Invoked by the sentinel agent on `Mode: structure`."
user-invocable: false
---

# Sentinel structure

Apply or reject one create / modify / delete on a project-local area or arch file, on team-lead's behalf. Two legitimate callers, both routed by team-lead: architect-authored content forwarded verbatim from an approved recommendation, or team-lead's own scaffolding (introducing or dismantling an area, project init). Team-lead's invocation is the write authorization.

Invocation:
```
Agent(subagent_type="dma:sentinel", prompt="Project: ${CLAUDE_PROJECT_DIR}. Mode: structure. Op: <create|modify|delete>. Target: <path>. Content: <text or '—' for delete>. Rationale: <one line>.")
```

## Procedure

1. Resolve the operation:
   - `create` — target must not exist; content required.
   - `modify` — target must exist; content required.
   - `delete` — target must exist; content omitted.
2. Read `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/structure-gates.md`, `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/area-config-schema.md`, and — when the content touches labels, statuses, or queues — `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/status-invariants.md`.
3. Read the target (modify / delete) or the parent area / arch context (create): enough to see the file's voice, the surrounding rule corpus, and what the new content interacts with.
4. Run the four gates from `structure-gates.md` in order — scope, schema, quality, consistency. Stop at the first failure.
5. On a failing gate: print the rejection block from `structure-gates.md → ## Rejection block` and stop. Nothing is written; never a partial apply. Team-lead either revises (own scaffolding) or routes the failing criterion to architect (forwarded recommendation).
6. On pass:
   - `create` / `modify` — polish prose fields (`role:`, `guidelines:`, free-text `review_checks` strings) per the charter's `## Writing replacements`; substance — rule semantics, thresholds, grep patterns, IDs — stays as submitted. `Write` the file.
   - `delete` — remove the file or directory.
7. Report to team-lead: the operation, the target, and the diff (or "created" / "deleted").

## Not sentinel's call

Subjective architectural taste — whether a pattern is wise, whether a stack choice is right, whether a rule's substance is the best engineering call — routes to architect. A rule whose semantics you disagree with but that passes the four gates is applied.

<example>
## Rejection
Criterion: quality
Class: RULE-ORPHANED
Failing: the new `review_checks` entry `API-NO-RAW-SQL` names no ENFORCEMENT clause although a grep (`text\(` / `execute\(\s*"`) detects it mechanically.
To pass: append `ENFORCEMENT: grep -rnE 'text\(|\.execute\(\s*"' apps/api/ — any hit outside repositories/ is a violation.` to the rule string and resubmit.
</example>
