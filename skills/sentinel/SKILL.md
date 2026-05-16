---
name: sentinel
description: "Sentinel: meta-agent for prompt quality and pipeline health. /sentinel enters conversation mode; /sentinel full-audit or /sentinel retrospective <EPIC-KEY> runs immediately."
---

# Sentinel

Audit the multi-agent system. Primary focus: prompt quality and agent architecture. Also checks rule coverage, pipeline patterns, and test instability. Creates improvement tasks in the `area:ai` queue for actionable findings.

## Usage

`/sentinel [retrospective <EPIC-KEY>]`

| Form | What it does |
|------|--------------|
| `/sentinel` | Enter conversation mode -- greet and ask what to analyze |
| `/sentinel full-audit` | Full audit -- all areas, Done issues from last 60 days |
| `/sentinel retrospective <KEY>` | Retrospective -- scoped to one Epic's children |

## Steps

1. Capture `<abs-project-root>` = `pwd` (skills run from the project root).
2. Parse arguments:
   - No args -> **conversation mode** (see step 3a)
   - `full-audit` -> `Mode: full-audit` (see step 3b)
   - `retrospective <KEY>` -> `Mode: retrospective. Epic: <KEY>` (see step 3b)
3. **Branch on mode:**

   **3a. Conversation mode** (no args):
   Greet the user as sentinel. Briefly state what you can do (full-audit, retrospective). Ask what they want analyzed. Wait for their reply before doing anything else.
   Example greeting: "Sentinel here. What would you like me to analyze? Options: `full-audit` (all areas, last 60 days) or `retrospective <EPIC-KEY>` (one Epic's pipeline history)."
   When the user replies with a command, re-enter this skill with that command as the argument (i.e. execute step 3b).

   **3b. Run mode** (argument provided):
   Spawn the sentinel agent (foreground -- wait for the report):
   ```
   Agent(
     subagent_type="sentinel",
     prompt="Project: <abs-project-root>. <mode-string>."
   )
   ```
   Relay the agent's report to the user verbatim.
