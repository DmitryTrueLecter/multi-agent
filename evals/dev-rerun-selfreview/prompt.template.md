---
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Edit, Write]
append_system_prompt: |
__CHARTER:dev__
---

Project: the current working directory — find it with `Glob` on `.claude/dma/config.yml` (the absolute path it returns is the prefix). Workspace: the same directory; it is already checked out on `ai/PROJ-301`. Area: shipments. Issue: PROJ-301.

Bash is unavailable in this environment: no git, no test run. Where the workflow runs `test_command`, record in the progress comment that the run is deferred and why, with no invented result. The tracker CLI is unavailable too: treat the block below as the output of `dma issue read PROJ-301`, and instead of calling `dma issue comment` / `dma issue handoff`, end with the exact comment body you would post followed by the exact handoff command you would run.

<dma-issue-read key="PROJ-301">
key: PROJ-301
title: Shipments: linear status transitions and operator listing
status: In Progress
labels: agent:dev, area:shipments
parent: null
blocked by: -

## description
## Purpose
Operators need a list of shipments still in motion and a single "advance" action that moves a shipment one step along created → packed → shipped → delivered.

## Requirements
- `list_shipments` returns shipments sorted by id, hiding delivered ones; a full-history variant includes them.
- `advance` moves a shipment exactly one step; advancing a delivered shipment is refused.
- `ship` records carrier and tracking number when a packed shipment leaves.

## Test contract
No architectural tests required — unit coverage sufficient.

## References
- `apps/shipments/models.py` — status literal and `with_status`.

## comments (2, newest first)
🤖 reviewer (shipments): handoff → dev
Verdict: BLOCK. Coverage: DEV-COMMENTS service.py 3 findings; DEV-FN-SHAPE service.py 2 findings; others clean.
[MEDIUM] [DEV-COMMENTS] apps/shipments/service.py:16-22 — six-line docstring restating the parameter; collapse to one why-line or delete.
[MEDIUM] [DEV-COMMENTS] apps/shipments/service.py:10,25 — section dividers `# === listing ===`, `# === transitions ===`.
[MEDIUM] [DEV-COMMENTS] apps/shipments/service.py:31 — comment embeds ticket ID `PROJ-77`; explain the invariant inline or drop.
[MEDIUM] [DEV-FN-SHAPE] apps/shipments/service.py:13 — `include_delivered: bool` is a behavioural mode switch; expose two functions.
[MEDIUM] [DEV-FN-SHAPE] apps/shipments/service.py:44 — `ship` takes 7 domain parameters, 4 of them unused (`weight_kg`, `service_level`, `insured`, `notify_email`); drop the unused ones or group.

🤖 dev (shipments): first attempt pushed on ai/PROJ-301 — list, advance, ship implemented; Tests: 4 passed.
</dma-issue-read>
