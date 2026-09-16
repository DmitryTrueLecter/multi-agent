---
type: llm
---

Inspect every backticked identifier, path, and rule ID in the "after" spans of the Fix block.

PASS if each one exists in the workspace (`libs/notify/render.py`: `render`, `_load`, `TEMPLATES`, `lru_cache`; `apps/notify/render_client.py`; `libs/notify/templates/`; rule IDs present in `areas/notify/area.yml`) or is introduced by the Fix itself as a rule ID, and no undefined qualitative term ("renderer module", "hot path", "properly") is used as a criterion.

FAIL if an after-span relies on a name that exists nowhere in the workspace (for example `TemplateCache`, `TemplateRegistry`, `warm_all`) or on an undefined qualitative term to decide a violation.
