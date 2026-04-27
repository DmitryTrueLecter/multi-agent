---
description: "Reject task result: /reject <ISSUE-KEY> <reason>. Reverts code, returns to To Do"
---

Reject a completed task and revert its changes.

**Setup:** Read `.claude/config.yml` to get `tasks.project_key`.

**Usage:** `/reject <ISSUE-KEY> <reason>`

Example: `/reject <ISSUE-KEY> implementation doesn't follow existing patterns from <similar-file>`

**Steps:**

1. Read the issue with `jira_get_issue` using the key from `$ARGUMENTS`.
2. Read the issue's comments to find which files were created/modified by the agent.
3. Revert those files:
   - Modified files: `git restore <file>`
   - Created files: `rm <file>`
4. Transition the issue back to `To Do` via `jira_transition_issue`.
5. Update the `agent:` label back to `agent:dev` via `jira_update_issue`.
6. Add a rejection comment via `jira_add_comment`:

```
**REJECTED**
Reason: <the user's reason>
Reverted files: <list>
```

7. Confirm to the user what was reverted.

The rejection comment stays in Jira permanently. Next time an agent picks up this task, it will see the rejection and know what to fix.
