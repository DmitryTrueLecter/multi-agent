# Consultation mode — procedure

Sync invocation by team-lead only — return an inline answer; do not process the inbox.

## Invocation

```
Agent(subagent_type="dma:sentinel", prompt="Project: ${CLAUDE_PROJECT_DIR}. Mode: consultation. Question: <q>. Context: <c>.")
```

## Behavior

- Read only what the question requires — typically one or two agent/skill files, plus the cited issue if a `<KEY>` is in the context.
- Do not process the inbox. Return the answer inline.
- If the question reveals a defect another agent's run would also hit, call `/dma:sentinel-flag` to put it in the inbox for next triage.

## Scope guard

Technical questions (pattern, library, file split) → reply *"Out of scope — architect consultation."* and stop.

## Output

```markdown
## Question
<verbatim>

## Finding
Class: <ID from taxonomy or "advisory">
Cite file:section.

## Recommendation
Concrete next action team-lead can take now. For prompt rewrites, give the rewritten paragraph.

## Followup flag
<filename> via /dma:sentinel-flag — or "none".
```

## Cross-mode contracts

- Classify the finding against `agents/sentinel.md → ## Findings taxonomy`, or label `advisory` when no class fits.
- Compose `## Recommendation` rewrites under `agents/sentinel.md → ## Writing replacements`.
