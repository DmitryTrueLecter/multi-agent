---
description: "Reject task result: /dma:reject <ISSUE-KEY> <reason>. Reverts code, returns to To Do"
---

Reject a completed task and revert its changes.

**Setup:** Read `${CLAUDE_PROJECT_DIR}/.claude/dma/config.yml` to get `tasks.project_key`.

**Usage:** `/dma:reject <ISSUE-KEY> <reason>`

Example: `/dma:reject <ISSUE-KEY> implementation doesn't follow existing patterns from <similar-file>`

**Steps:**

1. Read the issue with `${CLAUDE_PLUGIN_ROOT}/bin/dma issue read <KEY>` from `$ARGUMENTS`.
2. Read the issue's comments to find which files were created/modified by the agent.
3. Revert those files:
   - Modified files: `git restore <file>`
   - Created files: `rm <file>`
4. Run `${CLAUDE_PLUGIN_ROOT}/bin/dma issue handoff <KEY> dev` with the comment body:
   ```
   **REJECTED**
   Reason: <the user's reason>
   Reverted files: <list>
   ```
   The skill transitions the issue to `To Do`, sets `agent:dev`, and posts the comment.
5. Confirm to the user what was reverted.

The rejection comment stays in the issue tracker permanently. Next time an agent picks up this task, it will see the rejection and know what to fix.
