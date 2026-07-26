# CMIG Phase 3 — Regression Fixes + S3 Capability (Evaluator A, Claude Opus 5)

Addresses the round-2 findings from `report_round2_opus.md` (R2-A), `report_round2_redteam.md`
(R2-C) and `report_round2_codex.md` (R2-B). All six assigned items landed. **Every item below was
verified by re-running the evaluator's own repro command and reading the corrected output** — no
item is claimed from source inspection.

**Gates:** `uv run pytest -q` → **EXIT=0**, 614 collected, **612 passed / 2 skipped / 0 failed**
(both skips pre-existing: `Recon3D.xml` fixture absent). `uv run ruff check cmig` → **All checks
passed**. 84 new tests across 5 files; 3 pre-existing tests updated because my fixes deliberately
changed their contract (listed in §7).

---

## 1. P0-A — the strain-growth medium fix, done properly

**What was wrong.** All three evaluators independently confirmed the round-1 fix did not hold.
Root cause was an exchange-namespace mismatch: a community exposes `EX_glc__D_m`, each member model
exposes `EX_glc__D_e`, so one `MediumSpec` applied to both reached **neither** — while the summary
asserted `single_medium_equals_community_medium: true`. A second, deeper bug made the namespace
bridge impossible to write naively: `apply_medium_checked` gates on `model.medium`, which lists only
*currently-open* uptakes, so a medium could never **open** a closed exchange.

**What I built** (`cmig/core/medium_spec.py`): a metabolite-keyed bridge —
`exchange_metabolite()`, `model_exchange_index()` (over *all* exchanges, not just open ones),
`translate_medium_for_model()`, `apply_medium_translated(exact=…)`,
`effective_medium_by_metabolite()`, and `compare_effective_media()`. `strain-growth` now projects
the community's **effective** medium onto each member across the namespace, then **measures**
equality from the two effective media. A metabolite the member has no exchange for is recorded in
`medium_metabolites_unavailable_to_member` and exempted from the equality decision — it cannot be
offered that nutrient, which is biology, not a loss of control. New `--single-medium
{community,model_default}` keeps the old behaviour available, explicitly labelled.

**Verified — R2-A E4 / R2-C F3 / R2-B B4 repro:**

```
uv run cmig strain-growth --model-dir <iAF987,iHN637,iYO844> --out runs/p3/A_default2
```

| member | round-2 reported | phase-3 controlled | R2-A's independent control leg (E8) |
|---|---|---|---|
| iAF987 | 0.047322 | **0.047322435050338334** | 0.047322 ✓ |
| iHN637 | 0.224455 | **0.2992551392869518** | 0.299255 ✓ |
| iYO844 | 0.117966 | **0.7773368891734728** | 0.777337 ✓ |

My three controlled numbers reproduce R2-A's control script to every printed digit.
Consequence: **iYO844's headline conclusion inverts sign** — the reported "4.75× growth benefit
from the community" is a **0.72× cost** (alone 0.7773 → in community 0.5604), exactly what R2-A said
the controlled story should be. `single_medium_equals_community_medium: true` is now computed, with
`comparison_is_controlled: true`.

**Verified — the `--medium` path actually reaches the single leg** (R2-A D2 found `single_growth`
*byte-identical* to the no-medium run, proving it never applied):

| member | no medium | `--medium western_diet.csv` | identical? |
|---|---|---|---|
| iHN637 | 0.2992551392869518 | **1.0929318130480061** | no |
| iYO844 | 0.7773368891734728 | **2.406805969571474** | no |
| iAF987 | 0.047322435050338334 | 0.047322435050338334 | yes — *correct*: iAF987 has no glucose exchange, so a glucose diet cannot change it (recorded in its unavailable list) |

Strict mode (no `--allow-unknown-medium`) also no longer kills all three single legs; it now
completes with all three `optimal`. And the opt-out tells the truth:

```
--single-medium model_default → equal: False, controlled: False, status: degraded
  warning: ...NOT attributable to interaction and must not be reported as one
  warning: ...reports native growth capability, not a controlled interaction effect
```

## 2. P0-B — single-target search: no hidden failures, no false "best"

`search_model_pool` now partitions on `is_evaluable(status, score)`; only evaluable rows are
ranked, `--top-k` truncates **only** the ranked list, failures go to `result.unevaluated` +
`search_unevaluated.csv` + a top-level warning, and `_write_search_outputs` derives `status`
instead of writing `"ok"` as a literal. The CLI refuses to print a failed or zero-score candidate
as "best".

