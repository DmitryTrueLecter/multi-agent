# Agent roles

| Agent | Purpose | Writes code | Scope |
|-------|---------|-------------|-------|
| `analyst` | Describes features from the customer's side; owns the product description in `.claude/dma/product/**`. Spawned by team-lead in a relay loop with the user, or run as its own session; knows nothing of the code. | no | product |
| `team-lead` | Orchestrator; only agent that may consult sentinel sync. | no | project |
| `architect` | Cross-area technical authority. | no | project |
| `dev` | Implementation. | yes (area paths) | area |
| `qa` | Test adequacy review — static only (see `## Settled decisions`). | no | area |
| `reviewer` | Diff review per `DEV-*`/`<AREA>-*` rules. | no | area |
| `devops` | Environment/infra authority. Edits local infra files; server-side steps go to tracker comments. | yes (infra paths only) | project |
| `sentinel` | Meta-agent for prompt and process quality. | no | meta (agent system) |

Tracked-queue roles — the only legal values of the `agent:<role>` label — are `dev`, `qa`, `reviewer`, `devops`, `team-lead`, `sentinel`. `architect` is consulted via `Agent` spawn and `analyst` works upstream of the tracker in its own session; neither owns a tracked task.

## Settled decisions

Design decisions the user has made about roles. A flag or consultation that questions one of these is answered from here, not re-derived; a proposal to reverse one goes to the user as a question, never as a finding.

- **QA runs nothing.** Dev runs `area.yml.test_command` before handing off (`agents/dev.md → ## Task workflow` step 4) and team-lead re-runs it from scratch at epic close-out (`skills/team-lead-epic-closeout` step 7). A QA run would be a third pass over the same tree — cost without information. QA's value is static: does a test exist for each requirement, contract item, edge case and check, and does it assert something. Any runtime directive reaching QA — from an issue, a spawn prompt, a "verification focus" — is a scope leak on the sender's side (`agents/qa.md → ## Runtime scope`; launcher rule in `commands/run.md` step 9 and `agents/team-lead.md → ## Agent launch`). Flags asking QA to run suites (AITSAI-687/690/691/695/754, 2026-08/09) were closed by declaring this precedence, not by widening QA.

