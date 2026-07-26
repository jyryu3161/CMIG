# CMIG Phase 4 (batch 2) — all remaining known-open items

**All 9 items landed.** Each was verified by re-running the evaluator's own repro and reading the
corrected output; nothing below is claimed from inspection alone.

Regression tests: `tests/test_phase4_batch2_regressions.py` (**43 tests**, no solver required),
plus edits to three existing tests whose contracts I deliberately changed (§11).

---

## 1. `target_influence_share` was exactly inverted (R2-RT **F4**)

The share ignored abundance, so as the swept member's abundance *rose* its reported influence
*fell* — the trend ran backwards, which is worse than a wrong magnitude.

`cmig/core/metrics.py` now computes the community-level contribution (per-taxon flux × abundance)
before taking any share. Re-running the red-team's sweep:

| abundance | member flux | old (unweighted) | **new** |
|---|---|---|---|
| 0.25 | 7.144 | 0.75 | **0.500** |
| 0.50 | 3.804 | 0.50 | **0.500** |
| 0.75 | 2.711 | 0.25 | **0.500** |

Flat 0.50, matching the red-team's own derivation: with one producer and one consumer at steady
state the weighted contributions are equal and opposite by construction.

**Two quantities, not one.** F4's second half is that `abs()` credited *consumers* as producers.
Rather than pick one meaning and lose the other, both now exist under self-describing names:

- `target_turnover_share` — |contribution| over **all** members (the flat 0.50 above);
- `target_secretion_share` — producer-only; a member that consumes the target scores 0.

The CSV gains `target_secretion_share` and `target_member_contribution` alongside the existing
column, so a reader can see which question each number answers.

## 2. A failed solve exited 0 and still drew a full figure set (R2-C **D4**)

Two separate defects with one root: artifacts on disk were treated as evidence of a result.

- **Exit code.** New `EXIT_ANALYSIS_FAILED = 3`, distinct from argparse's `2` — *"it ran and the
  science failed"* is not *"bad input, nothing ran"*. Applied via `_exit_code_for_status` on 7
  parsers, with `--allow-failed-run` as an explicit opt-out for anyone who wants the artifacts
  anyway.
- **Figures.** `render_interaction_figures(..., failure_banner=…)` stamps the banner onto every
  SVG and raster. Three cases, most severe first:
  - community solve failed → `NOT A RESULT — community solve <status>; figures show inputs only`
  - host solve failed → `NOT A RESULT — host solve <status>; no metabolite reached the host`
  - solved but nothing coupled → `NO COUPLING — no microbial metabolite matched a host exchange`

Verified on the D4 repro: exit is now `3`, and the banner is legible on the raster. (First attempt
used PIL's default bitmap font — ~11 px on a 3900 px-wide image, i.e. invisible. `_banner_font`
now scales a truetype face to the banner height; checked by eye, not just by code path.)

## 3. Cross-feeding edges claimed an attribution the data does not identify (**A-B15 / B-D6**)

A shared metabolite pool does not identify which donor fed which recipient — the pairwise weights
are an *allocation*, not a measurement. Nothing in any artifact said so.

Tidy schema **1.1 → 1.2**; edges gain four columns:

| column | direct (secretion/uptake) | cross-feeding |
|---|---|---|
| `allocation_method` | `direct_flux` | `proportional_to_partner_flux` |
| `identifiable` | `True` | **`False`** |
| `weight_lo` / `weight_hi` | FVA interval when `--fva` | `None` |

The interval is deliberately withheld from allocated edges: an FVA range on the *exchange flux*
would look like a confidence interval on the *attribution*, which is exactly the overclaim being
fixed. `manifest.json` gains an `edge_attribution` block so the method is readable from the
artifact. `read_legacy_or_upgrade` migrates v1.1 edges with `None` (honest "unknown") rather than
back-filling a method the old run never used.

## 4. dFBA grew on substrates it was not tracking (R2-C **D5**)

`simulate_dfba` only bounds exchanges named in `initial_concentrations`; every other exchange keeps
its model default. A direct core probe reproduced D5 exactly: biomass rose 0.05 → 0.0619 while the
managed glucose sat at **exactly 10.0**, untouched. The organism was eating **fructose** (`EX_fru_e`
at 5.0) plus 18 other untracked substrates. A Km sweep on glucose under those conditions measures
nothing.

- Untracked uptake is now detected, reported (`untracked_uptake`, `n_untracked_uptake`, `warnings`)
  and printed to stderr.