**Verified — R2-C F1 (`--top-k` hiding the failure):**

```
uv run cmig search --model-dir <pool3> --target ac --min-size 2 --max-size 2 --top-k 10   # and --top-k 2
```
Both now print **identically** on the failure:
`evaluated: 3/3 | ranked: 2 | unevaluable: 1` +
`warning: 1 of 3 candidates could not be evaluated ... : iAF987+iYO844`.
Round-2: the failure was visible at `--top-k 10` and **gone** at `--top-k 2`.

**Verified — R2-C F2 (`--target zzz`, nothing evaluable):** `status: failed` (was `ok`),
`top_ranked: []`, ranking CSV has **zero data rows**, stdout says
`no evaluable candidate: there is no best producer for this target`, `inspect-run` → `failed`.
Round-2: ranks 1/2/3 with flux 0, `best: iAF987+iHN637 flux=0` printed, `status: ok`.

**Verified — R2-B B1 (`regression_single_status`, exact command):** `status: failed`,
`ranked: 0`, `top_ranked: []`, no "best" line, `inspect-run: failed`. Round-2: rank 1, flux 0,
printed as best, `status: ok`.

## 3. P0-C — multi-target: unevaluable rows hold no rank

`rank_multi_target` assigns contiguous ranks 1..N to evaluable rows and `rank = 0` ("no rank") to
the rest; `search_model_pool_multi` splits them into `ranks` / `unevaluated`, and the writer keeps
the unevaluable rows out of `search_rankings.csv` and `top_ranked` entirely.

**Verified — R2-B B2 / R2-A E1 repro** (`--target-preset scfa --multi-metric carbon_equivalent`):
`top_ranked` is now `[(1, iHN637+iYO844), (2, iAF987+iHN637+iYO844), (3, iAF987+iHN637)]` — all
`optimal` — and `iAF987+iYO844 (infeasible)` sits in `unevaluated` with no rank. Round-2 gave it
rank 2 or 3 inside `top_ranked` while the warning claimed it was "excluded from ranking".

Two round-2 side findings fixed in the same pass, both now firing in that run's output:
* **R2-A D7** — the linear joint objective collapses SCFA composition to one acid. A warning now
  names it: *"the joint objective is linear, so its optimum is a vertex: targets reported as
  exactly 0 alongside positive ones may be a vertex-selection artifact…"*
* **R2-C F10** — `pareto=false` meant "not computed" for ≠2 targets with nothing saying so:
  *"pareto was NOT computed (6 targets…); pareto=false means 'not evaluated', not 'dominated'"*.
* **R2-B B3** — the all-zero warning denied an observed non-zero flux when a normalized score was
  zero only because the candidate set had zero score range. The normalized wording now names the
  real cause and explicitly declines to deny the flux.

## 4. P0-D — worst-status semantics

* `strain-growth`: `status` derives from `_worst_status(community, single-leg tier, controlled?)`.
  **Verified** — all single legs failing now yields `status: failed` with
  `community_status: optimal` preserved separately; one failing leg yields `degraded`. Round-2
  (R2-A D3 / R2-B B5) reported `status: "optimal"` with all three legs failed. Note `optimal` is
  gone from the run-status vocabulary entirely — R2-C F11 flagged it as outside
  `_STATUS_SEVERITY`, so gates written against that vocabulary mis-handled it.
* `abundance-impact`: replaced `"ok" if any(row optimal)` with worst-row derivation, and added the
  `warnings` key the summary had never had. **Verified** — `status: degraded` (was `ok`), and the
  pFBA-mixing warning R2-C F5 asked for now fires with real counts:
  *"3 of 4 sweep points fell back to a non-parsimonious (FBA) flux distribution while the rest are
  pFBA; the exchange-flux curve mixes two flux-selection rules and the points are not
  like-for-like"*.

## 5. P1-E — the S3 capability: `cmig host-ko-impact`

New `cmig/core/host_ko_impact.py` + `_cmd_host_ko_impact`. Baseline and every knockout arm go
through the **same** `run_bigg_host_microbe` call with identical medium, interface map, biomass
basis, host objective, solver, tradeoff and abundances; only the named member's SBML is swapped, and
only for a knockout of the named gene/reaction. That invariance is recorded in the artifact under
`comparability.shared_across_arms`. A delta is emitted **only when both arms solved optimally** — an
infeasible perturbed host yields a null delta, never `-baseline`, because "the host died" and "the
host objective fell to zero" are different findings.

