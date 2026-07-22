# Task schema

How work is represented in the task manager: what blocks a task's **description** carries, what **comments** agents post on it, and which role reads or writes each block at which stage. Agents never talk to each other directly — every exchange is an issue field or a comment in the tracker. Read at triage start alongside `patterns/`; use it to place any flag about a description section, a comment block, or a who-reads-what question without re-deriving the map from the role files each time.

## Principle

- Each block's schema is **single-source and closed** at its owner. A role never invents an ad-hoc section in a block it does not own — the IDAI-42 `Verify:` improvisation is the failure mode this prevents.
- Readers **reference** the owner's schema; they never re-describe it — divergent copies rot.
- Every block a role writes has a **named reader** at a **named stage**, or it is dead weight. A reader that works by grepping for a word rather than a declared contract is fragile.

## Description blocks (issue body)

The description owner is whoever creates the issue — always team-lead.

| Issue type | Description schema | Owner |
|---|---|---|
| Dev / qa Task | `## Purpose` / `## Requirements` / `## Test contract` / `## References` — closed; no command directives in the body | `team-lead/decompose.md → ### Issue description format` (closed-schema `**Rule:**`) |
| `## Test contract` content | Invariants / Scenarios / Boundaries, each with level (`unit`/`integration`/`e2e`); copied verbatim from architect | authored `architect.md → ## Output format`; copied `decompose.md → ### Issue description format` |
| Epic | canonical spec (free-form), lives only in the tracker | `decompose.md → ## Workflow` (Spec storage) |
| Coordination Task (`agent:team-lead`, `to_do`) | originating sentinel finding + proposed steps + archived-flag ref | `team-lead/coordination.md → ## Handling coordination tasks` |
| Sentinel Task (`agent:sentinel`) | `## Context` / `## Desired effect` / `## References` | `team-lead.md → ## Consulting sentinel → Task` |

## Comment blocks

Every comment starts `🤖 <role> (<area>):` (sentinel and team-lead carry no area). Two kinds: **handoff comments** (posted by `/dma:handoff`, which sets the prefix and the `handoff → <to>` line) and **progress / report comments** (posted by `/dma:issue-comment`).

| Comment | Writer @ stage | Body schema | Owner |
|---|---|---|---|
| dev progress | dev @ pre-handoff | what changed, files, requirements met, branch name | `dev.md → ## Task workflow` step 6 |
| dev → qa handoff | dev @ done | handoff line only; the work summary is the progress comment | `dev.md → ## Task workflow` step 8 |
| dev → team-lead escalation | dev @ blocked | epic-branch-missing / ARCH-EPIC-SYNC drift / gap-decision (fixed bodies) | `dev.md → ## Task workflow` steps 2a / 2c / 7 |
| QA report | qa @ handoff | Coverage matrix / Findings / Runtime-checks-deferred | `qa.md → ## Task workflow` step 4 |
| reviewer summary | reviewer @ handoff | Coverage matrix / Findings / Summary+Verdict | `reviewer.md → ## Output format` |
| reviewer → awaiting_merge | reviewer @ approve | PR URL / review summary / `Local checkout` / `Approved tip: <sha>` | `reviewer.md → ## Task workflow` step 7c |
| devops runbook | devops @ handoff | Pre-checks / Steps / Verification / Rollback | `devops.md → ## Mode A — assigned task` step 8 |
| team-lead closing | team-lead @ done | what landed + PR URL(s) | `team-lead/coordination.md`; `epic-closeout.md → ## Closing Epics` step 7 |

**Bounce-target scan.** On re-run, dev/devops read comments newest-first and stop at the first matching prefix — that is the current target:
- dev (`dev.md → ## Task workflow` step 1): `🤖 user (decline) via PR <URL>:` → `🤖 reviewer (<area>): handoff → dev` → `🤖 qa (<area>): handoff → dev`.
- devops (`devops.md → ## Mode A — assigned task` step 1): `🤖 user (decline) via PR <URL>:` → `🤖 user (runbook failed):` → `🤖 team-lead:`.

## Read / write flow by stage

| Stage | Reads | Writes |
|---|---|---|
| decompose (team-lead) | spec, `area.yml` | Epic + Task descriptions |
| architect consult | issue / spec, source | Recommendation + Test contract (team-lead lands it in the description) |
| claim (dev / devops) | description + bounce-target comment | — |
| dev work → handoff | description, `area.yml` `test_command` | commit, progress comment; → qa (or escalate → team-lead) |
| qa | description (`## Requirements`, `## Test contract`), test files | QA report; → reviewer / dev / team-lead |
| reviewer | issue for context, diff, `git log` | review summary, PR; → awaiting_merge / dev / team-lead |
| pr-feedback | reviewer `Approved tip:` + PR state | status transition |
| epic close-out (team-lead) | Epic description + comments (greps `deferred` / `follow-up` / `out of scope`), re-runs `area.yml` build/test | closing comment, PR |

## Triage rule

When a flag cites a description section, a comment block, or a who-writes / who-reads question: consult this file before opening the role files. If it disagrees with the current files, that drift is itself a finding — reconcile this file in the same triage pass (same discipline as `area-config-schema.md`).