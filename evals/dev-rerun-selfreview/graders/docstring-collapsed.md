---
type: regex
target: { source: file, path: apps/shipments/service.py }
pattern: '"""[^\n]*\n[^\n]*\n[^\n]*\n[^\n]*"""'
match: not_contains
---