- `--close-untracked-uptake` turns the run into an actual control.

**The control run returns `infeasible`** — proving the original growth was entirely untracked, not
merely contaminated by it. That is the strongest available confirmation of D5.

`close_untracked_uptake` is in the dFBA hash components, so the open and closed runs fingerprint
differently (`c041955e…` vs `29da84a7…`) rather than colliding.

## 5. The multi-target path produced no figures and no pool diagnostics (R2-C **D9**)

`GUI_CLI_WORKFLOWS` advertised `pool_diagnostics.csv` and figures for `cmig search`; the
multi-target branch wrote neither. Extracted `_write_pool_diagnostics_csv`, threaded
`diagnostics=` through `_write_multi_target_outputs`, and added `_write_multi_target_figure`
(stacked per-target contribution bars).

The new figure incidentally became the clearest evidence for item 9 — every bar was pure acetate.

## 6. `gene-ko-search` ranked a zero-effect knockout first (**B12 / F7**)

Ranking was by absolute post-KO score, so a KO that changed nothing outranked the one that mattered.
On the evaluator's repro:

| gene | post-KO score | Δ | old rank | **new rank** |
|---|---|---|---|---|
| `LDH_D` | 12.11 | −0.000093 | **1** | 3 |
| `PTA2` | 12.11 | −0.000131 | 2 | 2 |
| `PTAr` | 11.38 | **−0.7346** | 3 | **1** |

`_ko_sort_key(row, rank_by=…)` sorts by `-abs(delta)` for `effect` (default) and `-score` for
`remaining`; `--rank-by` selects. The printed line now reads `rank 1 (largest effect)` — the old
label said "best", which was the actual claim being made.

## 7. `host-map` merged unreviewed stereoisomer swaps into the reviewed map (**F5**)

D/L swaps went into the same flat dict as exact matches, so a downstream run could silently consume
a mapping no human ever approved. The map file now splits `{interface_map, needs_review, unmatched}`,
and `_load_host_interface_map` **raises** on a map with pending `needs_review` entries unless
`--accept-unreviewed-map` is passed (3 parsers).

## 8. A 283-term objective was reported as "283 biomass reactions" (**A-B9**)

`n_biomass` counted objective *terms*. For `iAF987` that printed 283 biomass reactions, and the
optimum was plotted under the axis label "Growth rate" — which it is not.

`n_objective_terms` is now recorded in pool diagnostics, with
`objective_structure_warning`: *"objective has 283 terms; not a single biomass reaction — reported
growth is an objective value, not a growth rate."* When any member is multi-term the figure's axis
label changes to name them explicitly rather than asserting a growth rate for all.

## 9. Weighted-sum scalarisation collapses onto one metabolite (R2-RT)

The red-team measured all six SCFA per-target ranges at width ≈ 0. **This is not degeneracy and no
choice of weights fixes it**: maximising `Σ wᵢvᵢ` over a polytope is optimised at a *vertex*, so any
weight vector selects whichever metabolite has the best carbon-per-substrate yield. Re-weighting
moves which vertex wins, never that a vertex wins.

The fix is a different method, not different weights: `epsilon_constrained_solve` adds an explicit
per-target floor, swept over `PARETO_EPSILON_GRID`; `pareto_frontier_nd` then takes the
non-dominated set over all N objectives (the existing `pareto_frontier` handled only 2, which is
why the flag read `False` for the 6-target SCFA preset).

`--multi-metric pareto` on the evaluator's pool returns **3 non-dominated points** where the
scalarised path returned 1:

| ε | ac | but | lac__D | lac__L | ppa | succ |
|---|---|---|---|---|---|---|
| 0 | **12.11** | 0 | 0 | 0 | 0 | 0 |
| 0.05 | 9.77 | 0 | 0.359 | 0.354 | 0.261 | 0.285 |
| 0.15 | 5.05 | 0 | 1.078 | 1.062 | 0.784 | 0.853 |

ε=0 reproduces the old acetate-only answer exactly — it is one *endpoint* of the front, not the
answer. (`but` stays 0 at every level: this pool genuinely cannot make butyrate.)

Every non-pareto metric now carries `SCALARISATION_WARNING` naming the vertex bias and pointing at
`--multi-metric pareto`. Pareto runs report how many front points are single-metabolite specialists
(1 of 3 here) and declare `solution_semantics = epsilon_constrained_lp_non_dominated_set`, because
a front is **not totally ordered** — "rank 1" there is a reporting order, not a claim of best.

---

