# NONIDEMPOTENT-CREATE-ON-STALE-CONFIRM

## Signature

A skill creates a tracker issue and then confirms it reached a target status by re-reading it. The confirmation instruction is phrased as an outcome the caller must reach ("complete only once the flag is confirmed in the queue") rather than as "re-read the key you already created." When the read-after-write lags — the transition succeeded but the immediate re-read still shows the pre-transition status — the caller interprets slow confirmation as failure and re-invokes the whole skill. The second invocation runs the create step again, producing a duplicate issue. By the time the caller looks, the first issue has propagated to the target queue, so the caller stops and abandons the second run, leaving a stray in the workflow's default status (`to_do`). The root cause is prompt phrasing that conflates "verify" with "re-run," not caller carelessness: create and transition were never bound as one resumable unit.

## Observed instances

- **sentinel-flag double-file (2026-07-14, AITSAI-561, originating AITSAI-558).** 3 twin pairs in one cycle (538/539 dev, 543/544 architect, 557/558 devops); each earlier issue landed in Sentinel, each later retry (~4–10 s later) stalled in To Do and was closed as a duplicate. Fix: reworded `skills/sentinel-flag/SKILL.md` frontmatter ("invoke once per defect — creation and the Sentinel-queue transition are one unit the skill completes internally") and step 7 (verify by re-reading the returned key, never by re-invoking; a `to_do` status seconds after a successful transition is read-after-write lag; once create returns a key the invocation carries it to completion and never creates again). Rejected the flag's second hypothesis — mapping `agent:sentinel → sentinel_inbox` in `issue-create` — because `sentinel-flag` bypasses `issue-create`, and `agent:sentinel` also marks task-mode Tasks that correctly default to `to_do`.

## Triage rule

When the same issue double-files on retry and one copy strands in the default status: check whether the creating skill's confirmation step is phrased as an outcome the caller must reach ("complete only once confirmed") rather than "re-read the key you already created." If so, that phrasing is the cause — the caller re-invokes and re-creates on a stale read. Recommend: (a) bind create + status-transition as one resumable unit owned by a single invocation, (b) state that a stale read seconds after a successful transition is read-after-write lag, cured by re-reading the same key, not by re-invoking, and (c) forbid a second create once a key has been returned. A pre-create dedupe search of the target queue (match on type + where + originating) is the defense-in-depth complement, but it needs a search tool in the skill's grant — recommend it only when prompt phrasing alone is judged insufficient.

## Untriggered candidates

Other shapes likely to fit this pattern when they surface:

- Any create-then-transition skill (`issue-create`, `handoff`) where a caller re-invokes after a slow status read instead of re-reading the returned key.
- A PR-open or comment-post step re-run on a stale API read, producing a duplicate PR/comment.
- Batch creators that re-run the whole batch on partial confirmation instead of resuming only the unconfirmed items.
