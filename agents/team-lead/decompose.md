Procedure for decomposing a spec into an Epic and area-scoped Tasks. Reached from the interactive main session once the user authorizes turning a spec into tasks (`agents/team-lead.md → ## Default flow`). Read this after the spine in `agents/team-lead.md` — it inherits every rule there.

## Task management

Read task provider settings from `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` → `tasks`.

### Creating issues

```
${CLAUDE_PLUGIN_ROOT}/bin/dma issue create <task|group> "<summary>" \
    --labels <area-label>,<agent-label> [--parent <EPIC-KEY>] [--blocks <KEY1>,<KEY2>] \
    --description - <<'DESC'
<Markdown with Purpose, Requirements, References sections>
DESC
```

- `<summary>`: specific task name
- `--labels`: e.g. `area:ai,agent:dev` — both are required on every task, see below
- `--parent`: (task only) the group this task belongs to
- `--blocks`: (optional) issues this one blocks
- `--description -`: the body on stdin, so Markdown with tables and pipes survives
- `--state <key>`: (optional) overrides where the issue starts; by default the
  `agent:<role>` label decides (`agent:qa` → the qa queue) and anything else starts in `to_do`

**Both labels are REQUIRED on every Task issue. Never skip any.**
- `area:<area>` — permanent area label, never changes (e.g. `area:ai`, `area:core`, `area:api`)
- `agent:<role>` — current assignee, changes on handoff (e.g. `agent:dev` → `agent:qa` → `agent:reviewer`)

### Issue description format

```markdown
## Purpose
Why this task exists. What feature or behavior it enables.

## Requirements
Concrete list of what must be built.

## Test contract
Architectural tests that must accompany the implementation — invariants, end-to-end scenarios, and integration boundaries with the level (`unit` / `integration` / `e2e`) for each. **Copied verbatim from the architect's `## Test contract` section** when an architect consultation produced one. If the architect declared `No architectural tests required — unit coverage sufficient.`, copy that line in. Omit this section entirely only when the task did not require architect consultation at all (purely local change).

## References
Links to spec sections, existing code to follow.
```

**Rule:** if you spawned an architect for this task, the `## Test contract` section is mandatory in the issue description and must match what the architect produced. Dropping it silently disconnects the architectural intent from what dev/qa verify — that is the gap this section exists to close.

**Rule:** Audit the Requirements text against `DEV-*` rules before publishing. The architect's Recommendation specifies field sets and semantics (per `agents/architect.md → ## Output format`); the issue Requirements describe the same. When the architect's output contains a literal call-site signature that violates DEV-FN-SHAPE (domain inputs >4 without value-type grouping, boolean flag arguments) or another `DEV-*` rule, rewrite it before publishing — name the field set and let dev pick the rule-compliant call shape.

**Rule:** Any fixture, sample input, or captured payload a Task's `## References` or `## Test contract` depends on must be committed — to the repo, or to the Epic branch for Epic-scoped work — before you queue the Task. A machine-local or gitignored path is unreachable from the agent's worktree, so a test built from it is impossible or fabricated; commit the source (trimmed to what the contract needs) and reference the committed path.

**Rule:** Author every file path in the description repo-relative — the path as it reads from the repo root — never absolute (no leading `${CLAUDE_PROJECT_DIR}`, no machine path). Dev/qa/reviewer consume the description under a worktree checkout, not the repo root; an absolute path resolves to the wrong tree.

**Rule:** Register any runtime or format gate that matters at final verification — a test run, a build, a format or lint check, a mechanical grep invariant — with its owner; never inline it as a `Verify:` / `Run:` command directive in the Task body. The owners are `area.yml` `test_command` / `build_command` (re-run at epic close-out per `agents/team-lead/epic-closeout.md`), `area.yml` `review_checks` (enforced by reviewer), and CI. Before writing such a directive, check whether one of these owners already holds the gate: if so, drop it as a duplicate; if the gate is genuinely needed and unowned, register it with the owner — route the `area.yml` / `review_checks` change through sentinel per `## Rule lifecycle` — not into the description. Keep the description to what to build (`## Requirements`) and what must be tested (`## Test contract`); it never carries commands a role must execute, and QA is static-only and cannot run them.

### Dependencies

Pass `blocks:<KEY1>,<KEY2>` to `${CLAUDE_PLUGIN_ROOT}/bin/dma issue create` when creating issues — the skill creates the `Blocks` dependency links in one call.

### Linking to epic

Pass `--parent <EPIC-KEY>` when creating Tasks — the command links the Task to the group.

## How to decompose

### Principles

