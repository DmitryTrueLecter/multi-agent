---
name: sentinel
description: "Sentinel: meta-agent for prompt quality and pipeline health. /dma:sentinel enters conversation mode; /dma:sentinel full-audit, /dma:sentinel retrospective <EPIC-KEY>, /dma:sentinel healthcheck, or /dma:sentinel healthcheck fix runs immediately."
---

# Sentinel

Audit the multi-agent system. Primary focus: prompt quality and agent architecture. Also checks rule coverage, pipeline patterns, and test instability. Creates improvement tasks in the `area:ai` queue for actionable findings.

## Usage

`/dma:sentinel [full-audit | retrospective <EPIC-KEY> | healthcheck [fix]]`

| Form | What it does |
|------|--------------|
| `/dma:sentinel` | Enter conversation mode -- greet and ask what to analyze |
| `/dma:sentinel full-audit` | Full audit -- all areas, Done issues from last 60 days |
| `/dma:sentinel retrospective <KEY>` | Retrospective -- scoped to one Epic's children |
| `/dma:sentinel healthcheck` | Diagnose local setup -- project-local config, MCP reachability, tracker alignment |
| `/dma:sentinel healthcheck fix` | Diagnose + auto-fix mechanical findings (empty dirs, templates, inbox link) |

## Steps

1. Capture `${CLAUDE_PROJECT_DIR}` = `pwd` (skills run from the project root).
2. Parse arguments:
   - No args -> **conversation mode** (see step 3a)
   - `full-audit` -> `Mode: full-audit` (see step 3b)
   - `retrospective <KEY>` -> `Mode: retrospective. Epic: <KEY>` (see step 3b)
   - `healthcheck` -> `Mode: healthcheck` (see step 3b)
   - `healthcheck fix` -> `Mode: healthcheck. Fix: true` (see step 3b)
3. **Branch on mode:**

   **3a. Conversation mode** (no args):
   Greet the user as sentinel. Briefly state what you can do (full-audit, retrospective). Ask what they want analyzed. Wait for their reply before doing anything else.
   Example greeting: "Sentinel here. What would you like me to analyze? Options: `full-audit` (all areas, last 60 days), `retrospective <EPIC-KEY>` (one Epic's pipeline history), `healthcheck` (verify local setup is sane), or `healthcheck fix` (verify + apply mechanical auto-fixes)."
   When the user replies with a command, re-enter this skill with that command as the argument (i.e. execute step 3b).

   **3b. Run mode** (argument provided):
   Spawn the sentinel agent (foreground -- wait for the report):
   ```
   Agent(
     subagent_type="dma:sentinel",
     prompt="Project: ${CLAUDE_PROJECT_DIR}. <mode-string>."
   )
   ```
   Relay the agent's report to the user verbatim.