## 10. Two defects I introduced and the suite caught

Reported because they are the kind of thing that should not pass silently.

**The untracked-uptake loop crashed the emergency-clamp path.** It assumed `model.exchanges`
exists; the clamp tests use a minimal stub without it, and two previously-passing tests failed with
`AttributeError`. Split by intent:

- the **diagnostic** (`_record_untracked_uptake`) now returns quietly on a model that cannot
  enumerate exchanges, and skips an exchange missing from the flux vector — a diagnostic must never
  abort a finished simulation;
- the **control** (`--close-untracked-uptake`) *raises* in the same situation, because silently not
  closing the bounds would report a controlled experiment that never happened.

**The schema bump invalidated every committed golden** — see §12.

## 11. Deliberate contract changes to existing tests

Three, all changing an assertion that pinned the old (defective or now-stale) behaviour:

1. `test_tidy.py` — edge fixture gains the 4 identifiability columns.
2. `test_schema_migration.py` — v1.1 → v1.2 expectations.
3. `test_search_multi_target_metrics.py::test_metric_units_are_declared_for_every_metric` — the
   metric set gains `pareto`, and now asserts its "not totally ordered" caveat.

## 12. Golden regeneration — and why it is safe

`schema_version` is a *hashed* column, so bumping it to 1.2 changed the hash of **every** golden
table, including `nodes` and `profile` whose schemas did not change at all. Four tests failed with
what looked like a numeric regression.

I did not simply re-baseline. The regeneration (`REVIEW/scratch_p4b/regen_goldens.py`) is
**self-gating**: for each table it drops `schema_version` and the newly added columns and refuses
to write unless the remainder hashes identically to the committed golden. Result:

```
pair/nodes    new_columns=-        regenerated
pair/edges    new_columns=[4 cols] regenerated
pair/profile  new_columns=-        regenerated
gurobi/*      …                    regenerated   frozen run_hash still 29844e2910360332…
osqp/nodes    new_columns=-        regenerated
osqp/edges    new_columns=[4 cols] schema-only (floats kept; jitter within atol=1e-4)
osqp/profile  new_columns=-        regenerated
```

**OSQP got a schema-only migration.** Its edge weights differed by up to 7.1e-5 — within the test's
own `atol=1e-4`, and structurally just two symmetric degenerate optima swapping between three
identical *E. coli* members. But re-baselining on one jittery run could put a later run past
tolerance, so I kept every committed float **bit-for-bit** (verified against `git show HEAD:`) and
migrated only the schema. The new columns are deterministic functions of `edge_type`, so no
solver-dependent value crossed over.

A new test pins the goldens' stamp to `TIDY_SCHEMA_VERSION`, so the next schema bump fails with
*"regenerate the goldens"* instead of an opaque hash mismatch.

## 13. Batch-1 invariant — re-verified after every edit

| Check | Result |
|---|---|
| `solve-fixture --targets scfa` run_hash | `29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab` — **bit-identical** |
| `RUN_HASH_COMPONENTS` | untouched (still the frozen 11) |
| `cmig golden verify` (SC-5) | `[OK] gurobi 0.39.0`, `[OK] osqp 0.39.0`, exit 0 |
| stored `run_hash` in golden config | never rewritten (asserted in the regen script) |

The tidy schema version is not one of the 11 components, which is why the bump moved the tidy table
hashes without moving the run hash.

## 14. Gates

| Gate | Result |
|---|---|
| `uv run pytest -q` | **exit 0** — 731 tests, **0 failures, 0 errors**, 2 skipped |
| `uv run ruff check cmig tests` | **All checks passed** |
| `uv run cmig golden verify` | **exit 0** — `[OK] gurobi 0.39.0`, `[OK] osqp 0.39.0` |

Both skips are pre-existing (`Recon3D.xml` fixture absent), unchanged from batch 1. The suite grew
688 → 731, exactly the 43 new regression tests.

## 15. Limits worth stating

- **Item 3's FVA intervals are only populated when `--fva` is passed.** Without it the columns are
  `None` — absent, not zero-width.
- **The Pareto front is exhaustive over the ε-grid, not over the true continuous front.** Five
  levels sample it; a finer grid would find more points. The grid is recorded in the manifest.
- **Item 9's front was verified on a 2-member pool.** The mechanism is size-independent, but I did
  not re-verify at larger consortium sizes.
- **Item 4's warning lists untracked *uptake*, not untracked secretion.** Secretion does not
  invalidate a Km sweep the same way, so it is not flagged.
