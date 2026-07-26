# CMIG Functional Test — Independent Evaluator A (Claude Opus 5)

**Date:** 2026-07-25 · **Worktree:** `/Users/jaeyongryu/orca/CMIG` (branch `main`, `d3e90d7`)
**Env:** cobra 0.31.1 · micom 0.39.0 · gurobipy 12.0.3 · optlang 1.9.0 · Gurobi academic (exp. 2027‑05‑27) · macOS 15.6 arm64 · Python 3.12.11 · R 4.3.2 + ggplot2 3.5.2 · matplotlib 3.10.9
**Run outputs:** `runs/opusA/*` (14 run dirs) · **Scratch/figures:** `REVIEW/scratch_opusA/`
**Source files touched:** none (phase‑1 read‑only respected).

Method: `cmig workflows --format json` → `cmig <cmd> --help` → run → `cmig inspect-run`. Every number below was
read out of an artifact I produced in this session. Nothing is inferred from code alone unless explicitly labelled
"code-verified, not executed".

---

## 1. Verdict table

| | Scenario | Verdict | Ran end-to-end? | Primary evidence | Blocking gap |
|---|---|---|---|---|---|
| **S1** | Optimal microbial combination for **SCFA** production | **PARTIAL** | Yes — 4 searches, exit 0 | `runs/opusA/s1_multi_scfa_small`, `s1_but_all5`, `s1_pilot_ac` | Multi-SCFA ranking is **not usable as delivered**: (a) a consortium missing *one* of the 6 exchanges is dropped from the ranking entirely, (b) the winning score was `6.33e-05` with 4/6 SCFA fluxes exactly 0, (c) 10/10 butyrate candidates tied at flux 0 and the CLI still printed a single "best", with `warnings: []`, (d) exhaustive-only, hard cap 100 candidates. Single-metabolite search is sound. |
| **S2** | Microbe–microbe interaction | **SUPPORTED (with one P0 crash)** | Yes — 5 runs | `runs/opusA/s2_solve_small` (16 cross-feeding edges), `s2_strain_growth`, `s2_abundance_iHN637_ac` | Cross-feeding, alone-vs-community growth, and abundance sweeps all work and are interpretable. Blockers: a **legitimate 2-member community hard-crashes with a raw `GurobiError`, exit 1** (repro below); alone-vs-community growth is compared under **two different media**; edge weights carry no identifiability interval while the matching FVA range is `[-8.88, +7.14]`. |
| **S3** | Host–microbe + microbial perturbation → host effect | **PARTIAL** | Yes — 6 runs | `runs/opusA/s3_hostsearch_loo` (Δhost across 7 consortia), `s3_ko_reaction_ac` (6 reaction KOs), `s3_hostmicrobe_keep`, `s3_hostmap_iML1515` | Both halves work *separately* and well. There is **no composed "suppress microbe X → host objective changes by Y" workflow**: `gene-ko-search` has no host argument and `host-search-bigg` has no KO/perturbation argument, so the user must run and diff two workflows by hand. No germ-free host baseline is emitted. No host GEM ships, and the synthetic host (`host-fixture`) accepts **no microbial input at all**, so it cannot stand in. |

**Figure publication-readiness: NOT publication-ready.** Vector + ≥300 dpi raster + provenance are genuinely
there, but every figure fails on units (zero of 10 figures label a unit), panel letters (no support anywhere),
legends (bubble and circle plots have **none**), and overlap/occlusion (3 of 10 figures have colliding or
occluded text). `--journal-preset` is accepted, recorded in the provenance JSON, and **silently ignored**.
Categorical palettes fall below the Okabe-Ito colorblind floor (deuteranopia min ΔE76 = **7.9** in the gene-KO
figure vs **18.3** for Okabe-Ito). Details in §3.

---

## 2. Evidence log

Timings are `/usr/bin/time -p` wall-clock. All logs in `REVIEW/scratch_opusA/*.log`.

### 2.1 Discovery / environment

| # | Command | Exit | Time | Key result |
|---|---|---|---|---|
| E1 | `uv run cmig workflows --format json` | 0 | 0.24 s | 14 workflows mapped; `key_outputs` verified accurate against every run I made |
| E2 | `uv run cmig solvers` | 0 | — | gurobi LP/QP/MILP ✓, highs LP/MILP ✓, osqp LP/QP ✓ |
| E3 | `uv run cmig model-quality --model-dir models --out runs/opusA/model_quality_all` | 0 | 9.3 s | 5/5 optimal. Mass-balance pass rate 0.9865–0.9987; dead-ends 128–301; gene-association coverage 0.885–0.954 |

### 2.2 S1 — SCFA combination search

