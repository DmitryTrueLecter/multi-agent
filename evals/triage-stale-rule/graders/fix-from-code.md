---
type: llm
---

The response is a sentinel triage report on flag NOTIFY-91. The flag suggests deleting rule NOTIFY-TEMPLATE-WARM. The code in the workspace shows templates now load lazily inside `render()` / `_load` in `libs/notify/render.py`; `TemplateCache` no longer exists.

PASS if the Fix rewrites the rule (does not merely delete it) so that the new invariant is derived from the code: rendering goes through `libs/notify/render.py` (`render()`), and a module that reads template files itself, keeps its own template cache, or calls a warm-up is the violation; and the ENFORCEMENT grep targets paths that exist in the workspace and no longer mentions `TemplateCache`.

FAIL if the Fix deletes the rule, keeps `TemplateCache.warm()` as a requirement, or names a function, class, or path that does not exist in the workspace.
