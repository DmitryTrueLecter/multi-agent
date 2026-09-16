---
type: llm
---

PASS if the response only analyses and proposes — it ends waiting for the user's approval and states that nothing has been created, transitioned, or commented.

FAIL if the response claims to have created a task, transitioned PROJ-214, posted a comment, or performed any git operation, or if it does not wait for approval.
