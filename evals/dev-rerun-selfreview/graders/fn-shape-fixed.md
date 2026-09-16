---
type: llm
focus: { source: file, path: apps/shipments/service.py }
---

Judge the file after the dev's edits.

PASS if both hold: (1) no function takes a boolean behavioural-mode parameter — `include_delivered` is gone and the listing is exposed as two functions (one hiding delivered shipments, one including them), or an equivalent split without a flag; (2) `ship` takes at most four domain parameters besides `store` (the unused `weight_kg`, `service_level`, `insured`, `notify_email` dropped or grouped into a value type that is actually used), and it still records carrier and tracking number.

FAIL if a boolean mode switch remains on any function, if `ship` still lists unused parameters, or if `advance`'s behaviour changed.
