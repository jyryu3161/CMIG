# CMIG Round-1 Cross-Review — Claude Opus 5 (A) × Codex gpt-5.6-sol (B)

Coordinator synthesis. Two evaluators tested the same three scenarios
independently, without reading each other's report. This document records where
they **converged**, where they **diverged**, what only one caught, and which
claims the coordinator **independently reproduced**.

Source reports: `REVIEW/report_opusA.md` (43.6 KB), `REVIEW/report_codexB.md` (39.0 KB).

## 0. Methodological caveat (important)

Evaluator B ran partly against a **concurrently mutating worktree**: the
phase-2 fixes were being implemented by evaluator A while B was still testing.
B detected this itself, recorded source SHA-256 hashes for its decisive runs,
re-ran the decisive S1/S3 workflows after changes stopped, and correctly
discarded one transient `NameError: _resolve_run_status is not defined` as
non-reproducible. Consequence: **B's S1 numbers describe the *fixed* code, not
the baseline.** That accidentally produced useful independent validation of the
new `--target-preset scfa` / `--multi-metric carbon_equivalent` surface, but it
means A and B were not always testing the same tree. This was a coordinator
sequencing error, not an evaluator error.

## 1. Scenario verdicts

| Scenario | A (Opus 5) | B (Codex gpt-5.6-sol) | Agreed? |
|---|---|---|---|
| S1 — best SCFA-producing combination | PARTIAL | PARTIAL | ✅ |
| S2 — microbe–microbe interaction | SUPPORTED (+ one P0 crash) | PARTIAL | ⚠️ differ in degree |
| S3 — host–microbe + perturbation → host effect | PARTIAL | PARTIAL | ✅ |
| Figures publication-ready? | **No** | **No** | ✅ |

**The S2 divergence is a difference of threshold, not of fact.** Both observed
the same thing: cross-feeding edges are `proportional_shared_pool` allocations
from a shared pool, i.e. *inferred*, not identified transfers, and that
provenance is not written into `edges.parquet` or the manifest. A treated the
workflow as working-and-caveated (SUPPORTED) and filed the provenance gap as a
P2; B treated "a reviewer could mistake inferred edges for measured causal
links" as disqualifying (PARTIAL). B's stricter reading is the safer one for a
publication tool, and it is the one worth adopting.

## 2. Independently converged findings (both, unprompted)

These carry the most weight — two different models, separate sessions, same
quantitative conclusion:

| Finding | A | B |
|---|---|---|
| `--journal-preset` accepted, recorded in provenance, **never applied**; invalid preset names accepted silently | B2 | D2 |
| Figures carry **no axis units** anywhere, though the summaries know `flux_unit` | FAIL 0/10 | FAIL |
| **No panel letters** (A/B/C) anywhere; `composer.py` `PanelSpec` has zero callers | FAIL | FAIL |
| Palette is **not Okabe-Ito**; multiple inconsistent palettes across renderers | FAIL (ΔE76 7.9 vs 18.3) | PARTIAL/FAIL |
| Automatic TIFFs are **300 dpi, RGBA, uncompressed**; only the R `render-figure` path gives 600 dpi RGB LZW | PARTIAL | PARTIAL |
| Circle/bubble network figures have **no legend** for their encodings | FAIL | PARTIAL/FAIL |
| R renderer fails on hardcoded `Arial` → silent fallback to matplotlib | FAIL | PARTIAL |
| Multi-target search **excludes a real producer** over one missing/infeasible target | B3 | D1 |
| Exact ties presented as an ordered winner, no degeneracy flag | B4 | D3 |
| Cross-feeding edges omit allocation method / identifiability | B15 | D6 |
| **No composed KO → host-effect workflow**; user must bridge two workflows by hand | B19 | D7 |
| No human GEM ships; all host numbers are surrogate/toy and CMIG says so honestly | §6.1 | §1 |

Both also independently confirmed the same *positive*: the run-provenance
sidecars (`figure_spec.json`, `render_provenance.json` with script and input
SHA-256) are better than typical published pipelines, and the `viridis` heatmap
is genuinely CVD-safe.

## 3. Caught only by A (Opus 5)

