# CMIG Phase 2 — Correctness Fixes (Evaluator A, Claude Opus 5)

Implements the P0/P1 correctness items from `REVIEW/report_opusA.md`. All seven assigned items
landed, each with a regression test. Figure-layer files (`cmig/core/interaction_figures.py`,
`cmig/render/*`) were **not touched** — they belong to the parallel figure task.

**Gate results:** `uv run pytest -q` → **EXIT=0**, 535 collected, **533 passed / 2 skipped / 0
failed**, 107 s. Both skips are `tests/test_recon3d_host.py` — "Recon3D.xml fixture is not present"
(pre-existing, no host GEM ships). `uv run ruff check cmig` and `uv run ruff check tests` →
**All checks passed** (exit 0 both). The pre-change baseline was also EXIT=0, and the 37 new tests
are purely additive, so nothing regressed.

## Files changed

| File | Items |
|---|---|
| `cmig/core/engine.py` | P0-1 |
| `cmig/core/host_coupling.py` | P0-2 / P1-7 |
| `cmig/core/search.py` | P1-3 |
| `cmig/core/search_product.py` | P1-3, P1-4, P1-5 |
| `cmig/core/targets.py` | P1-4 |
| `cmig/cli/main.py` | P0-2, P1-3, P1-4, P1-5, P1-6, P1-7 |
| `cmig/io/solve_output.py` | P0-1 (1 line — see "outside assigned scope") |
| `tests/test_engine_solver_guard.py` (new, 5 tests) | P0-1 |
| `tests/test_run_status_reporting.py` (new, 10 tests) | P0-2, P1-7 |
| `tests/test_search_multi_target_metrics.py` (new, 17 tests) | P1-3, P1-4, P1-5 |
| `tests/test_strain_growth_medium_basis.py` (new, 5 tests) | P1-6 |

All 37 new tests run without micom/Gurobi (solver doubles + pure functions), so they gate in CI.

---

## P0-1 (B1) — MICOM delegate guarded, with a pFBA fallback

`MicomEngine.cooperative_tradeoff` no longer lets a solver exception escape. New
`_delegate_cooperative_tradeoff` tries `pfba=True`, retries once with `pfba=False`, and only then
gives up with `status="solver_failed"`. `SolveResult` gained `warnings: list[str]` and
`flux_normalization_method: str`; `status` gained `"solver_failed"`. A readout failure on a returned
solution is structured the same way. `ValueError` for an out-of-range `tradeoff_f` still fails fast.

The retry is a real recovery, not just a graceful failure — isolated measurement on the failing
community: `pfba=True` → `GurobiError`; `pfba=False` → `optimal, growth 0.5849`.

**Verified repro** (`cmig strain-growth --model-dir <iHN637+iYO844>`):

| | Phase 1 | Phase 2 |
|---|---|---|
| exit code | **1** | **0** |
| stderr | raw `gurobipy...GurobiError: Unable to retrieve attribute 'X'` traceback | none |
| result | no output directory | `community_growth 0.58486`, iHN637 0.22445 alone, iYO844 0.11797 alone |
| stdout | — | `warning: pfba_stage_failed; reporting non-parsimonious flux distribution` |
| summary `diagnostic` | — | structured `{"code":"solver_error", … "pFBA flux stage failed: GurobiError: …"}` |

The degradation is never silent: it appears in `warnings`, in the structured `diagnostic`, and in
`flux_normalization_method` (`"pfba"` → `"fba"`), which now flows into the solve manifest so a
`run_hash` cannot claim pFBA provenance it does not have.

## P0-2 (B1 silent half) — unevaluable candidates leave the ranking

`_cmd_host_search_bigg` splits rows on `evaluation_status`; only `ok` rows are ranked. Failures go
to a new `unevaluated` block in `host_search_summary.json`, plus `host_search_unevaluated.csv`,
`n_candidates_failed`, and a top-level `warnings` list naming each dropped consortium. The CLI now
prints `ranked: N/M`. A failed candidate can no longer appear as a zero-length bar indistinguishable
from a real host objective of 0.

**Verified**: re-running the phase-1 leave-one-out now reports `ranked: 7/7`. The candidate that
previously crashed and sat at rank 7 with `score=0` (`iHN637+iYO844`) now solves to host objective
**0.876997** — P0-1 removed the failure rather than merely labelling it. The "still fails" path is
covered by unit tests (unevaluated block, warnings, `status: degraded`, empty-ranking → `failed`).

## P1-3 (B3) — a missing exchange contributes 0, it does not disqualify

`joint_target_solve` optimises over the present targets and reports absent ones as flux 0, listing
them in `missing_targets`; only an all-absent target set is `status="missing"`.
`_evaluate_members_multi` does the same per target. Genuinely non-optimal LPs (infeasible /
baseline failure / solver error) still disqualify. `MultiTargetRank` gained `missing_targets` and
`flux_basis` (`joint_weighted_lp` vs `per_target_capability_not_simultaneous` vs `unevaluated`),
both emitted to CSV and JSON, so per-target capability maxima are never shown in the same row as a
joint solution without a marker.

**Verified** (6-target SCFA search, 3 small models): `iAF987+iHN637`, which phase 1 dropped for
lacking `EX_succ_m`, is now **rank 3 with score 10.235** and `missing_targets: ["succ"]`.
`iAF987+iYO844` is still excluded, but now for the right reason — `target LP returned no solution
object (solver_status=infeasible)` — and its three non-zero fluxes carry
`flux_basis: per_target_capability_not_simultaneous`.