| # | Command | Exit | Time | Key numbers |
|---|---|---|---|---|
| S1‑a | `cmig search --model-dir <iAF987,iHN637,iYO844> --target ac --min-size 2 --max-size 2 --top-k 5 --out runs/opusA/s1_pilot_ac` | 0 | 40.3 s | 3/3 evaluated. **#1 iHN637+iYO844: EX_ac_m = 12.1120, growth 0.29700. #2 iAF987+iHN637: 5.1177, 0.15393. #3 iAF987+iYO844: infeasible** (`target LP returned no solution object (solver_status=infeasible)`). Correct: iAF987 (*Geobacter*) has `EX_ac_e` bounds (−8.88, −6.84) → obligate acetate uptake, so a pool with no acetate producer is genuinely infeasible. |
| S1‑b | `cmig search --model-dir models --target but --min-size 2 --max-size 2 --top-k 10 --robustness-fva --out runs/opusA/s1_but_all5` | 0 | 250.2 s | 10/10 evaluated. **Every candidate: `target_flux = 0`, `status = optimal`, FVA `[0, 0]`, width 0.** `warnings: []`. CLI printed `best: iAF987+iHN637 flux=0`. `pool_diagnostics`: 4/5 models have `EX_but_e`; iYO844 correctly warned `target exchange not detected for but`. |
| S1‑c | `cmig search --model-dir <3 small> --targets ac,ppa,but,lac__L,lac__D,succ --min-size 2 --max-size 3 --top-k 10 --out runs/opusA/s1_multi_scfa_small` | 0 | 253.7 s | 4/4 evaluated, `normalizer=capability_range_joint_lp`, `solution_semantics=joint_weighted_lp_single_flux_vector`. **#1 iHN637+iYO844 weighted_score 6.32603e‑05** (ac 0, ppa 0, but 0, lac__L 7.0792, lac__D 0, succ 0). **#2 triple score exactly 0.0** (lac__L 4.1860, rest 0). **#3 iAF987+iHN637 and #4 iAF987+iYO844: `status=missing`, `weighted_score=null` — excluded from the ranking** because `EX_succ_m` / `EX_lac__D_m` are absent, even though their per-target solves reached the *largest* SCFA fluxes in the whole run (ac 5.1177 + lac__D 9.2986; ppa 1.2101 + lac__L 2.3521 + succ 2.2927). |
| S1‑d | `cmig search --taxonomy <10 unique ids> --targets ac,but --min-size 3 --max-size 3` | **2** | instant | `120 candidates > exhaustive_max=100; narrow --min-size/--max-size (multi-target search is exhaustive-only, no silent truncation)` — good guardrail, hard ceiling confirmed empirically. |

**S1 interpretation.** Ranking by a *single* metabolite is defensible and fast enough. Ranking by "total SCFA"
is where it breaks:

- Score is `Σ wₘ · minmax(fluxₘ)` over the **observed candidate range**, so it is dimensionless, non-comparable
  across runs, and rank-set-dependent. There is no carbon-equivalent option — summing raw mmol of acetate (C2)
  and butyrate (C4) is not a chemically meaningful "total SCFA" in the first place.
- The joint LP is a linear scalarization with per-metabolite coefficients `w/(hi−lo)`. Ranges are computed from
  only the *evaluable* candidates and zero-width ranges are silently replaced by `1.0`
  (`search_product.py:446`), so the achieved joint fluxes (7.08) sit orders of magnitude below the
  per-target capability that set the scale. Result: the entire top of the ranking is decided at the fifth decimal
  place, and 4 of 6 SCFAs are exactly zero in the "best SCFA producer".
- `targets.py` defines the documented 6-member SCFA preset and `cmig solve --targets scfa` accepts it, but
  `cmig search` does not — the user must type all six BiGG ids by hand.

### 2.3 S2 — Microbe–microbe interaction

| # | Command | Exit | Time | Key numbers |
|---|---|---|---|---|
| S2‑a | `cmig strain-growth --model-dir <3 small> --out runs/opusA/s2_strain_growth` | 0 | 22.4 s | single → community: **iAF987 0.047322 → 0.037169; iHN637 0.224455 → 0.558854; iYO844 0.117966 → 0.560382**; community objective 0.385468 = Σ abundance·growth (0.3333·(0.03717+0.55885+0.56038)) ✓ |
| S2‑b | `cmig solve --taxonomy runs/opusA/s1_pilot_ac/pool_taxonomy.csv --assume-bigg-namespace --targets scfa --fva --fva-metabolites ac,but,lac__L --out runs/opusA/s2_solve_small` | 0 | 39.5 s | `run_hash 67e63fb398039dd9…`, growth 0.38547. **96 edges: 59 uptake, 21 secretion, 16 cross_feeding.** Top cross-feeding: **iYO844→iAF987 ac 3.4286**, iHN637→iAF987 ac 0.27254, iHN637→iYO844 ile__L 0.21275, iYO844→iHN637 leu__L 0.18877, iHN637→iYO844 lys__L 0.18229. **FVA `ac` = [−8.88, +7.1351]** at f=0.5 while the point net flux is −1.0463. |
| S2‑c | `cmig abundance-impact --model-dir <3 small> --member iHN637 --fractions 0.1,0.25,0.5,0.75 --target ac --out runs/opusA/s2_abundance_iHN637_ac` | 0 | 66.6 s | `target_member_exchange` for acetate: **0.8857 → 0.0 → 22.5992 → 0.7168**; `community_target_exchange`: 0.05544 → 0 → 6.7459 → 0. All four `status=optimal`. Summary JSON has **no `warnings` key at all**. |
| S2‑d | `cmig strain-growth --model-dir <iHN637,iYO844> --out runs/opusA/s2_strain_growth_pair` | **1** | 9.9 s | **Unhandled `gurobipy._exception.GurobiError: Unable to retrieve attribute 'X'`**, full traceback to stderr, no CMIG diagnostic. See B1. |
| S2‑e | `cmig dfba-fixture --out runs/opusA/s2_dfba_fixture` | 0 | ~4 s | `dfba_summary.json` written; `inspect-run` kind `dfba`, status `completed` |

**S2 interpretation.** This is the strongest scenario. The cross-feeding readout is biologically coherent
(*B. subtilis* → *Geobacter* acetate, reciprocal branched-chain amino-acid exchange), the allocation method is
named in the artifact (`proportional_shared_pool`) and its non-identifiability is documented in the module
docstring. Three real caveats:

1. **Alone-vs-community is not a controlled comparison.** `_cmd_strain_growth` (`cmig/cli/main.py:1541‑1550`)
   builds the single-model solve from `read_sbml_model(model_file)` + `solve_single_model(model)` and **never
   applies `medium_spec`**, which is applied only to the community. So the "alone" leg runs on the model's native
   SBML bounds and the "in community" leg on MICOM's merged medium. The 2.5× iHN637 growth *increase* in S2‑a is
   therefore not attributable to mutualism.