- **P0 crash (B1).** `cmig strain-growth` on the legitimate pair
  iHN637+iYO844 died with a raw `gurobipy GurobiError: Unable to retrieve
  attribute 'X'`, exit 1, no diagnostic. A root-caused it precisely: MICOM's
  **pFBA second stage** leaves the Gurobi model unsolved, and
  `engine.py:128` calls `cooperative_tradeoff(..., pfba=True)` unguarded. A
  isolated it to three lines showing `pfba=False` succeeds where `pfba=True`
  fails. Blast radius: `solve`, `strain-growth`, `abundance-impact`,
  `host-microbe-bigg`, `host-search-bigg`, `sweep`.
  **Coordinator independently reproduced this** (exit 1, same traceback).
- **Silent-corruption variant.** The same failure inside `host-search-bigg` is
  caught per candidate and written as `score=0`, so an unsolvable consortium is
  **ranked last as if the host objective were genuinely zero**, run exits 0,
  `status: ok`, no warning.
- **B9 — `n_biomass` counts objective *terms*, not biomass reactions.** iAF987's
  active objective is a **283-term** linear combination, so its reported
  "growth" (0.0473) is an arbitrary objective value plotted under the label
  `Growth rate`. This one is easy to miss and quietly poisons S2 conclusions.
- **B5 — `strain-growth` compares the two legs under different media** (the
  single-model leg never receives `medium_spec`), so the headline
  "all strains grow better in community" is confounded.
- **B12 — KO screen's "best" is the *weakest* knockout** (ranked by remaining
  flux, so `PTA2` Δ−0.076 outranks `ACKr` Δ−0.665).
- **B13 — ~7× redundant work** in multi-target search (μ* recomputed per target).

## 4. Caught only by B (Codex gpt-5.6-sol)

- **D5 — dFBA grows without consuming the managed substrate.** Biomass rose
  0.05 → 0.0623 and acetate 0 → 0.508 while managed glucose stayed *exactly*
  10.0, and the sensitivity endpoint was independent of Km. Growth is being
  supported by unconstrained default-medium substrates, so the tracked
  glucose/Km experiment is not interpretable. This is a genuine
  scientific-validity trap A did not reach.
- **D4 — analysis failure returns process exit 0.** Host LP infeasible,
  top-level status `failed`, host objective 0 — and the command still exits 0
  and prints "coupling complete". Breaks any CI/automation gate.
- **SVG text is outlined to paths** (`ArialMT-*` glyph paths) in most matplotlib
  SVGs — zero `<text>` elements, so labels are not editable or accessible.
- **Mislabelled profile figure:** a figure titled "SCFA exchange profile" actually
  plots the full external profile including h, h2o, co2, o2, glucose, ammonium
  and phosphate.
- **Working demonstration of the S3 gap.** B manually bridged KO → host: applied
  the `AC2BUT` knockout to a scratch GEM, re-ran coupling, and measured host
  objective **30.25 → 19.0 (Δ = −11.25)** with coupling switching from butyrate
  6.25 to acetate 10.0. That proves the capability is *reachable* and only the
  composed workflow is missing — a more actionable framing than "not supported".

## 5. Coordinator-verified claims

Reproduced first-hand, not taken on trust:

- ✅ **P0 crash** — reproduced exactly (exit 1, `GurobiError`).
- ✅ **After the fix** — same command now exits 0 with
  `warning: pfba_stage_failed; reporting non-parsimonious flux distribution`.
- ✅ `cmig search --targets scfa` was rejected pre-fix (`--targets needs >= 2
  comma-separated metabolites`) — the documented SCFA preset existed in
  `targets.py` and was accepted by `solve` but **not** by `search`.
- ✅ Rendered figure hardcodes `#D62728` / `#1F77B4` (matplotlib `tab10`
  defaults) even through the R path; `font-family` unset.
- ✅ `strain_growth_plot.tiff` = 2160×1020, **300 dpi, RGBA, compression=raw,
  8.8 MB**.
- ✅ Three distinct palettes across `render/client.py`, `interaction_figures.py`
  and the strain-growth writer.
