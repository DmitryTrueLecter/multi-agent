---
description: "Initialize dma project-local scaffolding (config.yml, arch.yml, Justfile, resume script) into .claude/dma/. Idempotent — never overwrites existing files."
---

Run the dma plugin's installer against this project and report what it created or skipped:

`bash "${CLAUDE_PLUGIN_ROOT}/install.sh" "${CLAUDE_PROJECT_DIR}"`

If `.claude/dma/config.yml` was just created, tell the user to fill it in — it ships as a blank template (tracker provider, project/team key, workflow statuses).