2. **Edge weights have no uncertainty.** `edges.parquet` has no `fva_lo`/`fva_hi` columns. In S2‑b the acetate
   FVA interval spans uptake→secretion (`[−8.88, +7.14]`), i.e. the sign of the flux that generates the
   3.43 mmol/gDW/h `iYO844→iAF987 ac` edge is not determined, yet the edge is emitted as a point number.
3. **Requested FVA silently disappears.** `--fva-metabolites ac,but,lac__L` is recorded in the manifest, but
   `but` and `lac__L` are absent from `profile.parquet` entirely (dropped by the zero-net-flux rule in
   `interactions.py:104‑106`) with no diagnostic. A metabolite whose *point* net flux is 0 but whose FVA range is
   wide is exactly the interesting case, and it is the one that vanishes.
4. **Abundance sweep is degenerate, not reported as such.** The 0 → 22.60 → 0.72 swing in S2‑c is alternate-optima
   behaviour of the pFBA solution, not a dose–response. `abundance-impact` has no `--fva`, no uniqueness check,
   and emits no warning, while the figure joins the four points with straight lines (see F9).

### 2.4 S3 — Host–microbe and perturbation → host effect

No human/host GEM ships in `models/`. Two consequences I tested rather than assumed:

- `cmig host-fixture` runs the synthetic colonocyte and is honest (`scope:
  "synthetic_toy_host_not_human_gem_quantitative"`, biomass 35.0, lumen uptake ac 8.0 / but 4.0, viable true),
  but its help exposes only `--solver --maintenance-flux --out`: **it takes no microbial input**
  (`lumen_availability_from_pair()` is hardcoded). It cannot answer any question about *the user's* community.
- The only real host path is `host-microbe-bigg` / `host-search-bigg`, which need a BiGG-style host SBML. I used
  **iML1515 as an explicit surrogate host** to exercise the product pipeline. All S3 numbers below are pipeline
  evidence, not biology, and every run was tagged `--biomass-basis-kind validation`.

| # | Command | Exit | Time | Key numbers |
|---|---|---|---|---|
| S3‑a | `cmig host-map --host models/iML1515.xml --model-dir <3 small> --out runs/opusA/s3_hostmap_iML1515` | 0 | 6.7 s | **170 exact / 5 annotation / 0 normalized / 132 unmatched of 307 secretions; 21 host-uptake-capable.** All 6 SCFAs matched exactly. **3 of the 5 annotation matches are D↔L stereoisomer swaps**: `arab__D_e→EX_arab__L_e`, `glu__D_e→EX_glu__L_e`, `pser__D_e→EX_pser__L_e` (plus `glcn__D_e→EX_glcn_e`, `orn__L_e→EX_orn_e`). Each carries `confirm in interface map before quantitative coupling` — **and all are written into the default `interface_map` block of `host_interface_map.json`.** |
| S3‑b | `cmig host-microbe-bigg --host models/iML1515.xml --model-dir <3 small> --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation --biomass-basis-source "…" --out runs/opusA/s3_hostmicrobe_auto` | 0 | 22.2 s | community optimal (0.38547) but **host infeasible, `objective_value = 0`, `viable = false` — while top-level `status = "ok"`** and `inspect-run` also reports `status: ok`. Only `etoh`/`fe2` matched; co2/h/h2o excluded as currency; `4hba` unmatched. Warnings correctly include `biomass basis is validation-only; result is not publication-ready`. |
| S3‑c | same + `--keep-host-uptake` → `runs/opusA/s3_hostmicrobe_keep` | 0 | 27.6 s | **host objective 1.087363, viable true**, `microbe_to_host = {etoh: 5.083953}`. Good practice observed: `fe2` flagged `host transfer is not point-identifiable at the optimal objective … report FVA intervals` with `lumen_uptake_ranges fe2 = [0.017464, 16.400566]`; `member_contribution.csv` carries `identifiable = false` + `attribution_method = abundance_weighted_proportional_allocation`. |
| S3‑d | `cmig host-search-bigg --host models/iML1515.xml --model-dir <3 small> --min-size 1 --max-size 3 --target ac --metric objective_value --keep-host-uptake … --out runs/opusA/s3_hostsearch_loo` | 0 | 92.5 s | 7/7 candidates. **Host objective: all-3 1.087363 > iHN637 1.017991 > iAF987+iHN637 0.934137 > iYO844 0.877614 > iAF987+iYO844 0.876998 > iAF987 0.876997 > iHN637+iYO844 0 (failed).** Δhost(add iAF987+iYO844 to iHN637) = **+0.069372**. `target_transfer` (ac) = 0 for all but iYO844 (0.025225). |
| S3‑e | `cmig gene-ko-search --model-dir <3 small> --members iAF987,iHN637,iYO844 --member iHN637 --ko-level reaction --reactions ACKr,PTAr,PTA2,ACt2r,LDH_D,ALCD2x --target ac --out runs/opusA/s3_ko_reaction_ac` | 0 | 142.9 s | baseline ac flux **7.244007**. Δ vs baseline: **ACKr −0.664925 (−9.18 %), PTAr −0.638383, ACt2r −0.612112**, ALCD2x −0.076558, LDH_D −0.076439, PTA2 −0.075521. `n_genes_evaluated = n_genes_total = 6`, `warnings: []`. |

**S3 interpretation.** The two halves are individually good. The KO screen is the single most scientifically
convincing result in this whole test: with no hints, acetate kinase (`ACKr`), phosphotransacetylase (`PTAr`) and
the acetate transporter (`ACt2r`) came out as the top three suppressors of acetate secretion, exactly as the
*C. ljungdahlii* Wood–Ljungdahl/acetate biochemistry predicts, an order of magnitude ahead of the fermentation
side-branches. `host-search-bigg --min-size 1` is a genuine leave-one-out that quantifies "microbe → host
objective". What is missing is the *join*:

- `gene-ko-search --help` has no `--host` and `host-search-bigg --help` has no `--genes/--reactions/--ko-level`.
  A "knock out gene *g* in microbe *m* → Δ host objective" answer requires the user to hand-build two taxonomies,
  run `host-microbe-bigg` twice and subtract. `cmig/core/delta.py` implements exactly this diff for `SolveResult`
  but is not wired to the host path and has no CLI surface.
- No germ-free baseline. `--min-size 1` is the floor, so Δ-vs-no-microbiome must be inferred (here ≈0.877, from
  the single-member floor) rather than reported.
- `host-microbe-bigg` throws away the community's own perturbation context: the run that crashed in S2‑d is the
  same pair that `host-search-bigg` silently ranked last at 0.

---

## 3. Figure assessment

I inspected the produced files themselves (SVG/PDF XML, TIFF headers via PIL, and rasterised PNGs read visually
— `REVIEW/scratch_opusA/p1…p10.png`), not the code.

**Formats produced.** `render-figure` succeeded for all four formats on a tidy-profile run
(`svg` 1.38 s, `pdf` 2.25 s, `eps` 1.66 s, `tiff` 1.46 s, all exit 0), each with a sidecar
`*.figure_spec.json` + `*.render_provenance.json` recording renderer, R/renv or matplotlib version, script
SHA-256 and input SHA-256. That provenance layer is better than most published pipelines.

**Per-criterion verdict**

| Criterion | Verdict | Observed |
|---|---|---|
| Colorblind-safe categorical palette (Okabe-Ito or equivalent) | **FAIL** | **No Okabe-Ito hex appears anywhere.** Palettes are ColorBrewer/tab-style: `#2ca25f #3182bd #e6550d #9aa0a6 #2b8cbe #31a354 #969696 #1f77b4 #d62728`. Viénot/Brettel dichromat simulation + ΔE76 in CIELAB, minimum pairwise separation: gene-KO set (`#2ca25f`/`#e6550d`/`#969696`) deuteranopia **7.9** (green "improves objective" vs grey "no change" — indistinguishable); interaction 4-colour set deuteranopia **12.3**; protanopia 22.7 for both. Okabe-Ito's own 4-colour floor is **18.3**. 2-colour figures are fine (strain-growth 40.5, R profile 87.9 deutan). |
| Sequential colormap | **PASS** | `interaction_heatmap` uses `viridis` (`interaction_figures.py:360`) — perceptually uniform and CVD-safe. |
| Vector output | **PARTIAL** | SVG everywhere; PDF/EPS **only** via `render-figure`, which requires `profile.parquet` and therefore **refuses every search / host / strain-growth / KO run**: `no profile.parquet in runs/opusA/s2_strain_growth — render-figure needs a tidy-profile run` (exit 2). Also `interaction_heatmap.svg` embeds the matrix as a **base64 PNG** (1338×925 px) inside the SVG, so the data area is raster, not vector. |
| ≥300–600 dpi raster (TIFF) | **PARTIAL** | `render-figure` TIFF: 3600×2400 px, **600 dpi, RGB, `tiff_lzw`**, 211 KB — good. Every other TIFF (`search_plot`, `search_scatter`, `interaction_*`, `gene_ko_plot`, `strain_growth_plot`): **300 dpi, RGBA, `compression=raw`** → 8.8 MB and 11.7 MB single-panel files (`interaction_figures.py:273`, hardcoded `dpi=300`, no compression arg). 300 dpi is below the ≥600 dpi bar journals set for line art, and RGBA + uncompressed will be rejected by most submission systems. |
| Typography | **FAIL** | `font.family: "Arial"` hard-set with no fallback stack (`interaction_figures.py:261`). The R renderer aborted on `unknown family 'Arial'` and fell back to matplotlib → the resulting PDF embeds `DejaVuSans`, so typography is host-dependent and not reproducible. Sizes are consistent (title 14, label 11, ticks 10). |
| No clipped/overlapping labels | **FAIL** | 3/10 figures: (a) `search_plot` — subtitle `exhaustive · evaluated 3/3 candidates` **overlaps** the title `Target production search: ac`; (b) `gene_ko_plot` — the legend box is drawn **inside** the axes and sits on top of the ACKr and PTAr bars, occluding both; (c) R `External Profile` at the default 6×4 in — 28 metabolite tick labels collide (`glc__D`/`nh4`, `so4`/`mg2` overprint). |
| Multi-panel with panel letters A/B/C | **FAIL** | No panel-letter code exists in `cmig/render/` or `cmig/core/interaction_figures.py`. `cmig/render/composer.py` defines `PanelSpec`/`PANEL_KINDS` but has **zero CLI callers**; each artifact is a standalone single-panel file. The only genuinely multi-panel output is `abundance_impact_plot` (3 stacked rows, shared x) — and it has no A/B/C. |
| Axis labels with units | **FAIL (0/10)** | Not one figure carries a unit. Observed labels: `Target exchange flux (EX_ac_m)`, `Growth rate`, `Community growth under target objective`, `net exchange flux  (+ secretion / - uptake)`, `objective value`, `Transfer flux`, `Flux` (colorbar), `ac secretion flux delta vs baseline (bar) — color = objective`. All should read `mmol gDW⁻¹ h⁻¹` or `h⁻¹` — and CMIG *knows* the unit: `host_microbe_bigg_summary.json` carries `"flux_unit": "mmol gDW_host^-1 h^-1"`. The bubble plot has **no axis labels at all**. |
| Informative legend | **FAIL** | `interaction_bubble.svg` and `interaction_circle.svg` contain **no legend of any kind** — bubble size encodes flux magnitude and colour encodes `edge_type`, and neither channel is decodable. Text inventory of `interaction_bubble.svg` is tick labels + `Interaction bubble plot` only. The R profile legend is titled `label`, the internal column name. |
| No chartjunk / data-ink | **PARTIAL** | Good: spines removed, `set_axisbelow`, restrained gridlines. Bad: `interaction_heatmap` wastes ~30 % of the canvas to an empty bottom band (`tight_layout()` then `subplots_adjust(bottom=0.28)` fight each other) and 11 of 13 columns are all-zero, with a single `fe2` cell (16.40) saturating the scale so the acetate/ethanol cells are near-invisible; `interaction_circle` is straight-line node-link, not a chord diagram, with arrows crossing the interior. |
| Semantic coherence of axes | **FAIL** | `interaction_bubble` and `interaction_heatmap` put microbe ids (`iAF987`), a metabolite pseudo-node (`met:etoh`) and an aggregate (`microbiome`) on the **same categorical axis**, and the internal `met:` prefix leaks into the rendered figure in the bubble plot while being stripped in the heatmap. |
| SVG and TIFF agree | **FAIL** | For `search`, SVG and TIFF are produced by two **independent implementations** — a hand-rolled writer (`_write_search_scatter_svg`, main.py:3594) and a matplotlib writer (`_write_search_scatter_tiff`, main.py:3498). The TIFF has numeric axis ticks (0,2,…,12); **the SVG has gridlines but no tick numbers at all** and a different x-caption. A journal given the SVG receives an unreadable axis. |
| Journal presets | **FAIL** | See B2 — `--journal-preset` has no effect and validates nothing. |
| Failed data marked as failed | **FAIL** | `host_search_plot` renders the crashed candidate `iHN637+iYO844` as a **zero-length bar**, visually identical to a real host objective of 0. No hatch, no annotation. |

