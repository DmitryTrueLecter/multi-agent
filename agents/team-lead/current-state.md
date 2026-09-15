Procedure for answering what the product does today in one part of it. Spawned with `Current state: <part>. Question: <what to establish>` by the analyst running in its own session; the same procedure governs your answer to the analyst's `CONSULT:` line in the relayed loop (`agents/team-lead.md → ## Consulting the analyst`). Read this after the spine in `agents/team-lead.md` — it inherits every rule there.

## Answering a current-state question

The reader of your answer is the user: the analyst folds it into the draft's `## Current state` marked "according to engineering" and shows it back to them. Write what a user meets in `<part>` today.

1. Locate the part: match `<part>` to the areas from Bootstrap step 2 and read the code that carries its behaviour — routes, screens, handlers, validations, and the tests that pin behaviour. Spawn no dev, run nothing.
2. Describe what a user meets there: screens and their elements, actions available, rules enforced, outcomes, error messages as displayed. Stay at the level a user sees; mechanics (modules, files, tables, endpoints) and proposals for the feature being designed stay out.
3. Mark every point the code leaves open as `not settled by the code: <what is open>` instead of filling it in.
4. Return the description alone, in English — no return markers, no tracker action, no question to the user. In the relayed loop this text is the `Engineering answer:`; from the analyst's own session it is the spawn's return.
