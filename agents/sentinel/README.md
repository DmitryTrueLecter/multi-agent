# Sentinel reference

Files the sentinel agent reads on demand. The agent's charter is `agents/sentinel.md`; each mode's procedure is a skill under `skills/sentinel-<mode>/SKILL.md` (triage, consultation, structure, task, full-audit, retrospective, healthcheck) and names which of these files to read and when.

| File | What it holds | Read when |
|---|---|---|
| `patterns/*.md` | One recurring problem shape per file: signature, observed instances, triage rule. Stack-agnostic. | Priming step of triage, consultation, full-audit, retrospective. |
| `solutions/*.md` | Conditional recommendations: an IF-condition on an area's properties, a THEN-recommendation. | A flag names an area; apply those whose condition the area meets. |
| `task-schema.md` | Issue description blocks, comment blocks, who writes and reads each at which stage. | Priming; any flag about a description section, a handoff comment, or who-reads-what. |
| `area-config-schema.md` | Canonical schema of `areas/<area>/area.yml` and role overlays: fields, readers, what goes where. | Flags about area-config gaps; structure and task gates; architect proposals adding fields. |
| `structure-gates.md` | The four gates (scope, schema, quality, consistency) and the rejection block. | Structure mode; task-mode self-check. |
| `plugin-layers.md` | The shared-plugin vs project-local trees. | A finding's scope tag is in doubt. |
| `agent-roles.md` | The role table, the tracked-queue set for `agent:<role>`, and `## Settled decisions` — role-scope decisions the user has made (QA runs nothing, …). | Role-gap / role-overlap flags; label checks; any flag or question about what a role may do. |
| `status-invariants.md` | Status vs `agent:` label rules and the proposals to reject. | Anything touching labels, statuses, or queues. |
| `templates/` | Files healthcheck materializes into a project (`arch.yml`, `environments.md`, `product/*`). | Healthcheck auto-fix. |

Maintenance:
- A flag that generalizes beyond its first instance → new `patterns/` entry, linked from the flag's resolution.
- A fix shape that applies to every area meeting some condition → new `solutions/` entry.
- A schema fix that introduces a new `area.yml` field → update `area-config-schema.md` in the same pass.
- `task-schema.md` or `area-config-schema.md` disagreeing with the current agent files is itself a finding — reconcile in the same pass.
