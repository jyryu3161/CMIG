# CMIG Round-2 Independent Re-Evaluation — Evaluator R2-A

**Evaluator:** R2-A (Claude Opus 5, fresh context, independent)
**Date:** 2026-07-25
**Worktree:** `/Users/jaeyongryu/orca/CMIG` @ `d3e90d7` + uncommitted round-1 fixes
**Environment:** cobra 0.31.1, micom 0.39.0, gurobipy 12.0.3 (academic, exp. 2027-05-27),
Python 3.12.11, darwin/arm64. Binary used: `./.venv/bin/cmig`.
**Model pool:** `iHN637` (785 rxn), `iYO844` (1250), `iAF987` (1285); `iML1515` (2712) as a
stand-in "host". No Recon3D / Human-GEM is present in this worktree (see §6).
**Scratch:** `REVIEW/scratch_r2opus/` · **Runs:** `runs/r2opus/`

Every number below was read out of an artifact produced by a command I ran in this session.
Nothing is inferred from source alone unless explicitly marked **[code-read, not run]**.

---

## 1. Verdict table

| | Scenario | Verdict | Ran end-to-end? | Core evidence | Blocking gap |
|---|---|---|---|---|---|
| **S1** | Which microbial combination best produces SCFAs | **PARTIAL** | Yes — `search --target-preset scfa --multi-metric carbon_equivalent` completed (4:25.7, exit 0) | `runs/r2opus/s1_scfa_carbon/` — ranked 3/4 candidates, best `iHN637+iYO844` = **24.224 mmol C gDW⁻¹ h⁻¹**, carbon weights read from model formulas (ac=2, but=4, ppa=3, succ=4), `status: degraded`, exclusions warned | The joint LP is **linear**, so every ranked row collapses to acetate-only (`but=lac=ppa=succ=0`) with no warning; a candidate that demonstrably makes lac__L/ppa/succ is dropped entirely because *one* target LP was infeasible; the multi-target path emits **no figure and no `pool_diagnostics.csv`** although `cmig workflows` advertises them |
| **S2** | Microbe–microbe interaction (cross-feeding, alone-vs-community, sweeps, dFBA) | **NOT SUPPORTED** as a controlled comparison; PARTIAL as a descriptive readout | Yes — `strain-growth`, `solve --fva`, `abundance-impact` all completed exit 0 | `strain-growth` claims `single_medium_equals_community_medium: true` on the default path, but the community medium is measurably **more permissive than every member's own medium** (iYO844: +20 metabolites, nh4/pi/so4 5.0 → 999999). My control leg **inverts the sign** of the conclusion for iYO844 | The alone-vs-community difference is confounded by medium, and the one supported fix (`--medium`) is broken by an `_m` vs `_e` namespace mismatch. Cross-feeding edges carry no identifiability marker. FVA shows the acetate direction is not even sign-identifiable (interval −8.88 … +7.14 around a point estimate of −0.99 labelled "uptake") |
| **S3** | Host–microbe coupling + microbial perturbation → host effect | **PARTIAL** — supported at the *member* level, **NOT SUPPORTED** at the *gene* level | Yes — `host-microbe-bigg`, `host-search-bigg`, `gene-ko-search` all completed exit 0 | `runs/r2opus/s3_host_wd/`: ac transfer **7.0165 mmol gDW_host⁻¹ h⁻¹**, host objective **1.04856**, member split flagged `identifiable=false`. `host-search-bigg`: dropping iHN637 moves host objective 1.04856 → 0.87700 (−16.4 %) and ac transfer 7.0165 → 0. `gene-ko-search`: best of 25 KOs = **+0.0247 %** on acetate, 9/15 rows exactly 0 | **"Suppress gene X → host objective changes by Y" is not composable.** `gene-ko-search` ranks KOs by *target exchange flux only* and stops there; `host-microbe-bigg` accepts no `--bounds`/KO input, so the two halves cannot be joined. Default settings also produce a *vacuous* coupling (`matched_exchanges: {}`) while still reporting `status: "ok"` and a headline host objective |

### Recent-fix scorecard

| Claimed fix | Verdict | Evidence |
|---|---|---|
| Solver failure degrades gracefully, no raw traceback | **HOLDS** | Direct probe: engine returns `status=solver_failed`, `flux_normalization_method=none`, structured JSON diagnostic listing both the pFBA failure and the non-pFBA retry failure. No exception escaped. Real runs also surfaced `pfba_stage_failed; reporting non-parsimonious flux distribution` (3 host runs) |
| Unevaluable candidates not ranked as zeros | **HOLDS** | `s1_scfa_carbon/search_rankings.csv` rank 4 `iAF987+iYO844`: `weighted_score` **empty** (−inf, not 0), `status=infeasible`, diagnostic present, named in `warnings` |
| Top-level `status` reflects worst sub-status | **PARTIAL** | Holds for `search` multi-target (`degraded`), `host-microbe-bigg` (`failed`), `host-search-bigg` (`degraded`). **Fails for `strain-growth`**: all 3 single-model legs `failed`, yet `status: "optimal"` and `inspect-run` echoes `"status": "optimal"` |
| `strain-growth` uses the same medium for both legs | **DOES NOT HOLD** | Default path asserts `single_medium_equals_community_medium: true` — measurably false. `--medium` path with `--allow-unknown-medium` also asserts `true` while the medium was applied to *neither* single model (`single_growth` byte-identical to the no-medium run) |

Additional zero-ranking guard **holds**: `search --target but` printed
`no candidate achieved a non-zero target flux; the ranking order is arbitrary and rank 1 must
not be reported as the best producer`.

---

## 2. Evidence log

