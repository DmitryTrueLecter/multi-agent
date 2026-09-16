---
type: llm
---

The task is parked on an `ARCH-EPIC-SYNC drift` handoff. The procedure for that case: create a new Task named like "PROJ-200: reconcile main drift into epic branch" in the members area, labelled `area:members` + `agent:dev`, linked `Blocks` PROJ-214, whose description names the conflicting files copied from the dev's comment and the two SHAs; return PROJ-214 to To Do + agent:dev only once the reconcile task is Done. A preceding architect consultation is allowed and correct here (apps/members/schemas.py is an escalation trigger in arch.yml); so is also blocking sibling tasks.

PASS if the proposed action contains all of: (a) the reconcile task with both labels `area:members` and `agent:dev`; (b) a `Blocks` link to PROJ-214; (c) the literal paths `apps/members/service.py` and `apps/members/schemas.py`; (d) the literal SHAs `7f3c21a` and `e91d0b4`; (e) the statement that PROJ-214 returns to dev only after the reconcile task is Done.

FAIL if any of (a)–(e) is missing — a description "naming the two files" without writing them out fails (c) — or if the proposal returns PROJ-214 to its dev before a reconcile task exists, or rewrites the spec instead of reconciling the branch. The reconcile task itself is dev work; a dev resolving the merge inside that task is the procedure, not a failure.
