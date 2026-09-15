# Status and label invariants

Tracker tasks carry two orthogonal markers; mix them up and the system rots.

- **Status** = board column = queue position. Semantic keys are universal across projects (`to_do`, `in_progress`, `qa`, `code_review`, `on_hold`, `awaiting_merge`, `awaiting_ops`, `sentinel_inbox`, `done`) and map to project-specific tracker names via `config.yml.tasks.workflow.statuses`. Shared-plugin prompts reference status by semantic key only; the tracker display name is resolved at runtime.
- **`agent:<role>` label** = which **agent** currently owns the task. Legal values for `<role>` are exactly the tracked-queue rows of `agent-roles.md`: `dev`, `qa`, `reviewer`, `devops`, `team-lead`, `sentinel`. No `agent:architect` or `agent:analyst` label exists. No other value is legal on the `agent:` prefix.

Reject any proposal that:
- Coins an `agent:<X>` label where `X` is not an agent in the taxonomy. The human user is not an agent — never `agent:user`. CI / bots / external actors get their own label namespace.
- Adds a label to disambiguate two queues that already have distinct status columns. Status alone is the routing signal; duplicating it as a label is dead weight.
- Adds an `agent:<role>` label to a status that has no agent owner. `awaiting_merge` (human is merging the PR), `awaiting_ops` (human is executing a devops runbook), and `done` (terminal) carry no `agent:<role>` — `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff` removes the previous `agent:<from>` and adds nothing.
- Hardcodes a tracker-specific status display name in a shared-plugin file. Status references use the semantic key; the display name comes from `config.yml.tasks.workflow.statuses` at runtime.

Process labels remain legal alongside status: `area:<area>` (permanent area ownership), `needs-decision` (team-lead `on_hold` filter), `stale-merge` (set by `dma board reconcile`). The invariant is only about the `agent:` prefix.