All commands run from `/Users/jaeyongryu/orca/CMIG`. `$C = ./.venv/bin/cmig`,
`$M3 = REVIEW/scratch_r2opus/models3` (iHN637, iYO844, iAF987),
`$M2 = REVIEW/scratch_r2opus/models2` (iHN637, iYO844).

| # | Command | Exit | Wall | Key numbers | Artifact |
|---|---|---|---|---|---|
| E1 | `$C search --model-dir $M3 --target-preset scfa --multi-metric carbon_equivalent --min-size 2 --max-size 3 --top-k 10 --out runs/r2opus/s1_scfa_carbon` | 0 | **4:25.7** | 4/4 evaluated, 3 ranked; best `iHN637+iYO844` score **24.2239** mmol C gDW⁻¹ h⁻¹, `ac=12.1120`, all other SCFA = 0; weights `{ac:2, but:4, lac__D:3, lac__L:3, ppa:3, succ:4}`; `status: degraded` | `runs/r2opus/s1_scfa_carbon/` |
| E2 | `$C search --model-dir $M3 --target but --min-size 2 --max-size 3 --top-k 10 --out runs/r2opus/s1_single_but` | 0 | 57.6 s | best flux **0**, growth 0.15393; all-zero warning fired; 9 artifacts incl. SVG+TIFF | `runs/r2opus/s1_single_but/` |
| E3 | `$C search --taxonomy tax10.csv --target-preset scfa --multi-metric raw_sum --min-size 2 --max-size 3 --out …` | 2 | <1 s | `165 candidates > exhaustive_max=100; narrow --min-size/--max-size (multi-target search is exhaustive-only, no silent truncation)` | stderr |
| E4 | `$C strain-growth --model-dir $M3 --out runs/r2opus/s2_strain_growth` | 0 | 21.9 s | iAF987 0.047322 → 0.037169; iHN637 0.224455 → **0.558854** (2.49×); iYO844 0.117966 → **0.560382** (4.75×); community 0.385468; `single_medium_equals_community_medium: true`; `warnings: []` | `runs/r2opus/s2_strain_growth/` |
| E5 | `$C strain-growth --model-dir $M3 --medium medium_presets/western_diet.csv --allow-unknown-medium --out runs/r2opus/s2_strain_growth_medium` | 0 | 20.0 s | `single_growth` for iHN637 = **0.22445454212** — byte-identical to E4, i.e. medium not applied; per-row diagnostic `medium exchanges absent from iHN637: ['EX_glc__D_m']`; **yet** `single_medium_applied=True` and `single_medium_equals_community_medium: true` | `runs/r2opus/s2_strain_growth_medium/` |
| E6 | same as E5 without `--allow-unknown-medium` | 0 | ~20 s | all 3 single legs `single_status=failed`, `single_growth` empty; correct warning fires; `single_medium_equals_community_medium: false`; **but `status: "optimal"`** | `runs/r2opus/s2_sg_strict/` |
| E7 | `./.venv/bin/python REVIEW/scratch_r2opus/check_medium_basis.py` | 0 | ~40 s | community medium n=33. iAF987: own 26, +7 new, 1 looser. iHN637: own 22, +11 new, 17 looser. iYO844: own 13, **+20 new, 3 looser** (nh4/pi/so4 5.0 → 999999). `identical=false` for all three | `REVIEW/scratch_r2opus/medium_basis_audit.json` |
| E8 | `./.venv/bin/python REVIEW/scratch_r2opus/controlled_alone_vs_community.py` | 0 | ~50 s | **iYO844**: alone/own 0.117966, alone/**community medium 0.777337**, in community 0.560382. **iHN637**: 0.224455 / 0.299255 / 0.558854. **iAF987**: 0.047322 / 0.047322 / 0.037169 | `REVIEW/scratch_r2opus/controlled_alone_vs_community.json` |
| E9 | `$C solve --taxonomy tax3.csv --assume-bigg-namespace --tradeoff-f 0.5 --targets scfa --fva --fva-metabolites ac,but,ppa,succ,lac__L --out runs/r2opus/s2_solve3` | 0 | 47.8 s | growth 0.38547, run_hash `3392f96cf842867b…`; 96 edges incl. cross-feeding (`iHN637→iAF987 ac 0.27703`, `iYO844→iAF987 ac 3.58052`); profile `ac net_flux −0.99415` labelled **uptake** with `fva_lo −8.88`, `fva_hi +7.13511`; `but/ppa/succ/lac__L` absent from profile | `runs/r2opus/s2_solve3/` |
| E10 | `$C abundance-impact --model-dir $M3 --member iHN637 --fractions 0.1,0.25,0.5,0.75,0.9 --target ac --out runs/r2opus/s2_abundance_ac` | 0 | 1:25.0 | `target_member_exchange` = 0.8857, **0**, **22.599**, 0.7168, 0.2708; `community_target_exchange` = 0.05544, 0, **6.7459**, 0, 0; summary has **no `warnings` key**, `status: "ok"` | `runs/r2opus/s2_abundance_ac/` |
| E11 | same, `--fractions 0.45,0.48,0.5,0.52,0.55` | 0 | ~1:20 | growth 0.38998 → 0.39111 (+0.29 %) while `target_member_exchange` jumps **9.5358 → 23.8640** (2.50×) and `community_target_exchange` **0 → 7.0027** | `runs/r2opus/s2_abundance_fine/` |
| E12 | `$C host-microbe-bigg --host models/iML1515.xml --model-dir $M2 --microbial-biomass-gdw 0.5 --host-biomass-gdw 1.0 --biomass-basis-kind validation …` | **0** | 16.7 s | community 0.58486 optimal; host **infeasible**, objective 0; `matched_exchanges: {}`; `status: "failed"` (correct); `inspect-run` → failed | `runs/r2opus/s3_host_microbe/` |
| E13 | E12 + `--host-medium host_medium_iML1515.csv` | 0 | 16.5 s | host **optimal, objective 0.87700** — but `matched_exchanges: {}`, `microbe_to_host: {}`, `member_contribution.csv` header-only, community secretion = `{co2, h, h2o}` only. **`status: "ok"`** | `runs/r2opus/s3_host_microbe_fed/` |
| E14 | E13 + `--microbe-medium medium_presets/western_diet.csv` | 0 | 13.7 s | community 1.88849; microbial secretion `ac 7.01647`; **`microbe_to_host: {ac: 7.016472}`**, FVA range `[7.016472, 7.016472]`; host objective **1.048556**; member split iHN637 0.40858 / iYO844 0.59142, `identifiable=false`, `attribution_method=abundance_weighted_proportional_allocation` | `runs/r2opus/s3_host_wd/` |
| E15 | `$C host-search-bigg --host models/iML1515.xml --model-dir $M3 --min-size 2 --max-size 2 --target ac --metric target_transfer …` | 0 | 34.2 s | 2/3 ranked, `status: degraded`; #1 `iHN637+iYO844` transfer **7.01647**, host obj **1.04856**; #2 `iAF987+iYO844` transfer **0**, host obj **0.87700**; #3 `iAF987+iHN637` unevaluated (`medium exchange 가 community 에 없음: ['EX_glc__D_m']`) | `runs/r2opus/s3_host_search/` |
| E16 | Direct probe of `MicomEngine.cooperative_tradeoff` with an always-raising community | n/a | <1 s | No exception. `status=solver_failed`, `flux_normalization_method=none`, retry order `[pfba=True, pfba=False]`, structured diagnostic with both causes | inline |
| E17 | `python -m pytest tests/test_engine_solver_guard.py tests/test_run_status_reporting.py tests/test_search_multi_target_metrics.py tests/test_strain_growth_medium_basis.py -q` | 0 | ~15 s | **37 passed** | — |
| E18 | `./.venv/bin/python REVIEW/scratch_r2opus/figure_audit.py runs/r2opus` | 0 | ~30 s | 19 SVG + 19 TIFF inspected — see §3 | `REVIEW/scratch_r2opus/figure_audit.json` |
| E19 | `$C gene-ko-search --model-dir $M2 --members iHN637,iYO844 --member iHN637 --target ac --max-genes 25 --top-k 15 --out runs/r2opus/s3_ko_ac` | 0 | **3:54.0** | baseline ac flux 12.111959; best KO `CLJU_RS00585` `score_delta = +0.002993` (**+0.0247 %**); ranks 3/4/5 tied at 0.000212294308952; **9 of the 15 top-ranked rows have `score_delta` exactly 0**; truncation warning `evaluated 25 of 637 genes (selection=id)` fires; `status: "ok"` | `runs/r2opus/s3_ko_ac/` |

---

## 3. Figure assessment

I inspected the produced files directly: SVG XML parsed for `<text>` / `<path>` / `<image>` /
font declarations / hex colours; TIFF headers read with PIL (`tag_v2`); palettes scored with
CIE76 ΔE under normal vision and simulated protanopia / deuteranopia / tritanopia
(Vienot-style LMS projection). Two figures were additionally rendered and viewed.

| Criterion | Target (Nature Genetics / Claude Science) | Observed | Verdict |
|---|---|---|---|
| **Vector output** | true vector, no rasterised panels | 19/19 SVGs produced. **But** `interaction_heatmap.svg` contains an `<image>` tag — the heatmap body is an embedded raster inside the "vector" file | ⚠️ partial |
| **Editable text** | text as `<text>`, fonts embedded/declared | **Two backends disagree.** Hand-written SVG writers (`search_plot`, `search_scatter`, `interaction_*`, `member_contribution`): 8–27 `<text>` elements, `font-family: Arial`, sizes 10/11/14 pt — good. **matplotlib writers** (`strain_growth_plot`, `abundance_impact_plot`): **0 `<text>` elements, 59–84 `<path>`, no font declaration at all** — all text outlined to curves (`svg.fonttype` left at `path`) | ❌ fail for matplotlib figures |
| **Raster resolution** | 300–600 dpi | **300 dpi exactly**, on all 19 TIFFs (tags 282/283 = 300.0). Acceptable minimum; 600 dpi is preferred for line art and combination figures | ⚠️ marginal |
| **Raster compression / mode** | LZW or ZIP; no alpha; RGB or CMYK | **All 19 TIFFs: compression tag 259 = 1 (`none/raw`), mode RGBA (alpha channel present), photometric = RGB.** File sizes **8.81 – 21.25 MB each**; `runs/r2opus/s3_host_microbe/` alone = ~115 MB of TIFF for one run. Uncompressed RGBA TIFF is a routine submission-portal rejection | ❌ fail |
| **Colourblind-safe palette** | Okabe-Ito or equivalent; distinguishable under CVD | **Not Okabe-Ito** — ColorBrewer-derived (`#2b8cbe`, `#31a354`, `#756bb1`, `#d95f0e`, `#636363`, `#2ca25f`, `#3182bd`, `#e6550d`, `#9aa0a6`). Best pair: `#2b8cbe`/`#31a354` min ΔE under CVD = **69.3** (excellent). **Worst pair: `#2b8cbe` vs `#756bb1` — ΔE(deuteranopia) = 4.7**, ΔE(protanopia) = 12.3 (normal-vision ΔE = 31.7). Both appear in `abundance_impact_plot` (different panels, which mitigates but does not fix it). `#e6550d` vs `#2ca25f` in `interaction_circle`/`interaction_bubble`: **ΔE(protanopia) = 22.7** — legible but not comfortable | ❌ fail (one pair below the ~10 ΔE legibility floor) |
| **Typography** | consistent, ≥5–7 pt at final size, one family | Arial declared at 10/11/14 pt in the hand-written SVGs; matplotlib figures set `font.family: Arial` but macOS has no Arial for matplotlib, so the outlined glyphs are a **silent DejaVu Sans fallback** — the two backends do not match | ⚠️ fail (inconsistent) |
| **Multi-panel + panel letters** | A/B/C on composite figures | **Zero panel letters anywhere.** `abundance_impact_plot` is a genuine 3-panel figure (`plt.subplots(3, 1, …)`), `dfba_timecourse` is 3-panel **[code-read]** — neither labels its panels. Every other output is a standalone single-axes file, so no composite figure exists to assemble | ❌ fail |
| **Axis labels with units** | quantity + unit on every axis | **No axis carries a unit.** Observed strings: `"Target exchange flux (EX_but_m), larger is better for max secretion"`, `"Community growth under target objective"`, `"Growth rate"`, `"Growth"`, `"Exchange flux"`, `"Target share"`, `"Transfer flux"`, colourbar `"Flux"`. The summaries *do* carry the units (`mmol gDW_host^-1 h^-1`, `mmol C gDW^-1 h^-1`, `h^-1`) — they simply never reach the figure | ❌ fail |
| **Informative legend** | series identified, missing data distinguishable | Legends name series correctly. **But** `_write_strain_growth_figures` maps a failed leg to `_optional_float(...) or 0.0`. In `runs/r2opus/s2_sg_strict/` all three single-model legs failed → the rendered figure shows a blue **"Single model"** legend entry with **no bars at all**, visually indistinguishable from "single-model growth = 0". I viewed the rendered TIFF to confirm | ❌ fail (missing data drawn as measured zero) |
| **Uncertainty shown** | intervals where the quantity is not identifiable | No figure draws an interval. `abundance_impact_plot` connects the 5 sweep points with straight lines, implying a continuous trend, while the underlying flux jumps 2.5× for a 0.29 % change in growth (E11). FVA intervals exist in `profile.parquet` but are never plotted | ❌ fail |
| **Data-ink ratio** | no chartjunk | Good: top/right spines removed, light grid at `#d9dee3`, `set_axisbelow(True)`, no 3-D, no gradients, titles left-aligned | ✅ pass |

### Publication-readiness call

**Not publication-ready. These are good screening figures, not manuscript figures.**

The layout discipline is genuinely decent — clean spines, sensible grids, left-aligned titles,
no chartjunk — and the hand-written SVG writers produce properly editable text. But four
independent blockers stand between the current output and a Nature-Genetics submission, and
three of them are one-line-to-one-function fixes:

1. **Every TIFF is uncompressed RGBA** (8.8–21.3 MB). Needs `compression="tiff_lzw"` and an RGB
   flatten.
2. **matplotlib SVG text is outlined**, so half the figure set cannot be re-typeset.
   Needs `svg.fonttype: "none"`.
3. **No axis unit reaches any figure**, although the units are already known and recorded in the
   JSON summaries.
4. **Missing data is drawn as zero** in `strain_growth_plot`, and no figure carries the
   uncertainty that the FVA machinery already computes.

Add the absent panel lettering and the one deuteranopia-failing colour pair, and the honest
overall grade is **"solid internal screening output, ~2 focused days from submission quality."**

---

## 4. Bugs and defects

Ordered by scientific severity.

### D1 — `strain-growth` asserts a medium equality that is false (default path)

* **Repro:** `./.venv/bin/cmig strain-growth --model-dir $M3 --out runs/r2opus/s2_strain_growth`
* **Observed:** `strain_growth_summary.json` → `"medium_basis": {"medium_source":
  "model_default_bounds", "medium_checksum": "micom_default_medium",
  "single_medium_equals_community_medium": true}`, `"warnings": []`.
* **Expected:** either the two legs really share a medium, or the flag is `false` and the
  "not attributable to interaction" warning fires.
* **Why it is false (E7):** the MICOM community medium has 33 entries. Against it,
  iYO844's own medium has 13 entries, is missing 20 of them (ac, btn, cd2, cl, cobalt2, cro4,
  cu, cu2, fe2, fol, fru, mn2, …), and caps nh4/pi/so4 at 5.0 where the community allows
  999999.0. iHN637 is missing 11 and looser on 17. iAF987 is missing 7 and looser on 1.
* **Consequence (E8) — the reported biology is wrong, not merely imprecise:**

  | member | alone, own medium | alone, **community medium** | in community | CMIG's story | controlled story |
  |---|---|---|---|---|---|
  | iYO844 | 0.117966 | **0.777337** | 0.560382 | **4.75× benefit** | **0.72× — a cost** |
  | iHN637 | 0.224455 | 0.299255 | 0.558854 | 2.49× benefit | 1.87× benefit |
  | iAF987 | 0.047322 | 0.047322 | 0.037169 | 0.79× cost | 0.79× cost |

  For iYO844 the medium artifact does not just inflate the effect — it **inverts its sign**.
* **Root cause:** `cmig/cli/main.py:1613`, `_cmd_strain_growth` —
  `single_medium_applied = medium_spec is None` treats "no medium was requested" as "the media
  match". MICOM's default community medium is the union of member media, so they never match.

### D2 — `strain-growth --medium` never reaches the single-model leg (`_m` vs `_e`)

* **Repro:** `./.venv/bin/cmig strain-growth --model-dir $M3 --medium medium_presets/western_diet.csv --allow-unknown-medium --out runs/r2opus/s2_strain_growth_medium`
* **Observed:** per-row `diagnostic = "medium exchanges absent from iHN637: ['EX_glc__D_m']"`,
  `single_growth = 0.22445454212` — **byte-identical to the no-medium run (E4)** — while
  `single_medium_applied = True` and `single_medium_equals_community_medium = true`.
* **Expected:** `single_medium_applied = False` and the mismatch warning, since zero medium keys
  were applied.
* **Root cause:** `cmig/cli/main.py:1616-1620` sets `single_medium_applied = True`
  unconditionally after `apply_medium_checked`, discarding the returned `unknown` set from the
  flag (it is recorded only in the free-text diagnostic). Deeper cause: the bundled presets use
  the community namespace `EX_glc__D_m`, single models use `EX_glc__D_e`, and nothing bridges
  them — so **there is currently no invocation of `strain-growth` that yields a
  medium-controlled alone-vs-community comparison.** Strict mode (E6) doesn't fix it either; it
  just kills the single leg entirely.

### D3 — `strain-growth` top-level `status` ignores failed sub-legs

* **Repro:** `./.venv/bin/cmig strain-growth --model-dir $M3 --medium medium_presets/western_diet.csv --out runs/r2opus/s2_sg_strict`
  then `./.venv/bin/cmig inspect-run --run-dir runs/r2opus/s2_sg_strict --format json`
* **Observed:** all three rows `single_status=failed`, `single_growth` empty, the invalidating
  warning present — yet `"status": "optimal"` in the summary and `"status": "optimal",
  "status_source": "summary"` from `inspect-run`.
* **Expected:** `degraded` (or `failed`), per the same `_worst_status` rule already applied in
  `_write_multi_target_outputs` (`cmig/cli/main.py:2989`) and in `host-search-bigg`.
* **Root cause:** `_write_strain_growth_outputs` writes `community_status` straight through as
  the run status.

### D4 — Abundance sweeps report non-identifiable exchange fluxes as a curve, with no warning

* **Repro:** E10 / E11 above.
* **Observed (E11):** across `--fractions 0.45,0.48,0.5,0.52,0.55`, community growth moves
  0.389976 → 0.391112 (**+0.29 %**) while `target_member_exchange` moves **9.5358 → 23.8640**
  (2.50×) and `community_target_exchange` moves **0 → 7.0027**. In E10 the coarse grid shows
  0.8857 → **0** → **22.599** → 0.7168 → 0.2708.
* **Expected:** either FVA intervals on the reported exchange, or an explicit non-uniqueness
  warning.
* **Observed instead:** `abundance_impact_summary.json` has **no `warnings` key at all** and
  reports `"status": "ok"`; `abundance_impact_plot.svg` joins the points with straight lines.
* **Diagnosis:** classic alternate-optima degeneracy — `cooperative_tradeoff` pins community
  biomass but not the exchange flux vector, so the reported acetate flux is one arbitrary LP
  vertex per abundance point. E9 confirms the same community's acetate FVA range is
  **[−8.88, +7.135]** around a −0.994 point estimate.

### D5 — Community acetate direction is not sign-identifiable but is labelled "uptake"

* **Repro:** E9.
* **Observed:** `profile.parquet` row `ac`: `net_flux = −0.994150`, `label = "uptake"`,
  `fva_lo = −8.88`, `fva_hi = +7.135111`. `target_summary.json` reports the same single
  `{"metabolite": "ac", "label": "uptake", "net_flux": −0.994…}` with **no interval**.
* **Expected:** when the FVA interval straddles zero, the label must be flagged as
  non-identifiable (the machinery to do this already exists — `host_impact` emits
  `"host transfer is not point-identifiable at the optimal objective for: [...]"`).
* **Consequence for S1:** the headline SCFA answer rests on point target-max values;
  `--robustness-fva` exists but is **off by default**.

### D6 — Cross-feeding edges carry no identifiability marker

* **Repro:** E9, then read `edges.parquet`.
* **Observed:** columns are `schema_version, source_id, target_id, metabolite, edge_type,
  weight, label`. Rows such as `iHN637 → iAF987, ac, cross_feeding, 0.277029` read as measured
  pairwise transfers.
* **Reality:** `cmig/core/interactions.py:28` defines
  `CROSS_FEEDING_ALLOCATION_METHOD = "proportional_shared_pool"`, and
  `allocate_cross_feeding` explicitly documents that "a steady-state shared pool does not
  identify pairwise transfers". The internal honesty is exemplary — but
  `grep -rl "proportional_shared_pool" runs/r2opus/` returns **nothing**: the string appears in
  no artifact, not even `manifest.json`.
* **Expected:** an `attribution_method` / `identifiable` column on `edges.parquet`, matching
  what `member_contribution.csv` already does correctly for the host path.

### D7 — Multi-target search collapses the SCFA pool to a single acid, unflagged

* **Repro:** E1.
* **Observed:** all three ranked rows have `flux_but = flux_lac__D = flux_lac__L = flux_ppa =
  flux_succ = 0` and only `flux_ac > 0` (12.1120 / 7.2440 / 5.1177).
* **Cause:** `joint_target_solve` maximises `Σ wᵢ·vᵢ` — a *linear* objective. Any LP optimum
  sits at a vertex, so the solver dumps all available carbon into whichever acid has the best
  carbon-per-substrate ratio. The SCFA *composition* is therefore an artifact of vertex
  selection, not a prediction.
* **Consequence:** a user asking "which combination makes the most SCFA" is silently answered
  "which makes the most acetate", and `but = 0` is reported without any note that a
  butyrate-producing solution of near-equal total carbon may exist. No warning covers this.

### D8 — One infeasible target disqualifies a demonstrated producer

* **Repro:** E1, row 4.
* **Observed:** `iAF987+iYO844` is excluded from ranking (`status=infeasible`,
  `weighted_score` empty), yet its own capability-pass fluxes in the same CSV show
  `lac__L = 1.21013`, `ppa = 2.29268`, `succ = 2.35209` — it *is* an SCFA producer. Only the
  acetate leg was infeasible (`flux_ac = 0`, `"target LP returned no solution object
  (solver_status=infeasible)"`), almost certainly because `v_ac ≥ 0` (the max-secretion sign
  domain) is incompatible with `growth ≥ 0.5·μ*` — i.e. this consortium **must consume**
  acetate to grow.
* **Expected:** "cannot secrete metabolite X while growing" is a *result* (score 0 for that
  target), not an evaluation failure. Conflating it with a genuine solver error removes a real
  candidate from the S1 answer. The warning does name the combination, which is the difference
  between PARTIAL and NOT SUPPORTED here.

### D9 — Multi-target search emits no figure and no pool diagnostics

* **Repro:** E1 vs E2.
* **Observed:** `runs/r2opus/s1_scfa_carbon/` contains exactly
  `pool_taxonomy.csv, search_rankings.csv, search_summary.json`. The single-target run E2
  produced 9 artifacts including `search_plot.svg/.tiff`, `search_scatter.svg/.tiff`,
  `pool_diagnostics.csv`, `search_member_matrix.csv`.
* **Expected:** `cmig workflows --format json` lists `search_plot.svg`, `search_scatter.svg`,
  `pool_diagnostics.csv` under `key_outputs` for `cmig search`. The documented contract is not
  met on the very path the SCFA preset was added for.
* **Root cause:** `_write_multi_target_outputs` (`cmig/cli/main.py:2946`) never calls the figure
  writers or `diagnose_model_pool`.

### D10 — Host coupling reports `status: "ok"` with a completely empty coupling

* **Repro:** E13.
* **Observed:** stdout `community_growth=0.5849 host_objective=0.877 host_status=optimal`;
  summary `"status": "ok"`, `"matched_exchanges": {}`, `"microbe_to_host": {}`,
  `member_contribution.csv` header-only. The host objective 0.87700 comes **entirely from its
  own `--host-medium`**; not one microbial metabolite reached it.
* **Expected:** `degraded`. The warning `"no microbial secretions matched host exchange ids"` is
  present and correct, but the top-level status and the headline stdout line both read as
  success. Compare E14, where the coupling is real and the host objective is 1.048556 — the two
  runs are indistinguishable from the status field and the printed summary line.
* **Aggravating factor:** `exit code 0` even in E12 where `status` is `"failed"`. Any script
  keying on exit status will treat a failed host solve as a success.

### D11 — Multi-target SCFA search refuses realistic pool sizes; no heuristic fallback

* **Repro:** E3.
* **Observed:** 10 pool members at sizes 2–3 = 165 candidates → hard `ValueError`,
  `exhaustive_max=100`, not exposed as a CLI flag.
* **Expected/asymmetry:** single-target `search` has `--strategy {auto,exhaustive,random,ga}`
  and `--n-samples`; multi-target has none. The refusal is *honest* (better than silent
  truncation) but it means the S1 question cannot be asked of a realistic pool. Compounded by
  runtime: **4:25.7 for 4 candidates over three small GEMs** (~66 s/candidate), because each
  candidate is solved twice (capability pass then joint pass) and the MICOM community is rebuilt
  from SBML for each.

### D12 — `gene-ko-search` reports an all-but-null ranking as `status: "ok"`, with no tie guard

* **Repro:** E19.
* **Observed:** baseline acetate flux 12.111959. Top KO `CLJU_RS00585` moves it by
  **+0.002993 (+0.0247 %)**; ranks 3/4/5 are *exactly* tied at 0.000212294308952; **9 of the 15
  reported rows have `score_delta` exactly 0**. Summary reports `status: "ok"` with a single
  warning — the honest and correct truncation notice
  `iHN637: evaluated 25 of 637 genes (selection=id); raise --max-genes (0=all) for full coverage`.
* **Expected:** `search` already owns the right guard —
  `_ranking_degeneracy_warnings` (`cmig/core/search_product.py:74`) fires
  "no candidate achieved a non-zero target flux … rank 1 must not be reported as the best" and
  flags exact ties. `gene-ko-search` never calls it, so a screen where 60 % of the top-15 are
  null results and rank 1 is a 0.02 % effect presents as a clean ranked hit list.
* **Aggravating factor:** the default `--gene-selection id` slice is *positionally* biased —
  it takes the first 25 gene IDs (`CLJU_RS00085` … `CLJU_RS00895`, i.e. one locus
  neighbourhood), not a genome-spanning sample. `--gene-selection random` exists; `id` is the
  default. The warning names the selection mode, which is honest, but the default is the biased
  one.
* **Scalability:** 25 genes / 3:54 → a full 637-gene single-member screen is **~100 min**,
  because each KO rebuilds the MICOM community from SBML.

### D13 — Korean diagnostics in English-language artifacts

* **Repro:** E6, E15.
* **Observed:** `strain_growth.csv` → `medium exchange 가 community 에 없음: ['EX_glc__D_m']`;
  `host_search_summary.json` `unevaluated[0].diagnostic` → the same Korean string.
* **Expected:** user-facing artifacts destined for a supplementary table should be
  single-language. Cosmetic, but it lands in publication artifacts.

---

## 5. Prioritized proposals

### P0 — blocks a defensible scientific claim

| id | Fix | File · function |
|---|---|---|
| P0-1 | Stop asserting medium equality when no `--medium` is given. Either (a) set `single_medium_applied = False` and fire the existing mismatch warning, or (b) actually project `community.medium` onto each single model before its solve — the latter makes the comparison controlled and is ~6 lines (my E8 script is a working prototype). | `cmig/cli/main.py` · `_cmd_strain_growth` (line 1613) |
| P0-2 | Derive `single_medium_applied` from the *result* of `apply_medium_checked`: `applied = bool(spec.uptake) and not unknown`. Add a namespace bridge so `EX_x_m` presets map to `EX_x_e` on single models (or reject the preset up front with an actionable message). | `cmig/cli/main.py` · `_cmd_strain_growth` (lines 1616-1620); `cmig/core/medium_spec.py` · `apply_medium_checked` |
| P0-3 | Apply `_worst_status` in `strain-growth`: `status = _worst_status(community_status, "degraded" if any single leg failed else "ok")`. Same for `abundance-impact`. | `cmig/cli/main.py` · `_write_strain_growth_outputs` (1911), `_write_abundance_impact_outputs` |
| P0-4 | Attach FVA intervals (or an explicit non-uniqueness warning) to every reported exchange flux in `abundance-impact`; at minimum add a `warnings` key that says the flux column is one LP vertex among many. | `cmig/cli/main.py` · `_cmd_abundance_impact` |
| P0-5 | Distinguish "target cannot be secreted under the growth floor" (score 0, keep the candidate) from "solver failed" (exclude). Test the target sign-domain constraint separately from the LP status. | `cmig/core/search_product.py` · `_evaluate_members_multi`; `cmig/core/search.py` · `target_max_solve` |
| P0-6 | Emit a warning whenever a multi-target result has ≥1 target at exactly 0 while others are positive: the linear joint objective makes SCFA *composition* a vertex artifact. Consider offering a max-min (Chebyshev) or ε-constraint alternative under `--multi-metric`. | `cmig/core/search_product.py` · `_multi_target_warnings`, `joint_target_solve` |

### P1 — correctness of the reported artifact

| id | Fix | File · function |
|---|---|---|
| P1-1 | `status = "degraded"` when `matched_exchanges` is empty in a host-coupling run, and make the stdout summary line say `(no microbial metabolite reached the host)`. | `cmig/cli/main.py` · `_write_host_microbe_outputs`; `cmig/core/host_coupling.py` · `run_bigg_host_microbe` |
| P1-2 | Return a non-zero exit code when the run status is `failed`. | `cmig/cli/main.py` · `_cmd_host_microbe_bigg` and siblings |
| P1-3 | Add `attribution_method` and `identifiable` columns to `edges.parquet`, and record `CROSS_FEEDING_ALLOCATION_METHOD` in `manifest.json.components`. | `cmig/core/interactions.py` · `build_tidy`; `cmig/core/tidy.py` · `EDGES_SCHEMA`; `cmig/io/solve_output.py` · `build_run_components` |
| P1-4 | Flag a profile row whose FVA interval straddles zero as direction-non-identifiable, and propagate that into `target_summary.json`. | `cmig/core/tidy.py` · `build_tidy`; `cmig/core/targets.py` · `target_summary` |
| P1-5 | Call the figure writers and `diagnose_model_pool` from the multi-target path so `cmig search` honours its own documented `key_outputs`. | `cmig/cli/main.py` · `_write_multi_target_outputs` (2946), `_run_multi_target_search` (2854) |
| P1-6 | Give multi-target search the same `--strategy/--n-samples/--seed` surface as single-target, and cache the built community between the capability pass and the joint pass (currently rebuilt from SBML twice per candidate → ~2× wall clock). | `cmig/core/search_product.py` · `search_model_pool_multi` |
| P1-7 | Compose perturbation with host coupling: add `--bounds` / `--knockout` to `host-microbe-bigg`, or a `host-ko-search` that reports Δ(host objective) per KO. Today S3's "suppress gene X → host effect" has no supported path. | `cmig/cli/main.py` · `_cmd_host_microbe_bigg`; `cmig/core/host_coupling.py` · `run_bigg_host_microbe` |
| P1-8 | Call the existing `_ranking_degeneracy_warnings` from `gene-ko-search` so an all-zero / tied KO screen cannot present as a ranked hit list, and downgrade `status` to `degraded` when every reported `score_delta` is within solver tolerance of 0. | `cmig/cli/main.py` · `_cmd_gene_ko_search`, `_write_gene_ko_outputs`; reuse `cmig/core/search_product.py:74` |

### P2 — figure and polish

| id | Fix | File · function |
|---|---|---|
| P2-1 | `fig.savefig(out_tiff, format="tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})` and flatten RGBA→RGB. Cuts 8.8–21.3 MB files by ~10× and removes the alpha channel. | `cmig/cli/main.py` · `_save_screening_figure` (3245), `_write_search_tiff` (3739), `_write_search_scatter_tiff` (3771) |
| P2-2 | `plt.rcParams["svg.fonttype"] = "none"` so matplotlib SVG text stays editable; add a real font fallback chain (`["Arial", "Helvetica", "DejaVu Sans"]`) so the two backends agree. | `cmig/cli/main.py` · `_load_matplotlib_pyplot` (3220) |
| P2-3 | Put units on every axis — they are already in the summaries: `"Growth rate (h⁻¹)"`, `"Exchange flux (mmol gDW⁻¹ h⁻¹)"`, `"Transfer flux (mmol gDW_host⁻¹ h⁻¹)"`, `"Score (mmol C gDW⁻¹ h⁻¹)"`. | `_write_strain_growth_figures` (3374), `_write_abundance_impact_figures` (3415), `_write_search_svg`/`_write_search_tiff`, `_write_dfba_figure` (3303) |
| P2-4 | Draw missing data as missing: skip the bar and annotate `n/a (single-model solve failed)` instead of `_optional_float(...) or 0.0`. | `cmig/cli/main.py` · `_write_strain_growth_figures` (3377-3379) |
| P2-5 | Add panel letters (A/B/C) to every `plt.subplots(n>1, …)` figure. | `_write_abundance_impact_figures` (3441), `_write_dfba_figure` (3309), `_write_spatial_snapshots` (3570) |
| P2-6 | Switch to Okabe-Ito. The current worst pair `#2b8cbe`/`#756bb1` has ΔE(deuteranopia) = 4.7, below the legibility floor. Okabe-Ito `#0072B2/#E69F00/#009E73/#CC79A7/#56B4E9/#D55E00` keeps every pair well above ΔE 20 under all three simulations. | `cmig/cli/main.py` (hard-coded hex at 3344, 3386, 3392, 3450-3459); `cmig/core/interaction_figures.py:36` |
| P2-7 | English-only user-facing diagnostics. | `cmig/core/medium_spec.py` · `apply_medium_checked` |

---

## 6. What I could not test, and why

1. **A real host GEM.** No `Recon3D.xml` / Human-GEM exists in this worktree
   (`tests/test_recon3d_host.py` self-skips; `find` for `*recon*`/`*human*` returns only that
   test file). I used **`iML1515` as a stand-in host**, which exercises the BiGG `_e` coupling
   machinery correctly but is biologically meaningless. All S3 numbers are therefore
   **mechanism-valid, biology-invalid**, and I ran them with
   `--biomass-basis-kind validation` so the artifacts self-label as non-publication.
   Untested as a result: `--interface-map` against a reviewed lumen/blood map,
   `host-map`, `host-benchmark`, and whether a real host's exchange namespace matches.

2. **`dfba` / `dfba-sensitivity` / `spatial-preview`.** Deprioritised in favour of the
   controlled-comparison work in §4, which I judged higher-value per minute. dFBA figure code
   was read (`_write_dfba_figure`, `cmig/cli/main.py:3303`) and shares the same 3-panel /
   no-panel-letter / no-units / uncompressed-TIFF pattern — but I did **not run it**, so I make
   no claim about its numerics. This is a genuine gap in my S2 coverage: the brief lists dFBA
   under S2 and I did not exercise it.

3. **Whole-genome KO screening.** `gene-ko-search` *did* complete (E19, D13) but only for a
   25-gene slice of iHN637's 637 genes, at 3:54 wall clock. A full single-member screen
   extrapolates to **~100 min**, and the two-member screen the CLI advertises to roughly double
   that; I did not run either, so I cannot say whether a gene with a materially non-zero effect
   exists further down the ID order. Nor did I test `--ko-level reaction` or `--jobs > 1`.

4. **Scaling beyond 5 models / larger GEMs.** `iSFV_1184` (2621 rxn) and `iML1515` (2712) were
   only used singly. Given ~66 s per candidate on 785–1285-reaction models, and community
   construction dominating, I did not attempt a pool where the multi-target `exhaustive_max=100`
   ceiling would be reached with real solve time.

5. **`--robustness-fva` on `search`.** Exists as a flag; I ran neither single- nor multi-target
   search with it, so I cannot say whether it would have rescued the point-estimate concern in
   D5 for the S1 ranking. Note it does not appear on the multi-target path at all.

6. **Statistical claim: is the D4 degeneracy deterministic across re-runs?** I demonstrated the
   *discontinuity* (E11) but did not re-run an identical command to check whether Gurobi returns
   the same vertex twice. That distinguishes "degenerate but reproducible" from "degenerate and
   irreproducible" — the former is a reporting bug, the latter is worse. Untested.

7. **GUI.** Not launched. All claims are CLI-only.

---

## 7. Bottom line

The round-1 hardening is real and mostly landed. Solver failures degrade into structured
`solver_failed` results instead of tracebacks; the pFBA→FBA fallback announces itself in real
runs; unevaluable candidates score `-inf` rather than 0 and are named in warnings; all-zero and
tied rankings are called out in the exact words a careless reader needs; `carbon_equivalent`
pulls carbon numbers out of the model formulas and records the source metabolite for each; the
manifest's reproducibility surface (env lock, per-model checksums, dependency pins, run hash) is
better than most published pipelines; and non-identifiable host transfers and member
attributions are labelled as such. Thirty-seven regression tests pass.

What has not landed is the thing S2 actually needs. **The alone-vs-community comparison is still
uncontrolled**, and the summary now asserts in a machine-readable field that it *is* controlled.
That combination is worse than saying nothing: my control leg (E8) shows iYO844's headline
"4.75× growth benefit from the community" is really a **0.72× cost** once both legs share a
medium. The fix as shipped only works on a `--medium` path that a namespace mismatch makes
unusable. That is the single most important thing to fix before anyone writes a sentence about
cross-feeding from CMIG output.

S1 is answerable and the score now means something in real units — but the answer is
acetate-only by construction, and the tool does not say so. S3's coupling works and is honestly
labelled when it works, but its default settings produce a silent no-op that still reports `ok`;
its member-level perturbation answer is real (−16.4 % host objective when iHN637 is dropped)
while its gene-level answer is not reachable at all, because `gene-ko-search` and
`host-microbe-bigg` cannot be chained.

One pattern is worth naming on its own: the honesty machinery this codebase has built is good,
and it is applied **unevenly**. `_ranking_degeneracy_warnings`, `_worst_status`,
`identifiable=false`, `attribution_method`, and FVA intervals all exist and all work — but each
is wired into some commands and not others. `search` warns about ties; `gene-ko-search` does
not. `host-search-bigg` derives a worst-case status; `strain-growth` does not. `member_contribution.csv`
labels its allocation as non-identifiable; `edges.parquet` does not. Most of §5's P0/P1 list is
not new engineering — it is pointing existing, already-correct guards at the commands that
currently bypass them.

The figures are good screening output and are not close to submission: uncompressed RGBA TIFFs,
outlined text in half the set, not one axis unit anywhere, no panel letters, and missing data
drawn as zero. Nearly all of that is mechanical — the information needed is already sitting in
the JSON summaries next to the figures.
