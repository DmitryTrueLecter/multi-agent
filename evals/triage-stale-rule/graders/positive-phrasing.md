---
type: llm
---

Consider only the text inside the fenced blocks labelled "after" in the Fix section. Ignore the "before" blocks, the Finding, the Checked line, and the Note.

For each after block, count occurrences of the tokens "no " (the word), "never", "do not", "must not". A block whose count is 0 or 1 passes; a block whose count is 2 or more fails. An enumeration of violations joined by "or" ("reads a template itself, calls `_load()`, or clears the cache is a violation") contains none of the tokens and passes.

PASS if every after block passes. FAIL if any after block has two or more of the tokens.
