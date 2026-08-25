# Round-9 Coordinator Log

Coordinator: Claude (Fable 5) session. Workers: codex `gpt-5.6-sol` xhigh per
Orca worktree, launched per `REVIEW/ORCHESTRATION_NOTES.md` including the
round-8 postmortem's `-c check_for_update_on_startup=false` (no update incident
this round). Base: `aa6a845`. Sequential venv pre-sync 6/6; workers ran no git;
completion signal = report files.

## Track review results

| Track | Branch | Verdict | Notes |
| --- | --- | --- | --- |
| V1 dfba-community-cli | `feat/dfba-community-cli` | Accepted | U6's proposal implemented faithfully; envelope 17→18 additive; real CLI run reproduces U6's cross-feeding endpoint; the four round-8 kinds proven byte-identical across double console runs and promoted (community_dfba deliberately not promoted — timing telemetry is a required output). |
| V2 answer-quality | `fix/answer-quality` | Accepted | Fail-closed `community_contributions` with full consumer trace; N-dimensional pareto column sharing one dominance implementation with pareto mode; real-Gurobi verifications. |
| V3 render-pipeline | `feat/render-pipeline` | Accepted | RenderClient/Composer staged atomic publication (profile path byte-identical incl. sidecars); the three orphan R panels really rendered (ggraph 2.2.1 / ComplexHeatmap 2.18.0 / circlize 0.4.18) with presets applied and basis captions present. |
| V4 gui-medium-tools | `feat/gui-medium-tools` | Accepted | Spec-§11 medium surface; 9-preset byte-integrity proven; added an unrequested but correct safety rule (nutrients-only view refuses merge mode). 133 GUI tests green on the host. |
| V5 stats-5b5c-core | `feat/stats-5b5c-core` | Accepted | StatsConfig + seeded gated embedding pipeline + volcano prep; same-seed identity and different-seed divergence pinned. |
| V6 second-solver-repro | `analysis/second-solver-repro` | Accepted | Report-only audit that found three real defects (below). One classification corrected by the coordinator: the "stale tutorial number" is actually an under-specified document — the original 0.4/0.35/0.25 run reproduces 0.1502/a06d5799 exactly; V6 reconstructed with 1/3 splits because the tutorial omitted the abundances. |

## Integration (`round9/integration`)

Merge order V6 → V5 → V3 → V2 → V4 → V1: zero conflicts (third consecutive
round the ownership partition held exactly).

Coordinator commits:

1. **V6 defect fixes** (`85f7667`):
   - *Defect 2*: `EngineService.solve_fixture` now hashes components and the
     manifest at `VARIANT_DECIMALS[solver]`; fresh OSQP emits the frozen
     `a422eb89…`, Gurobi byte-unchanged — regression-pinned for both solvers.
   - *Defect 1*: `cmig solve`/`solve-fixture` verify the documented
     edge↔profile mass identity (`edge_profile_consistency` in
     `core/interactions`) and fail closed (exit 3, artifacts kept, worst
     offender named, `qp_only_approximate` pointer for OSQP). Verified live:
     fixture OSQP still exits 0 (residual ~1e-15); the audit's tutorial
     scenario now exits 3 — and this run's broken state differed from V6's
     measurement (residual 2.5e4 vs 1.5e3), i.e. the invalid state is not even
     run-stable.
2. **Cross-cutting** (`0cbdcb8`): abundance-impact all-failed sweeps exit 3
   (partial failures unchanged); `render-figure --panel` per V3's exact
   contract, verified with real R renders; pareto documentation rewritten in
   USER_GUIDE/SKILL (historical CHANGELOG text left as history); tutorial now
   prints its exact taxonomy (defect 3); dfba-community docs + skill routing;
   `MissingAbundanceError` docstring covers every community-basis quantity;
   round-9 CHANGELOG entries; new regression tests for all of the above.

## Final gates on `round9/integration`

- ruff clean; `mypy cmig` 0 errors in 79 files.
- `golden verify-envelope`: unchanged for **18** kinds (community_dfba added
  additively by V1).
- `golden verify`: both solvers match published hashes — and a fresh OSQP
  fixture CLI run now actually emits that hash.
- Full randomized pytest: recorded in the merge commit to main.

## Deferred / round-10 candidates

- Stats CLI wiring (`stats-sweep` dimred/clustering/volcano flags + hashed
  StatsConfig manifest component — V5's report has the proposal).
- GUI surfaces for `dfba-community` and the panel renders.
- Root-cause the OSQP community solve itself (the gate now contains it; the
  underlying optlang/OSQP hybrid state remains wrong for real communities).
- Path-normalizing provenance for the promoted deterministic kinds (V1's
  relocation caveat).
- Multi-file artifact-set transaction (per-file atomicity is complete).
- 0.2.0 release execution per `docs/release-drafts/` (coordinator phase 3).