**Verified end-to-end** against R2-B's ethanol-dependent synthetic host (their S3.3 fixture):

```
uv run cmig host-ko-impact --host <synthetic_host_etoh.xml> --model-dir <iHN637> \
  --member iHN637 --ko-level reaction --reactions ETOHt,ACKr,PTAr --target etoh \
  --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation \
  --biomass-basis-source "..." --host-medium ... --interface-map ... --exchange-suffix _lumen
```

```
baseline: host_objective=9.21243 host_status=optimal target_transfer=3.40414
iHN637:ETOHt: delta_host_objective=-0.600731 (-6.52%)  delta_target_transfer=-3.40414
iHN637:ACKr:  delta_host_objective=+0.736723 (+8.00%)  delta_target_transfer=+0.245574
iHN637:PTAr:  delta_host_objective=+10.7901 (+117.13%) delta_target_transfer=+3.59669
warning: biomass basis is validation-only; this comparison is not publication-ready
```

Two independent cross-checks that this reproduces what R2-B got by hand:
* baseline `host_objective 9.21243` and `target_transfer 3.40414` match their S3.3 values
  (9.2124325907 / 3.4041441969) exactly;
* the `ETOHt` KO's `delta_microbe_to_host` is `{etoh: −3.4041, ac: +4.8059}` — their manual-bridge
  run S3.7 observed the same rerouting to *"acetate 4.8058506308"*.

The null-delta path is also verified: against the plain synthetic host (baseline infeasible) the
run reports `status: failed`, `delta_host_objective: null`, `comparable: false`, and
*"the baseline host solve was not optimal…; no knockout delta is defined against it"* — instead of
manufacturing a number.

Artifacts: `host_ko_impact.csv` (baseline as its own first row) + `host_ko_impact_summary.json`.
Registered in `cmig workflows` (`Host / Knockout Impact`) and in `inspect-run`
(`kind: host_ko_impact`, verified).

## 6. P1-F — figures

| Item | Before (round-2 measured) | After (measured) |
|---|---|---|
| `--journal-preset` applied | stored in the sidecar, **ignored** — sidecar said `nature`, geometry stayed 6.0×4.0in @600dpi | `nature` → spec `3.5×3.0in @300dpi`, **PDF MediaBox `252×216pt` = 3.5×3.0in** |
| unknown preset | accepted, exit 0, recorded verbatim | **exit 2**, `unsupported journal preset: totally_made_up (supported: [...])` |
| TIFF mode | RGBA | **RGB** (alpha flattened onto white) |
| TIFF compression | tag 259 = 1 (raw) | **tag 259 = 5 (LZW)** |
| TIFF resolution | 300 dpi | **600 dpi** |
| TIFF size | 13.67 MB / 21.25 MB | **0.46 MB / 0.73 MB** (~25× smaller) |
| circle/bubble legend | **none** — colour and size channels undecodable | edge-kind colour key + bubble/arrow size key with units |
| panel letters | none anywhere | **A/B/C** on abundance-impact and dFBA (verified in the SVG) |
| palette | ColorBrewer mix; worst pair ΔE(deutan) = 4.7 | **Okabe-Ito**; every pair > ΔE 20 (asserted in tests) |
| font | `font.family: "Arial"` only; R aborted on unknown family, matplotlib silently used DejaVu | stack `["Arial","Helvetica","DejaVu Sans"]`, declared in the SVG |
| SVG text | matplotlib outlined every glyph to `<path>` | `svg.fonttype: "none"` → text stays text |
| axis units | none on any axis | 14 axis/colourbar labels now carry units |

I also fixed R2-C **F8** in the same figure: the hand-written `search_plot.svg` hardcoded
*"Target production search"* and *"larger is better for max secretion"* regardless of
`--direction`, so an uptake search rendered its strongest **consumers** under a "production"
heading. **Verified** with `--direction max_uptake`: the title is now `Target uptake search: ac`
and the caption `Target exchange flux, EX_ac_m (mmol gDW⁻¹ h⁻¹); bar length = |flux|,
objective = max_uptake`.