**Honest call.** These are competent exploratory/QC figures — clean, restrained, reproducible, with real
provenance sidecars. They are **not submission-ready** for Nature Genetics or an equivalent. To get there:
add units to every axis, add a panel-letter + composition path (wire up the already-written `composer`), give
the bubble/circle plots legends, switch categorical fills to Okabe-Ito, raise all TIFF writes to 600 dpi RGB
with LZW, actually apply `--journal-preset`, fix the three overlap cases, mark failed candidates, and make the
SVG and TIFF of a given figure the same figure. None of that is deep — it is roughly a day of focused work in
two files.

---

## 4. Bugs / defects found

### B1 — P0 · Unguarded MICOM call: raw `GurobiError` traceback, exit 1, on a valid 2-member community

**Repro (any of these):**
```bash
mkdir -p /tmp/pair && ln -sf $PWD/models/iHN637.xml /tmp/pair/ && ln -sf $PWD/models/iYO844.xml /tmp/pair/
uv run cmig strain-growth --model-dir /tmp/pair --out runs/x            # exit 1
uv run cmig host-microbe-bigg --host models/iML1515.xml --model-dir /tmp/pair --keep-host-uptake \
  --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 --biomass-basis-kind validation \
  --biomass-basis-source repro --out runs/y                             # exit 1
```
**Observed:** `gurobipy._exception.GurobiError: Unable to retrieve attribute 'X'`, full stack to stderr, no
CMIG diagnostic, no output directory. **Expected:** a `status`/`diagnostic` pair — the guard on the very next
line (`if community_result.status != "optimal":`, `host_coupling.py:218`) is already written for this case but is
unreachable because the exception is raised *inside* the delegated call.

**Isolated root cause** (`REVIEW/scratch_opusA`, executed):
```
A) c.cooperative_tradeoff(fraction=1.0, fluxes=False)            -> optimal, growth 0.5940
B) c.cooperative_tradeoff(fraction=0.5, fluxes=True, pfba=False) -> optimal
C) c.cooperative_tradeoff(fraction=0.5, fluxes=True, pfba=True)  -> GurobiError   <-- what CMIG calls
   gurobi Model.Status = 1 (LOADED); optlang status = "infeasible"
```
The **pFBA second stage** leaves the Gurobi model unsolved; `micom/solution.py:83` reads
`community.solver.primal_values` unconditionally. `cmig/core/engine.py:128` calls
`cooperative_tradeoff(fraction=f, fluxes=True, pfba=True)` with no `try/except`.

**Blast radius:** every workflow that goes through `MicomEngine.cooperative_tradeoff` — `solve`,
`strain-growth`, `abundance-impact`, `host-microbe-bigg`, `host-search-bigg`, `sweep`. `search` is immune only
because `target_max_solve` uses `fluxes=False`.

**Silent-corruption variant:** inside `host-search-bigg` the same failure is caught per-candidate and written as
`evaluation_status=failed, diagnostic="Unable to retrieve attribute 'X'", score=0` — so a numerically
unevaluable consortium is **ranked last as if the host objective were zero** (`s3_hostsearch_loo` rank 7), the
run exits 0, `status: "ok"`, and `host_search_summary.json` has **no `warnings` key** to report that 1 of 7
candidates never solved.

### B2 — P1 · `--journal-preset` is accepted, recorded in provenance, and silently ignored

```bash
uv run cmig render-figure --run-dir runs/opusA/s2_solve_small --out f.pdf --format pdf --journal-preset nature
```
**Observed:** exit 0. `f.pdf.figure_spec.json` → `{"journal_preset":"nature","width_in":6.0,"height_in":4.0,"dpi":600}`.
PDF `/MediaBox [0 0 432 288]` = 6.0×4.0 in. **Expected:** the `nature` preset is `(3.50, 3.0, 300)`
(`composer.py:31`). `PanelSpec.for_journal()` — the only function that applies a preset — has **zero callers in
the repository**; `_cmd_render_figure` (main.py:962) passes `journal_preset` straight into `FigureSpec` as
metadata.
**Worse:** `--journal-preset totally_made_up` → exit 0, no warning, recorded verbatim in the provenance JSON.
The artifact therefore *claims* a journal specification it never had, which is a reproducibility defect, not
just a cosmetic one.

### B3 — P1 · Multi-target search disqualifies a consortium for one missing exchange

