---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: |
__CHARTER:team-lead__
---

Bash is unavailable in this environment: find the project root with `Glob` on `.claude/dma/config.yml` (the absolute path it returns gives the prefix) and use `Read` for every file. The tracker CLI is unavailable too; this request needs none of it.

Current state: the team members screen. Question: what a person managing the team meets there today — what they see, what they can do, what happens when an invite goes wrong — and whether anyone can remove anyone.
