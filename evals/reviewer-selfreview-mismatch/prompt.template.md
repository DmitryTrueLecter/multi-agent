---
max_turns: 50
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep]
append_system_prompt: |
__CHARTER:reviewer__
---

Project: the current working directory — find it with `Glob` on `.claude/dma/config.yml` (the absolute path it returns is the prefix). Workspace: the same directory, checked out on `ai/PROJ-301`. Area: shipments. Issue: PROJ-301.

Bash is unavailable in this environment: no git. The diff of this task against its base touches exactly these files — `apps/shipments/service.py`, `apps/shipments/router.py`, `apps/shipments/tests/test_service.py` — read them in full as the diff, and run the pre-checks and sweeps with `Grep`. The tracker CLI is unavailable: treat the block below as the output of `dma issue read PROJ-301`, and instead of calling `dma issue handoff` / `dma pr open` / `dma branch verify-remote`, end with the exact review (Output format) followed by the exact handoff command you would run.

<dma-issue-read key="PROJ-301">
key: PROJ-301
title: Shipments: linear status transitions and operator listing
status: Code Review
labels: agent:reviewer, area:shipments
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

## comments (4, newest first)
🤖 qa (shipments): handoff → reviewer
## Coverage
[PASS] requirement — list_shipments sorted by id, hiding delivered; full-history variant
[PASS] requirement — advance moves exactly one step; delivered refused
[PASS] requirement — ship records carrier and tracking number
[N/A]  test_contract — No architectural tests required
[PASS] test_quality — assertions meaningful, in-memory store at the boundary
## Runtime checks deferred (team-lead close-out)
- `.venv/bin/python -m pytest apps/shipments/tests` — test_command

🤖 dev (shipments): second attempt on ai/PROJ-301 — reviewer's five findings addressed. Files: apps/shipments/service.py, apps/shipments/router.py, apps/shipments/tests/test_service.py. Tests: 6 passed.
## Self-review
Rejection: 5 points — fixed apps/shipments/service.py:11 (docstring → one line), fixed apps/shipments/service.py:10,16 (dividers removed), fixed apps/shipments/service.py:22 (PROJ-77 comment dropped), fixed apps/shipments/service.py:10,15 (include_delivered split into list_shipments / list_all_shipments), fixed apps/shipments/service.py:32 (ship 7 → 3 domain params)
Requirements: sorted, delivered hidden → service.py:10; test test_list_hides_delivered_by_default | full history → service.py:15; test test_list_includes_delivered_when_asked | advance one step → service.py:21; test test_advance_moves_one_step | delivered refused → service.py:25; test test_advance_from_delivered_is_invalid | ship records carrier+tracking → service.py:32; test test_ship_records_carrier
Test contract: none in issue
DEV-YAGNI: 1 new function list_all_shipments, caller router.py:14
Boundary code: none
Single source: none new
DEV-COMMENTS: grep -nE '^\s*(#|""")' apps/shipments/service.py → clean
DEV-FN-SHAPE: 5 functions checked → clean
DEV-NAMING: grep -nE '\b(data|result|tmp|handle|process)\b' apps/shipments/service.py → clean
DEV-SPLIT: LOC service.py 34, router.py 17 → below look
DEV-FAIL-FAST: grep -nE 'except' apps/shipments/service.py → 1 hit (KeyError re-raised as InvalidTransition) → clean
DEV-ERRORS: 4 return paths checked → clean
DEV-COMPOSITION: grep -nE 'class .*\(' apps/shipments/service.py → 1 hit (Exception subclass, is-a) → clean

🤖 reviewer (shipments): handoff → dev
Verdict: BLOCK. [MEDIUM] [DEV-COMMENTS] service.py:16-22 docstring; [MEDIUM] [DEV-COMMENTS] service.py:10,25 dividers; [MEDIUM] [DEV-COMMENTS] service.py:31 ticket ID; [MEDIUM] [DEV-FN-SHAPE] service.py:13 bool flag; [MEDIUM] [DEV-FN-SHAPE] service.py:44 7 params.

🤖 dev (shipments): first attempt pushed on ai/PROJ-301 — list, advance, ship implemented; Tests: 4 passed.
</dma-issue-read>
