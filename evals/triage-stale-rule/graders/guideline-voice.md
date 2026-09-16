---
type: llm
---

The fixture's `guidelines:` list already contains, as its first entry: "Keep templates under `libs/notify/templates/` and render through `libs/notify/render.py`." The flagged guideline is the second entry (about `TemplateCache.warm()`). Look at what the Fix does with that second entry.

PASS if either: (a) the Fix deletes the second entry (or folds only the rule ID into the first entry) because the first entry already states the action; or (b) the rewritten second entry opens with an imperative verb, states an action the first entry does not already state, cites the rule ID, and is at most two sentences.

FAIL if the rewritten entry repeats the first entry's action ("keep templates under … / render through …") in any wording, opens with a noun phrase or a statement of fact, explains how the mechanism works ("which caches each template…", "so a direct read re-reads…"), restates the rule's violation list, or runs past two sentences.
