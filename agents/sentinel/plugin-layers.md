# Plugin layers

The system spans two trees. Shared-plugin code lives in the `dma` plugin at `${CLAUDE_PLUGIN_ROOT}/`; project-local dma state lives in the project repo under `${CLAUDE_PROJECT_DIR}/.claude/dma/`. The path prefix is the layer signal — no symlink inspection needed.

| Layer | Location | Effect |
|-------|----------|--------|
| project-local | `${CLAUDE_PROJECT_DIR}/.claude/dma/` — `config.yml`, `arch.yml`, `areas/**`, `devops/**`, `product/**` (analyst's; `product/drafts/` gitignored), `scripts/**`, `Justfile` | this project only |
| shared-plugin | `${CLAUDE_PLUGIN_ROOT}/**` — agents, commands, skills, hooks, scripts, sentinel reference files | every project that enables the `dma` plugin |

Claude Code's own `settings.json` and `settings.local.json` sit at `${CLAUDE_PROJECT_DIR}/.claude/` (not under `dma/`); the harness owns them, not the plugin.

Tag findings by layer; for `shared-plugin`, append `(cross-project: yes)`. Reach for the customization seams (`.claude/dma/areas/**`, `.claude/dma/config.yml`) before editing a shared file.