`s1_multi_scfa_small` ranks 2 of 4 candidates as `status="missing"`, `weighted_score=null`, on the strength of a
single absent exchange (`EX_succ_m`, `EX_lac__D_m`) — while those two consortia hold the largest individual SCFA
fluxes in the run. `_evaluate_members_multi` (`search_product.py:410-411`) sets the whole combo non-optimal if
*any* target is non-optimal. For an additive question ("most total SCFA") a missing exchange should contribute
**0**, not disqualify. Secondary: the flux columns for those excluded rows are still populated in
`search_rankings.csv` from **independent per-target max solves** — mutually unachievable values presented in one
row with no marker.

### B4 — P1 · No tie/degeneracy warning; "best" is reported for an all-zero ranking

`s1_but_all5`: 10/10 candidates `target_flux = 0.0`, `status = optimal`, FVA `[0,0]`; `warnings: []`; CLI prints
`best: iAF987+iHN637 flux=0`. Rank 1 is simply the alphabetically first tie (`sort key (-score, members)`).
Expected: a warning such as `no candidate achieved non-zero target flux` / `top N candidates tied at score X`.
As delivered, a user copying the CLI line reports a butyrate-optimal consortium that produces no butyrate.

### B5 — P1 · `strain-growth` compares alone vs community under different media

`cmig/cli/main.py:1542-1548` — the single-model leg never receives `medium_spec`. With `--medium` supplied the
two legs are explicitly different environments; without it, one leg uses native SBML bounds and the other MICOM's
merged medium. The headline result of the workflow (all three strains grow *better* in community, S2‑a) is
therefore confounded and cannot be reported as interaction.

### B6 — P1 · Top-level `status: "ok"` while the host LP is infeasible

`s3_hostmicrobe_auto`: `host.status = "infeasible"`, `host.viable = false`, `host.objective_value = 0.0`, yet
`summary.status = "ok"` and `cmig inspect-run --format json` also returns `"status": "ok"`. Any script or agent
gating on `status` treats a failed host solve as success. `warnings` does not mention the infeasibility either
(only the validation-basis note, the currency exclusions and the unmatched metabolite).

### B7 — P1 · `inspect-run`, the mandated verification step, returns `unknown` for 4 of 14 run kinds

Executed over all 14 of my run dirs:

| run | kind | status |
|---|---|---|
| `s2_solve_small` | community_solve | **unknown** (has a full manifest + `run_hash 67e63fb39803`) |
| `s1_multi_scfa_small` | model_pool_search | **unknown** (exit 0, complete) |
| `model_quality_all` | **unknown** | **unknown** |
| `s3_hostmap_iML1515` | **unknown** | **unknown** |

The multi-target summary has no `status` key (the single-target one does); the solve manifest has `diagnostic`
but no `status`. `run_hash` is `null` for **every** workflow except `solve` — so a `search`, `host-*` or
`gene-ko-search` result cannot be cited or regression-checked the way `SKILL.md` promises
("runs emit manifests and run hashes").

### B8 — P1 · Auto-generated interface map ships stereochemically wrong D↔L mappings as *defaults*

`s3_hostmap_iML1515/host_interface_map.json` `interface_map` contains `"arab__D_e": "EX_arab__L_e"`,
`"glu__D_e": "EX_glu__L_e"`, `"pser__D_e": "EX_pser__L_e"`. These are chemically distinct metabolites. The CSV
does carry `match_type=annotation` and `confirm … before quantitative coupling`, and `SKILL.md` mandates review —
but the JSON that `--interface-map` consumes puts them in the same flat `interface_map` dict as the 170 exact
matches, behind a `_comment` string. A user who passes the file through unedited (the obvious workflow) gets
D-metabolites coupled to L-exchanges with no runtime warning.

### B9 — P2 · `n_biomass` counts objective terms, not biomass reactions

`pool_diagnostics.csv` reports **`n_biomass = 283`** for iAF987 with empty `warnings`;
`model_quality.csv` reports `solve_status=optimal, objective_value=0.047322` with no note.
`iAF987.xml` (checksum-matched to `MODEL_SOURCES.json`, so this is the genuine BiGG file) contains **283
`fluxObjective` entries** — its active objective is a 283-term linear combination, not a growth reaction.
`_biomass_reactions` (`cmig/io/model_import.py:84`) defines "biomass candidate" as *any reaction with a
non-zero objective coefficient*, so the check passes. Consequence: iAF987's "growth" (0.0473 single, 0.0372 in
community) is an arbitrary objective value being reported and plotted as a growth rate under the label
`Growth rate`. Expected: report `n_objective_terms` and warn when the objective is not a single
biomass-like reaction.

### B10 — P2 · Requested targeted FVA silently vanishes for zero-flux metabolites

`--fva-metabolites ac,but,lac__L` is recorded in `manifest.json`; only `ac` appears with `fva_lo/fva_hi`.
`but` and `lac__L` have no row in `profile.parquet` and no diagnostic (`interactions.py:104-105` drops
zero-flux rows before FVA is attached).

### B11 — P2 · `abundance-impact` reports a degenerate sweep with no caveat and no identifiability check

`s2_abundance_iHN637_ac`: acetate exchange 0.8857 → 0.0 → 22.5992 → 0.7168 across abundances 0.1/0.25/0.5/0.75,
all `status=optimal`. Summary JSON has **no `warnings` key**; there is no `--fva`; and the figure joins the
points with straight lines, implying a continuous dose–response. `SKILL.md`'s "sensitivity, not causality"
guardrail is documentation-only and is never emitted into the artifact.

### B12 — P2 · KO screen's "best" is the *weakest* knockout

`s3_ko_reaction_ac` sorts by descending score = descending remaining target flux, so `PTA2` (Δ = −0.0755) is
rank 1 and `ACKr` (Δ = −0.6649) is rank 6, and the CLI prints
`best: iHN637:PTA2 delta=-0.07552`. For the dominant use case — "which knockout most suppresses this
metabolite" — "best" is inverted. `--direction` changes the LP objective, not the ranking direction.