1. **One task = one complete deliverable.** If two things are meaningless without each other, they are one task.
2. **Task names must be specific.** Anyone reading the board should understand what the task produces without opening it.
3. **Each task has a purpose.** Write WHY this task exists. Without this, QA cannot verify correctness.
4. **Requirements in the task, not in the role.** The issue description contains what to build and why. The role contains how to work.
5. **NO separate QA tasks.** QA reviews the SAME task. When dev finishes, the label changes from `<area>/dev` to `<area>/qa`. One task, one issue.
6. **Don't over-split.** If two things are always done together, they are one task.
7. **Don't under-split.** If a task spans multiple areas, split by area. Infrastructure work (Docker, CI/CD, deploy, log shipping) is its own scope: label `area:devops` + `agent:devops`, not an application area. Mixed app + infra goes into separate tasks linked via `blocks:`.
8. **Inventory cross-area symbol references.** For each draft Task scoped to area `<X>`, scan its Requirements for references to code in any other area — paths matching another area's `paths:` glob (from `areas/<other>/area.yml`) **and the named function / class / module being imported or called**. For each (path, symbol) pair:
   - Grep `<path>` for the symbol's definition. A `NotImplementedError` / stub / placeholder body counts as missing — open the match and confirm a real implementation.
   - Symbol present with a real implementation → no action.
   - Symbol missing or stub → it must be the deliverable of an earlier child Task in the same Epic whose Requirements name **that symbol**, not just the file. If no such Task exists, create the owner Task first and link the consuming Task with `blocks:<owner-KEY>`.

   A Task that owns a path without naming each downstream-required symbol does **not** satisfy this check — the recurring failure mode is a core file shipping as a `NotImplementedError` stub while a downstream-area Task imports a function from it. Without the symbol-level check the same bounce fires per downstream consumer: dev claims → blocks → team-lead handoff → architect consult → new sub-task → re-queue.
