---
name: team-lead-current-state
description: "Team-lead current-state procedure: describe what a user meets today in one part of the product, from the code, in the user's terms — for the analyst's `CONSULT:` line or its `Current state:` spawn. Invoked by the team-lead agent."
user-invocable: false
---

# Team-lead: current state

Answer what the product does today in one part, as a user meets it. Two callers, one procedure: the analyst's `CONSULT:` line in the relayed loop (`agents/team-lead.md → ## Consulting the analyst`) and the `Current state: <part>. Question: <what to establish>` spawn from the analyst's own session. Every rule of `agents/team-lead.md` applies here.

## Answering a current-state question

The reader of your answer is the user: the analyst folds it into the draft's `## Current state` marked "according to engineering" and shows it back to them. Write what a user meets in `<part>` today.

1. Locate the part: match `<part>` to the areas from Bootstrap step 2 and read the code that carries its behaviour — routes, screens, handlers, validations, and the tests that pin behaviour. Spawn no dev, run nothing.
2. Describe what a user meets there: screens and their elements, actions available, rules enforced, outcomes, error messages as displayed. Stay at the level a user sees. Detection before returning: the words `code`, `file`, `function`, `route`, `module`, `template`, `test`, a path, or a symbol in backticks — any hit outside the literal marker `not settled by the code` is a mechanics leak; rewrite that sentence as what the user sees, or drop it. Proposals for the feature being designed stay out too.
3. Mark every point the code leaves open as `not settled by the code: <what is open>` instead of filling it in.
4. Return the description alone, in English. Your return begins with the description's first sentence and ends with its last — no line about bootstrap, about what you read, or about the areas you found; no return markers, no tracker action, no question to the user. The analyst pastes this text to the user word for word. In the relayed loop this text is the `Engineering answer:`; from the analyst's own session it is the spawn's return.

<example>
Question: what an operator meets on the export list today, and what happens when an export fails.

The export list shows every export the operator created, newest first, with its name, the filter set it was built from, when it was requested, and a status of Queued, Running, Done, or Failed. A Done row offers "Download"; a Failed row shows the failure reason in red under the status and offers no action — the operator creates a new export to try again. Exports older than 30 days are absent from the list. Not settled by the code: whether an operator can see exports created by other operators — the list is filtered by the signed-in account, and no role-based view exists.
</example>
