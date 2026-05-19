# Sentinel knowledge base

Durable storage for sentinel meta-agent. Read by sentinel at the start of every triage (`/sentinel full-audit`, `/sentinel retrospective`, conversation mode).

## Structure

- `patterns/` — recurring problem shapes observed in past flags. Each file documents one shape with its signature, observed instances, and a triage rule. Stack-agnostic. Use to recognize when a new flag matches a known meta-form.
- `solutions/` — conditional recommendations. Each file declares an IF-condition (a property of an area, its stack, or its role) at the top and a THEN-recommendation (rules or fixes to apply). Sentinel reads all solutions and applies those whose conditions match the affected area.

## How sentinel uses this

1. On triage start, scan `patterns/*.md` (small catalog, read all).
2. For each flag referencing an area, read `.claude/areas/<area>/area.yml` to learn the area's characteristics, then scan `solutions/*.md` and apply those whose IF-condition matches.
3. If a new flag matches a known pattern: cite the pattern, don't re-derive.
4. When a flag generalizes beyond its first instance: add a new entry to `patterns/` and link to it from the originating flag's resolution.
5. When a recurring fix shape applies to all areas matching some condition: add a new entry to `solutions/`.
