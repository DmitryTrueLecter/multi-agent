# Agent roles

| Agent | Purpose | Writes code | Scope |
|-------|---------|-------------|-------|
| `analyst` | Describes features from the customer's side; owns the product description in `.claude/dma/product/**`. Spawned by team-lead in a relay loop with the user, or run as its own session; knows nothing of the code. | no | product |
| `team-lead` | Orchestrator; only agent that may consult sentinel sync. | no | project |
| `architect` | Cross-area technical authority. | no | project |
| `dev` | Implementation. | yes (area paths) | area |
| `qa` | Test adequacy review. | no | area |
| `reviewer` | Diff review per `DEV-*`/`<AREA>-*` rules. | no | area |
| `devops` | Environment/infra authority. Edits local infra files; server-side steps go to tracker comments. | yes (infra paths only) | project |
| `sentinel` | Meta-agent for prompt and process quality. | no | meta (agent system) |

Tracked-queue roles — the only legal values of the `agent:<role>` label — are `dev`, `qa`, `reviewer`, `devops`, `team-lead`, `sentinel`. `architect` is consulted via `Agent` spawn and `analyst` works upstream of the tracker in its own session; neither owns a tracked task.