- ✅ Rich multi-panel figures (circle/heatmap/bubble/contribution) are produced
  **only** by `host-microbe-bigg`; S1 and S2 never get them.
- ✅ `gene-ko-search` has no host awareness at all (no `host` reference in
  `search_advanced.py`).
- ⚠️ **Coordinator self-correction:** I initially inferred from
  `s1_multi_scfa_small` that the excluded candidate `iAF987+iHN637` was the
  *better* SCFA producer (summing its per-target fluxes to 14.4 vs the winner's
  7.08). That was **wrong** — those are per-target *capability probes*, each
  maximised independently, and are not additive. Re-running the joint LP without
  `succ` gave `iAF987+iHN637` = 3.41 vs winner 7.19, confirming the rank order
  was correct. The real defect is narrower and still valid: a single missing
  exchange **silently removes** an otherwise-valid candidate from the ranking.

## 6. Merged priority list

Ranked by scientific damage, merging both reports:

**P0 — done in phase 2**
1. Guard the MICOM delegate so solver failure degrades gracefully (A-B1). ✅ implemented + verified
2. Unevaluable candidates must not sit in a ranking as zeros (A-B1 variant). ✅ implemented
3. Top-level `status` must reflect the worst sub-status (A-B6). ✅ implemented

**P1 — partly done**
4. Multi-target: missing exchange contributes 0, not disqualification (A-B3 / B-D1). ✅ implemented, but B still saw one candidate excluded as *infeasible* — the secretion-domain constraint in `search.py::joint_target_solve` is a second, distinct exclusion path that remains open.
5. Physically meaningful total-SCFA metric + wire the `scfa` preset into `search` (A-P1-4). ✅ implemented (`--target-preset scfa`, `--multi-metric carbon_equivalent`, score in mmol C gDW⁻¹ h⁻¹)
6. Tie / all-zero ranking warnings (A-B4 / B-D3). ✅ implemented for product search; **`search-fixture` still bypasses it** (B-D3).
7. `strain-growth` same medium on both legs (A-B5). ✅ implemented
8. **Still open:** `--journal-preset` must be applied and validated (A-B2 / B-D2).
9. **Still open:** figure fundamentals — axis units, panel letters, legends on circle/bubble, Okabe-Ito palette, 600 dpi RGB LZW TIFF, font fallback stack, one implementation per figure.
10. **Still open:** `run_hash` / `status` for every workflow, not just `solve` (A-B7) — B confirmed `run_hash=null` post-fix.
11. **Still open:** split reviewed vs unreviewed entries in the host interface map; D↔L stereoisomer swaps currently ship as defaults (A-B8).
12. **Still open:** compose KO → host effect into one supported workflow (A-B19 / B-D7). B has already demonstrated the manual bridge and the expected output.

**P2 — all still open**
13. Report objective structure, not "biomass" (A-B9) — iAF987's 283-term objective.
14. dFBA must not grow on untracked substrates without a warning (B-D5).
15. Non-zero process exit when the science failed (B-D4).
16. Edge identifiability (`weight_lo`/`weight_hi`, allocation method) in the schema (A-B15 / B-D6).
17. `abundance-impact` self-auditing: degeneracy warning, `--fva` (A-B11).
18. KO ranking direction `--rank-by {remaining,effect}` (A-B12).
19. Hoist μ* — recover the ~7× multi-target cost (A-B13).

## 7. Bottom line

All three scenarios are **real and reachable**, none is **fully
publication-defensible through a single supported workflow** in the tested
state. S2 is the strongest (biologically coherent cross-feeding: *B. subtilis* →
*Geobacter* acetate 3.43, reciprocal branched-chain amino acids). S1's ranking
is now physically meaningful for the first time (carbon-equivalent, mmol C
gDW⁻¹ h⁻¹) but still has one live exclusion path. S3 has the widest gap: the
KO → host-effect join does not exist as a command, and no human GEM ships, so
every host number today is a surrogate — which CMIG, to its credit, labels
honestly rather than hiding.

The figures are competent, reproducible QC plots with unusually good provenance,
and are **not** submission-ready. Both evaluators independently costed the fix
at roughly a day of focused work across two files.