One regression I introduced and then fixed: placing the new legend below the axes collided with the
rotated category tick labels. I rendered the figure, saw the overlap, and moved the legend outside
the axes on the right with reserved width. Re-rendered and re-inspected — clean.

## 7. Tests

| File | Tests | Covers |
|---|---|---|
| `tests/test_medium_namespace_bridge.py` | 20 | P0-A: `_m`↔`_e` translation, opening a closed exchange, exact vs merge, measured equality, exemptions |
| `tests/test_search_unevaluable_partition.py` | 12 | P0-B/P0-C: evaluability predicate, `--top-k`-proof warnings, rank 0, contiguous ranks, B3 wording |
| `tests/test_host_ko_impact.py` | 17 | P1-E: delta arithmetic, null delta on either arm failing, metabolite rerouting, status tiers, guardrails |
| `tests/test_strain_growth_medium_basis.py` | 9 (rewritten) | P0-A/P0-D at CLI level with **real cobra member models** — the round-1 version's thin fake is what let the bug through |
| `tests/test_figure_publication_export.py` | 26 | P1-F: preset applied + rejected, TIFF 600/RGB/LZW, Okabe-Ito ΔE, font stack, units, panel letters |

**Three pre-existing tests updated** because a fix deliberately changed their contract:
* `test_cli_solve.py::test_strain_growth_cli_writes_member_growth_report` — asserted
  `status == "optimal"`; now asserts the run-status tier plus `community_status == "optimal"`.
* `test_search_advanced.py::test_rank_multi_target_weighted_normalized_and_pareto` — asserted ranks
  `[1,2,3,4]`; now `[1,2,3,0]`, which is the P0-C requirement.
* `test_cli_solve_medium.py::test_unknown_medium_exchange_is_strict_by_default` — asserted the word
  "community" in a message that is now English and generic (the primitive serves both community and
  single models); asserts the offending exchange id instead.

I also had to fix two `.ranks[0]` call sites in `gene-ko-search` that P0-B would otherwise have
turned into an `IndexError`: a KO leaving no evaluable consortium now reports `evaluation_status:
failed` rather than crashing, and an unevaluable **baseline** raises with an actionable message
instead of silently producing deltas against nothing.

## 8. Beyond the assigned list (small, same failure class)

* **R2-C F4** — `abundance-impact`'s `target_influence_share` mixed bases: micom `member_exchange`
  is per-**taxon** flux, so the community-level contribution needs the abundance weight, and
  `abs()` credited *consumers* as contributors. Now an abundance-weighted **secretion** share.
  Verified: 1.000 at abundances 0.25/0.50/0.75 where iHN637 is the sole acetate secretor, replacing
  the inverted 0.75 → 0.50 → 0.25 trend that R2-C showed was an artifact of the missing weight.
* **R2-A D13** — Korean strings in three user-facing diagnostics that land in CSV/JSON artifacts are
  now English.

## 9. Deliberately deferred

* **R2-A D4/D5/D6** — no FVA intervals on abundance sweeps or cross-feeding edges, and no
  direction-non-identifiability flag when an FVA interval straddles zero. I added the *warnings*
  (the sweep now says the flux is one LP vertex) but not the interval plumbing, which needs an
  `EDGES_SCHEMA` change and a targeted FVA pass per sweep point.
* **R2-A D9 / R2-C F10** — the multi-target path still writes no figures and no
  `pool_diagnostics.csv`, so `cmig search` does not meet its own documented `key_outputs` on that
  path.
* **R2-C F6** — the science commands still emit no `manifest.json` / `run_hash`, so a published
  `search` result cannot be re-derived from its own directory. This is the largest remaining
  reproducibility gap.
* **R2-C F9 / F12, R2-A D10** — figures are still written from a failed host solve with no failure
  annotation; `--biomass-basis-kind measured` still accepts a contradictory source string; a
  `status: failed` run still exits 0.
* **R2-A D11/D12, R2-B B7/B8** — multi-target has no heuristic strategy above 100 candidates and
  rebuilds each community twice; `gene-ko-search` still ranks by absolute post-KO score (so rank 1
  can be a zero-effect KO) and never calls `_ranking_degeneracy_warnings`.
* **R2-A P2-4** — `strain_growth_plot` still draws a failed leg as a zero-height bar rather than
  marking it missing.
* **dFBA / spatial-preview numerics** — untouched and unverified by me this round; I only changed
  their figure export path.
