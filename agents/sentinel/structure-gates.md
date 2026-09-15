# Structure gates

The four gates every create / modify / delete on a project-local area or arch file passes before it is written. Applied in order; the first failing gate ends the check. Used by `dma:sentinel-structure` (team-lead intake) and `dma:sentinel-task` (self-check before each write).

## Gate 1: Scope

Target is one of:
- `${CLAUDE_PROJECT_DIR}/.claude/dma/arch.yml` — any op.
- `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/area.yml` — any op.
- `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/<role>.yml` — any op.
- `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/<area>/` directory — `create` (via writing the first file) or `delete` (full removal).

Out of scope, reject with `Criterion: scope`:
- `agents/*.md`, `skills/**`, `commands/**`, `hooks/**`, `agents/sentinel/**` — shared-plugin; the path is a flag → triage.
- `config.yml`, `settings*.json` — dedicated bootstrap skills.
- `${CLAUDE_PROJECT_DIR}/.claude/dma/product/**` — the analyst's product description, written only by the analyst.
- Anything outside `.claude/`.

## Gate 2: Schema

Validate against `${CLAUDE_PLUGIN_ROOT}/agents/sentinel/area-config-schema.md`:
- Required fields present.
- Rule IDs unique within the file.
- `arch.yml` matches its documented shape.
- Field content follows the schema's per-field prescriptions (e.g. `## What belongs in qa.yml.checks`). A `qa.yml.checks` entry those would assign to a pytest in the code rejects with `Class: PROMPT-SCOPE-LEAK`.

An edit adding an undocumented schema field is out of scope — return that path explicitly; schema extension is `area-config-schema.md → ## Adding a new field`.

## Gate 3: Quality

Apply the findings taxonomy against the post-apply state. Reject if the change would introduce any of:
- **`PROMPT-UNCLEAR`** — wording vague enough that dev/qa/reviewer cannot act without guessing. Quantify thresholds, name patterns explicitly, glob the scope.
- **`PROMPT-INCOMPLETE`** — workflow omits a real adjacent case; new `review_checks` rule without an enforcement clause where mechanical detection applies; deletion of a rule still cited elsewhere.
- **`PROMPT-CONTRADICTION`** — proposed rule cannot coexist with an existing `ARCH-*`, `<AREA>-*`, or `DEV-*` rule already in the corpus.
- **`PROMPT-FRAGMENTED`** — modification appends a clause to a rule that needs to be rewritten as one paragraph. Light fragmentation resolves under polish; substantive fragmentation (contradicting voices, dual procedures in one rule) rejects.
- **`PROMPT-SCOPE-LEAK`** — area content instructs an agent into another area's territory; `<role>.yml` overlay reaches outside the area's `paths`.
- **`RULE-CONTRADICTION` / `RULE-ORPHANED` / `RULE-GHOST`** — new rule without paired enforcement; rule deletion that orphans a detection in `reviewer.md`; clause citing a rule ID absent from its source-of-truth.
- **`ARCH-ROLE-GAP` / `ARCH-ROLE-OVERLAP`** — content assigns a responsibility to no one or to two roles ambiguously.

## Gate 4: Consistency

- No rule-ID collision across paired files (e.g. `<AREA>-NNN` in `area.yml` colliding with an existing detection in `reviewer.md`).
- No dangling cross-references — a new `arch.yml` entry naming a non-existent area; deleting an area with live `area:<name>` labels in the tracker.

## Rejection block

Returned on the first failing gate; nothing is written, never a partial apply.

```markdown
## Rejection
Criterion: scope / schema / quality / consistency
Class: <taxonomy ID — only for quality>
Failing: <one sentence — what specifically failed>
To pass: <concrete revision the caller can make>
```
