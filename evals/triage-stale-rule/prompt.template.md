---
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: |
__CHARTER:sentinel__
---

Project root: the current working directory (run `pwd` once and use that absolute path wherever the charter says `<project-root>`). Mode: triage.

The tracker CLI is unavailable in this environment. Treat the two blocks below as the output of `dma board list --status Sentinel --label sentinel-flag` and of `dma issue read NOTIFY-91`; do not call the CLI. Stop after printing the report — the user has not answered yet, so apply, route, or resolve nothing.

<board-list>
NOTIFY-91	Sentinel	agent:sentinel,flag-type:rule-contradiction,sentinel-flag	parent=-	[RULE-CONTRADICTION] NOTIFY-TEMPLATE-WARM requires TemplateCache.warm() which NOTIFY-77 removed
</board-list>

<issue-read>
key: NOTIFY-91
title: [RULE-CONTRADICTION] NOTIFY-TEMPLATE-WARM requires TemplateCache.warm() which NOTIFY-77 removed
status: Sentinel
labels: agent:sentinel, flag-type:rule-contradiction, sentinel-flag
parent: null
blocked by: -

## description
*Where:* areas/notify/area.yml : review_checks NOTIFY-TEMPLATE-WARM + paired guideline

*Reporter:* reviewer

*Originating:* NOTIFY-77

*Problem:* NOTIFY-77 replaced the import-time `TemplateCache.warm()` with lazy per-template loading in `libs/notify/render.py` (`_load` under `lru_cache`). `TemplateCache` no longer exists anywhere; the rule's first ENFORCEMENT grep (`grep -rnL 'TemplateCache.warm'`) now lists every renderer module as a violation, so reviewer blocks every notify PR.

*Details:* Suggested fix: delete NOTIFY-TEMPLATE-WARM and its guideline.

## comments (0, newest first)
</issue-read>
