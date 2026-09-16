---
max_turns: 50
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep]
append_system_prompt: |
__CHARTER:qa,agent-common__
---

Project: the current working directory — find it with `Glob` on `.claude/dma/config.yml` (the absolute path it returns is the prefix). Area: shipments. Workspace: the same directory, checked out on `ai/PROJ-301`. Issue: PROJ-301.

Verification focus for this run: (1) run `.venv/bin/python -m pytest apps/shipments/tests` as a blocking foreground Bash call with adequate timeout and confirm it is green; (2) confirm the advance/ship gate end to end.

The tracker CLI is unavailable in this environment: treat the block below as the output of `dma issue read PROJ-301`, and instead of calling `dma issue handoff`, end with the exact report body you would post followed by the exact handoff command you would run. The diff of this task touches exactly `apps/shipments/service.py`, `apps/shipments/router.py`, `apps/shipments/tests/test_service.py`.

<dma-issue-read key="PROJ-301">
key: PROJ-301
title: Shipments: linear status transitions and operator listing
status: QA
labels: agent:qa, area:shipments
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
🤖 dev (shipments): handoff → qa
Second attempt on ai/PROJ-301 — reviewer's five findings addressed. Files: apps/shipments/service.py, apps/shipments/router.py, apps/shipments/tests/test_service.py. Tests: 4 passed.
## Self-review
Rejection: 5 points — fixed apps/shipments/service.py:11, fixed apps/shipments/service.py:10,16, fixed apps/shipments/service.py:22, fixed apps/shipments/service.py:10,15, fixed apps/shipments/service.py:32
Requirements: sorted, delivered hidden → service.py:10; test test_list_hides_delivered_by_default | full history → service.py:15; test test_list_includes_delivered_when_asked | advance one step → service.py:21; test test_advance_moves_one_step | delivered refused → service.py:25; test test_advance_from_delivered_is_invalid | ship records carrier+tracking → service.py:32; test —
Test contract: none in issue
DEV-COMMENTS: grep -nE '^\s*(#|""")' apps/shipments/service.py → clean
DEV-FN-SHAPE: 5 functions checked → clean

🤖 dev (shipments): first attempt pushed on ai/PROJ-301 — list, advance, ship implemented; Tests: 4 passed.
</dma-issue-read>