### B13 — P2 · `mu_community` recomputed once per target (multi-target cost ≈ 7× per consortium)

`_evaluate_members_multi` calls `target_max_solve` per spec with `mu_community=None`, so
`_community_growth_star` (a `cooperative_tradeoff(fraction=1.0)` QP) runs once **per target**, then
`_evaluate_members_multi_joint` rebuilds the community and does it again. Measured: 6-target search over 4
consortia of small models = **253.7 s (63 s/consortium)** vs 13 s/consortium for the single-target search on the
same models. μ*, and the built community, are per-consortium invariants.

---

## 5. Prioritized improvement proposals *(not implemented — phase 1)*

### P0

1. **Guard the MICOM delegate.** `cmig/core/engine.py` → `MicomEngine.cooperative_tradeoff`: wrap the
   `community.cooperative_tradeoff(...)` call in `try/except (GurobiError, Exception)` and return
   `SolveResult(status="solver_failed", diagnostic=…)` so the existing downstream `status != "optimal"` branches
   (e.g. `host_coupling.py:218`) actually fire. Add a `pfba=True → pfba=False` retry with an emitted
   `warnings` entry (`pfba_stage_failed; reporting non-parsimonious flux distribution`), since B1‑B shows the
   non-pFBA solve succeeds on exactly the community that crashes. Fixes B1 for all six affected workflows.
2. **Never let an unevaluable candidate sit in a ranking as a zero.** `cmig/cli/main.py` →
   `_cmd_host_search_bigg` / `_write_host_search_outputs`: move `evaluation_status != "ok"` rows out of the
   ranked block into an `unevaluated` block, add a top-level `warnings` and `n_candidates_failed` to
   `host_search_summary.json`, and hatch-or-omit them in `host_search_plot`. Fixes the silent half of B1 and the
   corresponding figure defect.

### P1

3. **Make multi-target additive-safe.** `cmig/core/search_product.py` → `_evaluate_members_multi` /
   `search_model_pool_multi`: treat a missing exchange as `flux = 0` for that target (recording it in a
   per-candidate `missing_targets` list) instead of invalidating the consortium; keep the current behaviour only
   for genuinely non-optimal LPs. Fixes B3.
4. **Add a physically meaningful total-SCFA metric.** `cmig/core/targets.py` + `search_product.py`: add a
   `--target-preset scfa` (the preset already exists and `solve` already accepts it) and a
   `--multi-metric {normalized_weighted, carbon_equivalent, raw_sum}` where `carbon_equivalent` weights each
   target by its carbon number from the model's metabolite formula. This is what "which combination produces the
   most SCFA" actually means, and it removes the observed-range dependence that produced the `6.3e-05` ranking.
5. **Warn on ties and all-zero rankings.** `cmig/core/search_product.py` → `search_model_pool` (and the
   multi-target twin): append `no candidate achieved a non-zero target flux` when `max(score) <= eps`, and
   `top-{k} candidates tied at score {s}` when the leader is not strictly ahead. Fixes B4.
6. **Apply the medium to both legs of `strain-growth`.** `cmig/cli/main.py:1542-1548`: pass `medium_spec`
   through `apply_medium_checked` to the single-model solve, and record
   `single_medium == community_medium` in the summary. If a medium cannot be applied to the single model, emit a
   warning rather than silently comparing two environments. Fixes B5.
7. **Derive top-level `status` from the worst sub-status.** `cmig/core/host_coupling.py` (summary assembly) and
   `cmig/core/run_store.py` (`inspect-run`): set `status` to `degraded`/`failed` when
   `host.status != "optimal"` or any candidate failed, and add the infeasibility to `warnings`. Fixes B6.
8. **Give every workflow a `status` and a `run_hash`.** `cmig/core/manifest.py` + the per-command summary
   writers in `cmig/cli/main.py`: emit `status` in the multi-target search summary and the solve manifest, teach
   `inspect-run` the `model_quality` and `host_exchange_map` kinds, and extend run-hashing beyond `solve` so
   `search`/`host-*`/`gene-ko-search` results are citable. Fixes B7.
9. **Split reviewed from unreviewed in the interface map.** `cmig/core/host_map.py`: write
   `{"interface_map": {<exact only>}, "needs_review": {<annotation/normalized, with match_type and reason>}}`,
   and have `host-microbe-bigg` refuse (or loudly warn) when a passed map still contains `needs_review` entries.
   Fixes B8, and removes the D↔L footgun without weakening the wizard.
10. **Fix the figure fundamentals.** `cmig/core/interaction_figures.py` and the `_write_*_svg/_tiff` pair in
    `cmig/cli/main.py`: (a) add units to every axis and colorbar, sourcing them from the `flux_unit` values the
    summaries already carry; (b) add legends to `_render_bubble` (colour = edge type, a 3-point size key) and
    `_render_circle`; (c) `font.family = ["Arial", "Helvetica", "DejaVu Sans"]`; (d) `_save_svg_and_tiff` →
    `dpi=600, compression="tiff_lzw"`, RGB not RGBA; (e) move the `gene_ko_plot` legend outside the axes and
    give `search_plot`'s subtitle its own row; (f) delete one of the two divergent search-figure
    implementations so SVG and TIFF are the same figure.
11. **Wire up `--journal-preset` or remove it.** `cmig/cli/main.py:962` → call
    `FigureSpec(...).for_journal(args.journal_preset)` (already implemented, currently uncalled) when the flag is
    not `default`, and validate the name against `JOURNAL_PRESETS` in `FigureSpec.validate()` so
    `totally_made_up` exits 2 instead of being written into the provenance. Fixes B2.
12. **Extend `render-figure` beyond tidy-profile runs.** `cmig/cli/main.py` → `_cmd_render_figure`: dispatch on
    the `inspect-run` kind so search/host/KO/strain-growth runs can be re-rendered to PDF/EPS at journal specs
    (today they only ever get one hand-rolled SVG plus a 300 dpi RGBA TIFF).