## P1-4 (S1 core) — `--target-preset scfa` and `--multi-metric`

`targets.py` gained `preset_targets()` and a strict `parse_carbon_number()` (returns `None` rather
than guessing, so a bad formula stops the run instead of silently weighting by 1).
`cmig search` gained `--target-preset {scfa}` and
`--multi-metric {normalized_weighted,carbon_equivalent,raw_sum}`. For `carbon_equivalent` the CLI
reads each target's carbon number from the pool models' metabolite formulas, multiplies it into the
weights, and records `carbon_numbers` + `carbon_number_sources` in the summary. Absolute metrics set
the joint-LP scales to 1.0 so the score keeps real units and does not depend on the candidate set;
`normalized_weighted` keeps its previous behaviour and now carries an explicit warning that it is
dimensionless and not comparable across runs. `MULTI_METRIC_UNITS` is emitted as `score_unit`.

**Verified** — same pool and target set as phase 1:

| | Phase 1 | Phase 2 (`--target-preset scfa --multi-metric carbon_equivalent`) |
|---|---|---|
| best score | `6.32603e-05` (dimensionless, decided at the 5th decimal) | **24.2239 mmol C gDW⁻¹ h⁻¹** |
| carbon numbers | n/a | `ac 2, but 4, lac__D 3, lac__L 3, ppa 3, succ 4` from `iAF987:*` formulas |
| candidates ranked | 2 of 4 | **3 of 4** |
| summary `status` | absent (`inspect-run` → `unknown`) | `degraded` |

Cross-check: 24.2239 mmol C = 12.1120 mmol acetate × 2 C, and 12.1120 is exactly the flux the
independent single-target acetate search reports for the same consortium.

## P1-5 (B4) — tie and all-zero warnings

New pure `_ranking_degeneracy_warnings` is applied to both the single- and multi-target paths and
echoed to stdout. **Verified** on the butyrate search where all 10 candidates tie at flux 0 —
phase 1 had `warnings: []` and printed `best: iAF987+iHN637 flux=0`; phase 2 prints the same line
followed by `warning: no candidate achieved a non-zero target flux; the ranking order is arbitrary
and rank 1 must not be reported as the best producer`.

## P1-6 (B5) — strain-growth applies one medium to both legs

The single-model leg now receives the same `MediumSpec` through `apply_medium_checked` before
solving. The summary carries `medium_basis` with `medium_source`, `medium_checksum`, and
`single_medium_equals_community_medium`; `strain_growth.csv` gained `single_medium_applied`. If any
single leg fails to run under the shared medium, `media_matched` goes false and a warning states
that the alone-vs-community difference is not attributable to interaction. Engine `warnings` (e.g.
the pFBA fallback) are propagated into the summary.

## P1-7 (B6) — top-level status derived from the worst sub-status

New `_worst_status` / `_run_status_from_solve` (unknown values are pessimistically `failed`).
`host_microbe_bigg_summary.json` derives `status` from the community and host statuses, and
`host_coupling.py` adds a warning when the host solve is non-optimal. `_resolve_run_status` lets
`inspect-run` derive a status from `top_ranked`, `reports`, or the solve manifest's `diagnostic`
instead of returning `unknown`, and reports how it got there via a new `status_source` field.
`RUN_SUMMARY_FILES` learned `model_quality`, `host_exchange_map`, `dfba_sensitivity`, and
`publication_benchmark`.

**Verified** — re-running the host-infeasible coupling: top-level `status` is now **`failed`**
(phase 1: `"ok"`) with `host solve was not optimal (status=infeasible); the reported host objective
is not a result` in `warnings`, and `inspect-run` agrees. Across my 14 phase-1 run directories,
`inspect-run` no longer returns `unknown` for any kind or status.

---

## Outside the assigned scope (one line, flagged)

`cmig/io/solve_output.py` had `flux_normalization_method="pfba"` hardcoded. Left alone, a run that
fell back to non-parsimonious flux would still be hashed and recorded as pFBA — which would make
P0-1's honesty guarantee false at the manifest layer. Changed to read the value off the result
(`getattr(result, "flux_normalization_method", "pfba")`). It does not touch the figure files and
does not change any existing run's hash.

## Deliberately not done

- **Figures.** No changes to `interaction_figures.py` or `cmig/render/*` per the task boundary, so
  every figure defect from the phase-1 report (units, panel letters, legends, `--journal-preset`
  being ignored, 300 dpi RGBA TIFFs, colorblind palettes) is untouched here.
- **`host-search-bigg` tie warning.** P1-5 was scoped to `search_product.py`. The verification run
  surfaced a new instance worth a follow-up: ranks 6 and 7 are exactly tied at `0.876997214427`
  and nothing says so. `_ranking_degeneracy_warnings` is already a pure function and would drop
  straight into `_cmd_host_search_bigg`.
- **Remaining P2 items** from the phase-1 report (B9 objective-term counting, B10 silent FVA drop,
  B11 abundance-sweep degeneracy, B12 inverted KO "best", B13 μ\* recomputation, and the
  `host-ko-impact` capability gap) were not in this task's list.
- **`--multi-metric` for the single-target path** is not applicable, and multi-target search still
  carries its 100-candidate exhaustive ceiling — that is a tractability item (B13/P2-18), not a
  correctness one.
