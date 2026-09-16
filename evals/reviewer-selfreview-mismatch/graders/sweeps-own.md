---
type: llm
---

The reviewer must run every mechanical sweep itself and not inherit dev's `clean` lines.

PASS if the `## Coverage` table lists each mechanical rule (DEV-COMMENTS, DEV-FN-SHAPE, DEV-NAMING, DEV-SPLIT, DEV-FAIL-FAST, DEV-ERRORS, DEV-COMPOSITION) against each changed file with `clean` / `N findings` / `N/A: reason`, the DEV-COMMENTS cell for `router.py` reports a finding, the `Self-review:` line names the DEV-COMMENTS mismatch (dev clean, reviewer found it — dev grepped service.py only), and the review does not re-list dev's fixed findings as new ones.

FAIL if any rule/file cell is empty, if router.py's comment block is missed, if the reviewer copies dev's `clean` verdicts without its own sweep, or if it invents findings on code that complies.