### P2

13. **Report objective structure, not "biomass".** `cmig/io/model_import.py:84` → rename to
    `objective_reactions`, expose `n_objective_terms`, and have `model_pool.py:154` and `model_quality.py` warn
    `objective has {n} terms; not a single biomass reaction — reported growth is an objective value` when
    `n > 1`. Fixes B9 (and would have flagged iAF987 immediately).
14. **Never silently drop requested analysis.** `cmig/core/interactions.py:104-105` /
    `cmig/core/fva.py`: keep an explicitly `--fva-metabolites`-requested metabolite in `profile.parquet` even at
    zero net flux (with its FVA interval), or record it in a `dropped_zero_flux` diagnostic. Fixes B10.
15. **Add identifiability to interaction edges.** `cmig/core/interactions.py` → `build_tidy`: add
    `weight_lo`/`weight_hi` to `EDGES_SCHEMA`, populated when `--fva` ran, and surface the
    `CROSS_FEEDING_ALLOCATION_METHOD` + non-identifiability note in the manifest rather than only the docstring.
16. **Make `abundance-impact` self-auditing.** `cmig/cli/main.py` → `_cmd_abundance_impact`: add a `warnings`
    key carrying the standing "sensitivity, not causality" note; add `--fva` on the target exchange per
    abundance point; and emit `non_monotonic_target_response` when the sweep changes sign of slope, so the
    degeneracy in B11 is visible in the artifact.
17. **Add `--rank-by {remaining,effect}` to the KO screen.** `cmig/cli/main.py` → `_cmd_gene_ko_search`: default
    to ranking by `|score_delta|` descending (the suppression use case) or at minimum relabel the CLI line from
    `best:` to `highest remaining {target}:`. Fixes B12.
18. **Hoist μ\* and the built community.** `cmig/core/search_product.py`: compute `_community_growth_star` once
    per consortium and thread it into every `target_max_solve` via the existing `mu_community` parameter, and
    reuse the built community between the capability and joint passes. From the measured 63 s/consortium this
    should recover most of a ~7× factor and is the single change that most improves S1's tractability. Fixes B13.
19. **Close the S3 loop.** New surface, e.g. `cmig host-ko-impact`, composing `gene-ko-search`'s KO application
    with `host_coupling.run_bigg_host_microbe` and `cmig/core/delta.py`, emitting
    `Δhost_objective`, `Δtarget_transfer` and `Δmicrobe_to_host` per knockout; plus a `--include-germ-free`
    baseline row in `host-search-bigg`. This is the one *capability* gap (as opposed to a defect) in the three
    scenarios.

---

## 6. What I could not test, and why

1. **Real host–microbe biology.** No human/host GEM ships in `models/` and CMIG (by design) does not download
   Recon3D/Human-GEM. Every S3 number used **iML1515 as a surrogate host**, so it validates the *pipeline* and
   nothing biological. `--biomass-basis-kind validation` was used throughout and the artifacts correctly carry
   `not publication-ready`. `host-generic`/`host-benchmark` need `$CMIG_RECON3D_PATH` and were not run.
2. **A publication-grade host run.** That needs real measured/literature `--microbial-biomass-gdw` /
   `--host-biomass-gdw` values and a *reviewed* interface map. I refused to invent gDW numbers or to pass the
   auto-generated map as reviewed, so `--biomass-basis-kind measured|literature` and the `weighted` metric
   (which additionally requires defensible `--host-reference`/`--target-reference`) are untested.
3. **A realistically sized model pool.** Only 5 unique GEMs are available and member ids come from the SBML
   `model.id`, so duplicating files does not enlarge the pool (`taxonomy id values must be unique`). I probed the
   >100-candidate multi-target guard with a synthetic 10-row taxonomy CSV (exit 2, confirmed), but I could not
   measure real runtime at 20–100 members, which is where the S1 tractability question actually bites.
   Extrapolating the measured 63 s/consortium, a 6-target search over even a 10-member pool at size 3 is both
   over the hard cap and hours of wall-clock.
4. **`--strategy ga` / `random` on a real large pool** — same reason. Code-verified that both add
   `global optimum is not guaranteed` warnings (`search_product.py:216, 220`); not executed at scale.
5. **A full gene-level KO screen.** `--ko-level gene --max-genes 0` on iHN637 is 637 genes; the measured
   ~24 s/KO in a 3-member community puts a complete screen at ≈4 h. I ran a 6-reaction targeted screen instead,
   so the `--max-genes` truncation warning, `--gene-selection random --seed`, and `--jobs > 1` thread-safety are
   untested.
6. **`dfba` / `dfba-sensitivity` on a user model, and `spatial-preview`.** I ran `dfba-fixture` (exit 0,
   `inspect-run` kind `dfba`, status `completed`) and read the flags, but did not audit a dFBA endpoint across
   `--dts × --kms`, so I cannot say whether the sensitivity guardrail behaves as documented.
7. **`sweep`, `publication-benchmark`, `golden verify`, `stats-*`, `sandbox-fixture`, and the GUI.** Out of
   budget for this pass; all exist in the workflow map. Notably `publication-benchmark` is the one surface that
   claims to bundle the whole audit, and it is the highest-value untested item.
8. **Cross-platform typography.** The R renderer's `unknown family 'Arial'` fallback was observed on this macOS
   box; I could not check what a Linux/CI run produces, which is exactly where the hardcoded font is most likely
   to change the figures.

One environment caveat, so it is not mistaken for a CMIG bug: an unrelated editor plugin created a `.omc/`
directory inside `runs/opusA/s1_pilot_ac` while I was inspecting it, and `inspect-run` listed its contents as
run artifacts. That is my tooling, not CMIG's — though it does show `inspect-run` enumerates a run directory
recursively without filtering.
