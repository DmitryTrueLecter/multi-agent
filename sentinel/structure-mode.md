# Structure mode — procedure

Sync intake from team-lead for create / modify / delete operations on area and arch files. Sentinel reasons about the proposed change against the prompt-quality taxonomy and either applies (with light polish) or rejects with a class and a path to revision.

## Invocation

```
Agent(subagent_type="sentinel", prompt="Project: <abs-project-root>. Mode: structure. Op: <create|modify|delete>. Target: <path>. Content: <text or '—' for delete>. Rationale: <one line>.")
```

## In scope

- `.claude/arch.yml` — any op.
- `.claude/areas/<area>/area.yml` — any op.
- `.claude/areas/<area>/<role>.yml` — any op.
- `.claude/areas/<area>/` directory — `create` (via writing the first file) or `delete` (full removal).

## Out of scope (reject with `Criterion: scope`)

- `agents/*.md`, `skills/**`, `commands/**`, `hooks/**`, `sentinel/**` — shared-plugin, flag → triage path.
- `config.yml`, `settings*.json` — dedicated bootstrap skills.
- Anything outside `.claude/`.

## Procedure

1. Resolve the operation:
   - `create` — target must not exist; content required.
   - `modify` — target must exist; content required.
   - `delete` — target must exist; content omitted.
2. Read the target (for modify/delete) or the parent area/arch context (for create) — enough to see the file's voice, the surrounding rule corpus, and what the new content interacts with.
3. Validate the four gates in order. Stop at the first failing gate.

### Gate 1: Scope

Target inside the in-scope list above. Operation allowed for that path.

### Gate 2: Schema

- `area.yml` validates against `sentinel/area-config-schema.md`.
- `arch.yml` matches its documented shape.
- Required fields present.
- Rule IDs unique within the file.

Edits adding undocumented schema fields are out of scope — return that path explicitly. Schema extension is documented in `area-config-schema.md → ## Adding a new field`.

### Gate 3: Quality

Apply the lens from `agents/sentinel.md → ## Findings taxonomy` against the post-apply state. Reject if the change would introduce any of:

- **`PROMPT-UNCLEAR`** — wording vague enough that dev/qa/reviewer cannot act without guessing. Quantify thresholds, name patterns explicitly, glob the scope.
- **`PROMPT-INCOMPLETE`** — workflow omits a real adjacent case; new `review_checks` rule without an enforcement clause where mechanical detection applies; deletion of a rule still cited elsewhere.
- **`PROMPT-CONTRADICTION`** — proposed rule cannot coexist with an existing `ARCH-*`, `<AREA>-*`, or `DEV-*` rule already in the corpus.
- **`PROMPT-FRAGMENTED`** — modification appends a clause to a rule that needs to be rewritten as one paragraph. Light fragmentation resolves under polish (see below); substantive fragmentation (contradicting voices, dual procedures in one rule) rejects.
- **`PROMPT-SCOPE-LEAK`** — area content instructs an agent into another area's territory; `<role>.yml` overlay reaches outside the area's `paths`.
- **`RULE-CONTRADICTION` / `RULE-ORPHANED` / `RULE-GHOST`** — new rule without paired enforcement; rule deletion that orphans a detection in `reviewer.md`; clause citing a rule ID absent from its source-of-truth.
- **`ARCH-ROLE-GAP` / `ARCH-ROLE-OVERLAP`** — content assigns a responsibility to no one or to two roles ambiguously.

### Gate 4: Consistency

- No rule-ID collision across paired files (e.g., `<AREA>-NNN` in `area.yml` colliding with an existing detection in `reviewer.md`).
- No dangling cross-references — new `arch.yml` entry naming a non-existent area, deleting an area with live `area:<name>` labels in the tracker.

## On pass

- `create` / `modify` — apply `agents/sentinel.md → ## Prompt rewrite style` to prose fields (`role:`, `guidelines:`, free-text `review_checks` strings); `Write` the file. Substance — rule semantics, thresholds, grep patterns, IDs — stays as submitted.
- `delete` — remove the file or directory.

## On fail

Return the rejection block; do not act. Never partial-apply.

```markdown
## Rejection
Criterion: scope / schema / quality / consistency
Class: <taxonomy ID — only for quality>
Failing: <one sentence — what specifically failed>
To pass: <concrete revision the caller can make>
```

## Not sentinel's domain

Subjective architectural taste — whether a pattern is wise, whether a stack choice is right, whether a rule's substance is the best engineering call. Those route to architect. A rule whose semantics sentinel disagrees with but that passes the taxonomy is applied.
