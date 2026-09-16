# Plugin evals

Behavioural tests for the dma skills, run with `claude plugin eval` (docs: code.claude.com/docs/en/plugin-evals). Each case is a prompt plus graders; a run spawns a sandboxed `claude -p` child with only this plugin loaded.

## Run

```
python3 evals/build.py                       # render each case's prompt.md; the template's __CHARTER:<agent>__ marker picks which agents/<agent>.md is inlined
claude plugin eval . --case triage-stale-rule --runs 3 --ablation none --scaffold --judge-model sonnet --max-cost-usd 6 --no-publish --json evals/results/<name>.json
```

- `--scaffold` runs the case's `fixture.sh` to seed the workspace; pass it only for cases you wrote.
- `--ablation none` skips the no-plugin arm — the sentinel cases have no meaning without the plugin.
- `--judge-model sonnet` — the default haiku judge is too loose for the prose rubrics.
- No `--allow-tools Bash`: the sandbox refuses the grant on this machine (a symlink inside `~/.docker`); the agent uses Read/Glob/Grep instead. Team-lead cases therefore tell the agent to find the project root with `Glob` — its Bootstrap otherwise runs `pwd`.
- `prompt.md` and `results/` are generated and gitignored. Re-run `build.py` after editing the charter.

## Cases

| Case | Exercises | Trap |
|---|---|---|
| `triage-stale-rule` | `dma:sentinel-triage` on one RULE-CONTRADICTION flag in a fictional `notify` area: priming, report format, Fix derived from code, checklist (`Checked:` line) | the flag suggests deleting the rule; the fix must rewrite it from the code |
| `tl-current-state` | `dma:team-lead-current-state` on a fictional `members` screen: user-terms description, no mechanics, open points marked, no preamble | the removal path has no authorization check — surface it, do not design it |
| `tl-on-hold-drift` | `dma:team-lead-on-hold` on an `ARCH-EPIC-SYNC drift` handoff: whole-epic read, reconcile task with labels / Blocks / files / SHAs, hold until Done, wait for approval | `schemas.py` is an `arch.yml` escalation trigger — the architect goes first |

## Reading results

`results/<name>.json` → `cases[].arms.with[].graders[]` has `passed` per grader per run; `evidence` holds the agent's final message. Compare per-grader pass counts across runs, not the aggregate score alone. Change one thing (charter, skill, or rubric) per iteration; to attribute an effect, run the previous version under the same rubrics (`git stash` the prompt files, `build.py`, run, `git stash pop`, `build.py`).
