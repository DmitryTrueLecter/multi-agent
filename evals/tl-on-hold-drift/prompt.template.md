---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: |
__CHARTER:team-lead__
---

Bash is unavailable in this environment: find the project root with `Glob` on `.claude/dma/config.yml` (the absolute path it returns gives the prefix) and use `Read` for every file. The tracker CLI is unavailable: treat the blocks below as the output of the `dma` commands named on each, and call nothing yourself. The task is already claimed. Stop after presenting your analysis — the user has not answered, so create, transition, and comment nothing.

On Hold task: PROJ-214.

<dma-issue-read key="PROJ-214">
key: PROJ-214
title: Members: expire pending invites after 7 days
status: On Hold
labels: agent:team-lead, area:members, needs-decision
parent: {key: PROJ-200, type: group}
blocked by: -

## description
## Purpose
Pending invites that are never accepted clutter the list forever; expire them so the list reflects the real team.

## Requirements
- An invite older than 7 days is refused on acceptance with a message that tells the person to ask for a new invite.
- The members list shows how many days ago a pending invite was sent.

## Test contract
- Invariant: acceptance on day 8 is refused, on day 7 accepted (level: unit).

## References
- Epic description → "Business rules" → invites.

## comments (2, newest first)
🤖 dev (members): handoff → team-lead (ARCH-EPIC-SYNC drift)
Forward-merge of main into ai/PROJ-200 conflicts in apps/members/service.py and apps/members/schemas.py. Epic tip 7f3c21a, main tip e91d0b4 (PROJ-231 merged to main 2026-09-14: renamed `Member.status` to `Member.state`, added `Member.invited_at`). I did not resolve — cross-team conflict per ARCH-EPIC-SYNC. Task branch not cut.

🤖 team-lead: task created from Epic PROJ-200 decomposition.
</dma-issue-read>

<dma-board-list parent="PROJ-200">
PROJ-212	Done	area:members	parent=PROJ-200	Members: invite by email with a role
PROJ-213	Awaiting Merge	area:members	parent=PROJ-200	Members: change a member's role from the list
PROJ-214	On Hold	agent:team-lead,area:members,needs-decision	parent=PROJ-200	Members: expire pending invites after 7 days
PROJ-215	To Do	agent:dev,area:members	parent=PROJ-200	Members: remove a member from the list
</dma-board-list>

<dma-issue-read key="PROJ-200">
key: PROJ-200
title: Team members management
status: In Progress
labels: area:members
## description
## Goal
Let an editor manage who is on the team without asking an administrator.
## Business rules
- Invites expire after 7 days.
- Only editors invite, change roles, or remove.
## comments (0)
</dma-issue-read>

<dma-issue-read key="PROJ-231">
key: PROJ-231
title: Members: track when an invite was sent (schema rename status→state)
status: Done
labels: area:members
parent: null
## description
Standalone fix merged to main on 2026-09-14: `Member.status` → `Member.state`, new `Member.invited_at` timestamp; routers and templates updated.
## comments (1)
🤖 reviewer (members): approved. PR #88 merged.
</dma-issue-read>
