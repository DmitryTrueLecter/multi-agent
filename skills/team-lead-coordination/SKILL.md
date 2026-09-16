---
name: team-lead-coordination
description: "Team-lead coordination-task procedure: claim a short-lifecycle task in to_do + agent:team-lead (sentinel-routed finding or area scaffolding), execute its steps through architect and sentinel structure mode, close it. Invoked by the team-lead agent on `Coordination task: <KEY>`."
user-invocable: false
---

# Team-lead: coordination task

Execute one coordination task — a sentinel-routed finding or a scaffolding step — with no dev/qa/reviewer cycle: claim, act, close. Spawned by `/dma:run` with `Coordination task: <KEY>`; every rule of `agents/team-lead.md` applies here.

## Handling coordination tasks (`to_do` + `agent:team-lead`)

Coordination tasks land in `to_do` with `agent:team-lead` when sentinel routes a triage finding that needs another role's action, or when team-lead itself queues a scaffolding step (introducing or dismantling an area, project init). Short lifecycle: no dev/qa/reviewer cycle — claim, execute the coordination action, close.

Pickup query:

```
${CLAUDE_PLUGIN_ROOT}/bin/dma board list --status <statuses.to_do> --label agent:team-lead
```

For each coordination task:

1. **Claim the task**: `${CLAUDE_PLUGIN_ROOT}/bin/dma issue claim <KEY>`. When launched as a subagent via `/dma:run`, the claim is already done; use `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>` for the data.
2. Read the description. It carries the originating sentinel finding (or scaffolding spec), the proposed steps, and a reference to any archived flag.
3. Execute the proposed steps. Two typical shapes:
   - **Architect consultation → `Mode: structure` apply** — spawn architect with the framing from the description, present the recommendation to the user for approval, then route the resulting content to sentinel via `Mode: structure` (one `Op:` per affected file, batched).
   - **Area scaffolding** — route the new `area.yml` / role-overlay content directly to sentinel `Mode: structure` (`Op: create`).
4. **Close the task** with `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> done <closing-comment>`. The comment starts with `🤖 team-lead:`, names what landed (architect ID, structure-mode applies, follow-up tasks if any), and references the originating flag filename.
