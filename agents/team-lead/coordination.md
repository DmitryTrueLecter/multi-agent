Procedure for coordination tasks (`to_do` + `agent:team-lead`). Spawned with `Coordination task: <KEY>`. Read this after the spine in `agents/team-lead.md` — it inherits every rule there.

## Handling coordination tasks (`to_do` + `agent:team-lead`)

Coordination tasks land in `to_do` with `agent:team-lead` when sentinel routes a triage finding that needs another role's action, or when team-lead itself queues a scaffolding step (introducing or dismantling an area, project init). Short lifecycle: no dev/qa/reviewer cycle — claim, execute the coordination action, close.

Pickup query:

```
/dma:issue-search status:<statuses.to_do> label:agent:team-lead
```

For each coordination task:

1. **Claim the task**: `/dma:issue-claim <KEY>`. When launched as a subagent via `/dma:run`, the claim is already done; use `/dma:task-read <KEY>` for the data.
2. Read the description. It carries the originating sentinel finding (or scaffolding spec), the proposed steps, and a reference to any archived flag.
3. Execute the proposed steps. Two typical shapes:
   - **Architect consultation → `Mode: structure` apply** — spawn architect with the framing from the description, present the recommendation to the user for approval, then route the resulting content to sentinel via `Mode: structure` (one `Op:` per affected file, batched).
   - **Area scaffolding** — route the new `area.yml` / role-overlay content directly to sentinel `Mode: structure` (`Op: create`).
4. **Close the task** with `/dma:handoff <KEY> done <closing-comment>`. The comment starts with `🤖 team-lead:`, names what landed (architect ID, structure-mode applies, follow-up tasks if any), and references the originating flag filename.
