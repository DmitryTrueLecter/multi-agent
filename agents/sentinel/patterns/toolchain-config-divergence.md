# TOOLCHAIN-CONFIG-DIVERGENCE

## Signature

The same toolchain command (test runner, linter, type checker) is invoked twice in different configurations: a strict mode for the build/CI gate and a relaxed mode for the per-task test gate. The relaxed mode silently passes problems that the strict mode catches. Treating the relaxed `test_command` as the correctness gate misses the class of defects only the strict mode reports.

## Observed instances

- **`ts-jest` `isolatedModules: true, diagnostics: false` vs `tsc` (backend, 2026-05-18, TRACKAI-67).** TypeScript-only errors (e.g. TS7011 implicit-any in property assignments) passed the test gate and broke CI build. Fix: added `build_command` to area `qa.yml`; team-lead close-out now runs both (see `agents/team-lead.md` → "Build/typecheck gate" step).

## Triage rule

When a build/CI failure surfaces an error class that the per-task test suite should logically have caught: ask whether `test_command` and the build use the same configuration of the underlying toolchain. If not, the gap is the cause; recommend a parallel strict-mode gate (e.g. `build_command` field in `qa.yml`) so both configurations enforce the contract.

## Untriggered candidates

Other shapes likely to fit this pattern when they surface:

- `pytest --no-cov` vs `pytest --cov` — coverage-only failures
- `ruff check` vs `ruff format --check` — formatting drift
- `mypy --no-strict` vs `mypy --strict` — strict-mode-only type errors
- ESLint with vs without `--max-warnings 0` — warning-as-error drift