9. **Production access belongs to the user, never an agent.** No agent sandbox can reach production — no credentials, no network path, by design (mirrors devops's no-server-access rule). When a task's Requirements need a production result before the code can be written — an audit query, a row count, a live-state probe — do not route the whole task to dev. Split it: surface the production step to the user, who runs it; record the returned result as a Task comment. The code work becomes a separate dev Task linked `blocks:` the data step, held in `to_do` + `agent:dev` until the result is attached. A dev Task whose Requirements embed an unrun production query is unfollowable — the dev can only fabricate the answer or escalate.

## Workflow

**Spec storage.** The canonical spec lives in the Epic description in the issue tracker — never in the repo. The analyst's feature document under `${CLAUDE_PROJECT_DIR}/.claude/dma/product/drafts/` is a gitignored working file, not a tracked spec: it is the input you copy into the Epic, and the analyst's working copy while a requirements objection is open (`agents/team-lead.md → ## Requirements objection`). Any other input the user provides (chat paste, scratch file, link) is a draft the same way. Once you create the Epic, its description is authoritative for engineering; a change the analyst records in the document during an objection is mirrored into the Epic description by you, and clarifications or follow-ups that arise later land there or as Epic comments. Do **not** create, read, or reference epic markdown files under `docs/` or any tracked path.

1. Read the spec: the analyst's feature document when the user gives its path, otherwise the text the user provided. Read the relevant architecture docs.
2. Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` for conventions and `${CLAUDE_PROJECT_DIR}/.claude/dma/areas/` for area boundaries.
3. Create an Epic in the issue tracker with `${CLAUDE_PLUGIN_ROOT}/bin/dma issue create group "<summary>" --description -`. An analyst document goes in verbatim — its sections are the customer's words and the closed schema downstream roles read (`## Goal`, `## How it works`, `## Business rules`, `## Boundaries`, `## Acceptance criteria`, `## Decisions`). Raw user text you copy and expand yourself. Either way the Epic description becomes the canonical spec.
4. **Create the epic branch** `<vcs.branch_prefix><EPIC-KEY>` in each affected area's workspace, then **verify it landed on the remote before decomposing**. The verify step exists because the push can silently fail (auth, network, hook, protected-branch rule) and the failure surfaces only later as `🤖 dev (<area>): handoff → team-lead (epic branch missing on remote)` from every child task — a bounce per child Epic-wide. Catch it once, here.

   Resolve each affected area's workspace per the rule in the role docs (`area.yml.workspace` → `config.yml.workspace` → built-in defaults: `path=.`, `remote=origin`, `dev_branch=vcs.dev_branch`). Take the set of distinct `workspace.path` values. For each, use a **subshell** so cwd does not leak:

   - Per workspace:
     ```
     ${CLAUDE_PLUGIN_ROOT}/bin/dma branch create-epic <EPIC-KEY> --area <area>
     ```
     `CREATED` — the branch was cut from `<workspace.dev_branch>` and is on the remote (the command verifies it landed). `EXISTS` — it was already there and was left untouched, which is what makes the recovery below safe to re-run. Exit `12` `PUSH_NOT_LANDED` or exit `1` — stop the decomposition, post the output with `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <EPIC-KEY> <output>`, and do not create child tasks: they would all fail on a missing epic branch.

   The branch name is derived from the Jira Epic KEY (e.g. `ai/AITSAI-50`) — same across all affected workspaces so any task references it unambiguously via its own `parent` field. Record the affected workspaces in the Epic description (the branch name itself is implicit from the KEY).

   **Recovery — Epic already decomposed without an epic branch.** Symptom: dev hands off a child with `🤖 dev (<area>): handoff → team-lead` citing "Epic branch missing on remote" (per `agents/dev.md` → `## Task workflow` step 2a). The Epic has live children but the branch this step was supposed to create never landed. Do this and only this — do **not** retroactively rebase already-merged children:

   1. Identify every affected `workspace.path` from the Epic's child Task labels (same resolution rule as the create step above).
   2. For each workspace, run the same `branch create-epic` call as in step 4 — an epic branch that already exists is reported as `EXISTS` and left untouched, so the recovery is safe to re-run.
   3. If any child Task was already merged to `<workspace.dev_branch>` while no epic branch existed (i.e. dev silently fell back to dev-branch base — the pre-2026-05 prompt allowed this), post `${CLAUDE_PLUGIN_ROOT}/bin/dma issue comment <EPIC-KEY> "🤖 team-lead: epic branch <vcs.branch_prefix><EPIC-KEY> created retroactively after N child(ren) already merged to <dev_branch>. ARCH-EPIC-SYNC contract was not enforced for those children — the close-out integration-drift check in `agents/team-lead/epic-closeout.md → ## Closing Epics` step 7 will catch any resulting drift."`. List the merged child keys in the comment.
   4. Return each on-hold child citing the missing epic branch to `To Do` + `agent:dev` via `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <CHILD-KEY> dev "Epic branch <vcs.branch_prefix><EPIC-KEY> now present on <workspace.remote>. Re-run task workflow step 2."`.

   The retroactive comment is the audit trail — close-out (`agents/team-lead/epic-closeout.md → ## Closing Epics` step 7) is where the drift, if any, is actually mechanically caught and resolved.
5. **Verify the base is green per affected workspace, before decomposing.** Test rot on the base masquerades as task failures once decomposition lands — every child task that touches a rotted file pays the cost (dev hits red tests, escalates via `dev.md` step 4, triage task is filed, original task re-queues). Catch the rot once, here. For each `workspace.path` from step 4, in a subshell:

   ```
   ( cd <workspace.path> && \
     git checkout <workspace.dev_branch> && \
     <test_command from areas/<area>/area.yml> )
   ```

   - **All green** → proceed to step 6.
   - **Failures exist** → classify each failing test (or group sharing a failure mode) into **fix** / **delete** / **temporarily disable** per the criteria in `agents/team-lead/on-hold.md → ## Handling On Hold tasks` step 4 (the test-rot bullet). File triage tasks against this Epic before any application Task — label `area:<area> agent:dev`, link each as `Blocks` for any application Task whose Requirements touch the rotted file's symbols. Triage tasks land first; application Tasks land after. Do not decompose application work over rotted tests.
6. **Consult the architect where `## Always delegate to architect` requires it, and pass the document's requirements as `Constraints:`.** Read the verdicts before drafting Tasks. A *holds, with cost* or *does not hold* verdict on a requirement from the analyst's document, or a blocking question only the customer can answer, is a requirements objection — follow `agents/team-lead.md → ## Requirements objection`: write the review block, draft no Task that depends on the contested requirement, continue with the rest, and tell the user the decomposition is partial until the analyst resolves it. `## Test contract` sections come from the same consultations and go into the affected Tasks in step 7.
7. Create Task issues with `${CLAUDE_PLUGIN_ROOT}/bin/dma issue create task "<summary>" --parent <EPIC-KEY> --labels area:<area>,agent:dev --description -`. The `parent:<EPIC-KEY>` argument is what dev/qa/reviewer use to derive the epic branch. Each Task is scoped to **one area** (and therefore one workspace). Pass `blocks:<KEY>` for any dependency links. Every Task's `## Requirements` traces to a sentence in the Epic description; a requirement that appears in no Task is an omission to fix, and a Task requirement that appears nowhere in the Epic is an invention to remove.
8. Present the decomposition to user for approval.
9. User launches agents via `/dma:run`. You report progress. When a paused objection resolves, re-read the document, mirror any `Changed after engineering review` edits into the Epic description, and decompose the remaining requirements from step 6.
