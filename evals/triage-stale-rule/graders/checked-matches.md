---
type: llm
---

Compare the `**Checked:**` line with the Fix section above it.

PASS if the Checked line either says `no changes`, or lists checklist items (voice, positive phrasing, thresholds/terms, references, one home, every-sentence-a-criterion, fewest words) and for each names the concrete draft span that changed, and the Fix is consistent with each described result: a span said to be rewritten appears rewritten; a term said to be dropped is absent from the after blocks; an entry said to be deleted is shown in the Fix as deleted — its after block reads "(deleted …)" or the Fix states the deletion in words — and a sibling said to have received the rule ID shows that ID in its after block.

FAIL if the Checked line is missing or generic ("all items checked"), names no draft spans, or describes a result the Fix contradicts (for example "positive phrasing fixed" while an after block still contains two or more of "no "/"never"/"do not"/"must not", or "deleted" while the Fix shows that entry rewritten rather than removed).
