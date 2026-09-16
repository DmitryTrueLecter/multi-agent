# Plugin evals

Behavioural tests for the dma skills, run with `claude plugin eval` (docs: code.claude.com/docs/en/plugin-evals). Each case is a prompt plus graders; a run spawns a sandboxed `claude -p` child with only this plugin loaded.

## Run

```
python3 evals/build.py                       # render each case's prompt.md; the marker __CHARTER:<agent>[,<skill>,...]__ inlines agents/<agent>.md plus the skills its Bootstrap invokes
claude plugin eval . --case triage-stale-rule --runs 3 --ablation none --scaffold --judge-model sonnet --max-cost-usd 6 --no-publish --json evals/results/<name>.json
```

- `--scaffold` runs the case's `fixture.sh` to seed the workspace; pass it only for cases you wrote.
- `--ablation none` skips the no-plugin arm — the sentinel cases have no meaning without the plugin.
- `--judge-model sonnet` — the default haiku judge is too loose for the prose rubrics.
- Cases that edit files pass `--allow-tools Edit Write` (not gated by the Docker check).
- No `--allow-tools Bash`: the sandbox refuses the grant on this machine (a symlink inside `~/.docker`); the agent uses Read/Glob/Grep instead. Team-lead cases therefore tell the agent to find the project root with `Glob` — its Bootstrap otherwise runs `pwd`.
- `prompt.md` and `results/` are generated and gitignored. Re-run `build.py` after editing the charter.

## Cases

| Case | Exercises | Trap |
|---|---|---|
| `triage-stale-rule` | `dma:sentinel-triage` on one RULE-CONTRADICTION flag in a fictional `notify` area: priming, report format, Fix derived from code, checklist (`Checked:` line) | the flag suggests deleting the rule; the fix must rewrite it from the code |
| `tl-current-state` | `dma:team-lead-current-state` on a fictional `members` screen: user-terms description, no mechanics, open points marked, no preamble | the removal path has no authorization check — surface it, do not design it |
| `tl-on-hold-drift` | `dma:team-lead-on-hold` on an `ARCH-EPIC-SYNC drift` handoff: whole-epic read, reconcile task with labels / Blocks / files / SHAs, hold until Done, wait for approval | `schemas.py` is an `arch.yml` escalation trigger — the architect goes first |
| `dev-rerun-selfreview` | `agents/dev.md` re-run after a reviewer block on a fictional `shipments` area: fix exactly the cited DEV-COMMENTS / DEV-FN-SHAPE findings, stay inside `dev.yml` write scope, hand off with a `## Self-review` block | four of `ship`'s parameters are unused — drop, do not group; a prior "Tests: 4 passed" is not this run's result (no Bash) |
| `reviewer-selfreview-mismatch` | `agents/reviewer.md` on the shipments task after dev's second attempt: own mechanical sweeps, reconciliation with dev's `## Self-review`, `[PROCESS-SELF-REVIEW]` finding, BLOCK to dev | dev's `DEV-COMMENTS: … service.py → clean` is true for service.py; the three-line comment block sits in router.py |

## Reading results

`results/<name>.json` → `cases[].arms.with[].graders[]` has `passed` per grader per run; `evidence` holds the agent's final message. Compare per-grader pass counts across runs, not the aggregate score alone. Change one thing (charter, skill, or rubric) per iteration; to attribute an effect, run the previous version under the same rubrics (`git stash` the prompt files, `build.py`, run, `git stash pop`, `build.py`).

## Harness limits found while building the suite

- `skills:` in a plugin agent's frontmatter does **not** preload the skill (tried `dma:agent-common`, `agent-common`, with and without `user-invocable: false`, in a fresh `claude -p --agent dma:dev` process, Claude Code 2.1.273). Shared content therefore reaches an agent through an explicit `Skill` invocation the charter orders as Bootstrap step 0 — the mechanism the sentinel and team-lead modes use — and the `Skill` tool must be in the agent's `tools:`.
- Agent definitions are cached for the session: an `Agent(subagent_type=…)` spawn from a running session sees the charter as it was at session start. Probe prompt changes in a fresh `claude -p --agent <name>` process.
- Long eval runs can be killed under memory pressure on this machine; prefer `--runs 1` smoke passes and one case per invocation when the host is busy.
