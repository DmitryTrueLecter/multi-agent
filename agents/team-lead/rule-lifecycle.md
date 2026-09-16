# Rule lifecycle (DEV-* / ARCH-* / <AREA>-* rules)

The project has three rule namespaces, each with its own home and paired enforcement. A rule without enforcement is decoration; one half without the other is a violation — stop and route the missing half through sentinel.

| Namespace | Source of truth | Paired enforcement |
|-----------|-----------------|---------------------|
| `DEV-*`   | `agents/dev.md` → `## Code standards` | `agents/reviewer.md` → detection method per ID |
| `ARCH-*`  | `agents/architect.md` → `## Project-level invariants` (generic, cross-project); project-specific `ARCH-*` in `arch.yml` → `invariants` (project-local) | architect cites in recommendations; some are also reviewer-detectable (e.g. `ARCH-NO-LEAKY-MODELS`) — add detection to `reviewer.md` when applicable |
| `ARCH-EPIC-SYNC` (process-paired) | `agents/architect.md` → `## Process invariants` | dev claim step (`agents/dev.md` → `## Task workflow` step 2) + team-lead close-out drift check (`skills/team-lead-epic-closeout` step 7). No reviewer grep — process step rather than diff-detectable. |
| `<AREA>-*` | `areas/<area>/area.yml` → `review_checks` (keyed by rule ID) | architect writes when making area decisions; reviewer enforces via grep patterns in `review_checks` |

Every rule change has two halves; land the prompt half first, then dispatch the code half.

- **Prompt half** — under `.claude/**`; team-lead never edits it (`.claude/dma/product/**` is the analyst's, the rest is sentinel's; the one exception is `product/drafts/<feature>.review.md`, team-lead's channel to the analyst). Two channels by rule location:
  - `<AREA>-*` in `areas/<area>/area.yml` → a sentinel **task** (preferred when the change ships with an Epic): `${CLAUDE_PLUGIN_ROOT}/bin/dma issue create task "<summary>" --parent <EPIC-KEY> --labels area:<area>,agent:sentinel` — see `agents/team-lead.md → ## Consulting sentinel`; or a **consultation** (ad-hoc).
  - `DEV-*` in `agents/dev.md`, `ARCH-*` in `agents/architect.md`, or any other shared-plugin path → **consultation only** (task-mode is scope-locked to `areas/**`): `Agent(subagent_type="dma:sentinel", prompt="Project: ${CLAUDE_PROJECT_DIR}. Mode: consultation. Question: <add|remove|modify> rule <ID>: <what>. Context: <why>.")`. Sentinel returns the rewrite; the user commits it.
- **Code half** — the production code the rule governs. Goes into a dev-area task scoped to the area's `dev.yml` write paths. Never put `.claude/**` paths in a dev/qa/reviewer task description.
