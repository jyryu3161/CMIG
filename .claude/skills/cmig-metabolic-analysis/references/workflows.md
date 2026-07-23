# CMIG workflow reference

Per-command reference for the CMIG CLI. This mirrors the machine-readable map
from `uv run cmig workflows --format json`; when in doubt, that command and
`uv run cmig <command> --help` are ground truth. Every analysis command takes
`--out runs/<name>` and should be followed by
`uv run cmig inspect-run --run-dir runs/<name> --format json`.

## Contents

- [Model pool search family](#model-pool-search-family)
- [Host-microbe family](#host-microbe-family)
- [Community solve](#community-solve)
- [Dynamics: dFBA and spatial](#dynamics-dfba-and-spatial)
- [Model QC and publication preflight](#model-qc-and-publication-preflight)
- [Inspection, reproducibility, utilities](#inspection-reproducibility-utilities)
- [Fixture demos](#fixture-demos)

---

## Model pool search family

### `cmig search` — rank model combinations for a target
Rank microbial model combinations by target exchange production or uptake
(e.g. "choose 2 models from a folder and maximise butyrate").
- Required: `--model-dir` (or `--taxonomy`), `--target`, `--out`.
- Common: `--min-size`, `--max-size`, `--strategy auto`, `--n-samples`,
  `--seed`, `--top-k`, `--robustness-fva`, `--medium`, `--recursive`.
- Outputs: `search_summary.json`, `search_rankings.csv`,
  `search_member_matrix.csv`, `pool_diagnostics.csv`, `search_plot.svg`,
  `search_scatter.svg`.
- Use `--recursive` when the pool is organised as subfolders
  (`strainA/model.xml`, `strainB/model.xml`).
```bash
uv run cmig search --model-dir models --target but --min-size 2 \
  --max-size 2 --top-k 10 --strategy auto --out runs/search_but
```

### `cmig strain-growth` — single vs community growth
Compare each strain's single-model FBA growth with its member growth inside the
full MICOM community.
- Required: `--model-dir` (or `--taxonomy`), `--out`.
- Common: `--medium`, `--tradeoff-f`, `--recursive`.
- Outputs: `strain_growth_summary.json`, `strain_growth.csv`,
  `strain_growth_plot.svg`.
- Interpretation: `single_growth` = individual GEM FBA; `community_member_growth`
  = growth after MICOM construction + cooperative tradeoff; `abundance` = member
  abundance used by the community model.
```bash
uv run cmig strain-growth --model-dir models --out runs/strain_growth
```

### `cmig abundance-impact` — one-member ratio/abundance sweep
Sweep one member's abundance and quantify how it changes community growth,
member growth, and target exchange. **Sensitivity analysis, not causality.**
- Required: `--model-dir` (or `--taxonomy`), `--member`, `--out`.
- Common: `--fractions`, `--target`, `--medium`, `--tradeoff-f`, `--recursive`.
- Outputs: `abundance_impact_summary.json`, `abundance_impact.csv`,
  `member_growth_by_abundance.csv`, `abundance_impact_plot.svg`.
- Key fields: `target_member_growth`, `target_member_exchange`,
  `community_target_exchange`, `target_influence_share` (selected member's
  absolute target flux / total absolute member target flux).
```bash
uv run cmig abundance-impact --model-dir models --member iML1515 \
  --fractions 0.1,0.25,0.5,0.75 --target ac --out runs/iML1515_ac_ratio
```

### `cmig gene-ko-search` — rank gene/reaction knockouts
Screen single-gene (or single-reaction) knockouts in a fixed consortium and
rank them by effect on target production relative to the un-knocked baseline.
- Required: `--model-dir` (or `--taxonomy`), `--members`, `--target`, `--out`.
- Common: `--member` (restrict to one member; omit to screen all →
  `screening_scope: all_members`), `--ko-level gene|reaction`, `--genes`,
  `--reactions`, `--gene-selection id|random`, `--seed`, `--max-genes`,
  `--jobs`, `--direction`, `--growth-fraction`, `--top-k`, `--recursive`.
- Outputs: `gene_ko_summary.json` (baseline, `warnings`, `ko_level`,
  `gene_selection`, `seed`, `n_genes_total`, ranked knockouts),
  `gene_ko_rankings.csv`, `gene_ko_plot.svg`, `gene_ko_plot.tiff`.
- `--max-genes 0` evaluates every target. Automatic reaction enumeration skips
  exchange and objective/biomass reactions; list them via `--reactions` to
  include. `--genes`/`--reactions` require `--member`. `--jobs > 1` gives
  results independent of `--jobs`, but the speedup depends on solver thread
  safety — validate on your environment.
```bash
uv run cmig gene-ko-search --model-dir models --members iML1515,iHN637 \
  --target but --max-genes 0 --top-k 20 --out runs/gene_ko_but
```

---

## Host-microbe family

> Read `references/scientific-validity.md` before any host run: biomass basis,
> interface-map review, and the weighted-metric unit rule are all mandatory.

### `cmig host-microbe-bigg` — direct host↔microbe coupling
Run direct BiGG-style host-microbe exchange coupling for Recon / Human-GEM style
host models plus a microbial model folder.
- Required: `--host`, `--model-dir` (or `--taxonomy`),
  `--microbial-biomass-gdw`, `--host-biomass-gdw`, `--biomass-basis-kind`,
  `--biomass-basis-source`, `--out`.
- Common: `--host-objective`, `--microbe-medium`, `--host-medium`,
  `--interface-map` (reviewed map), `--exclude-metabolites`,
  `--include-currency-metabolites`, `--recursive`.
- Outputs: `host_microbe_bigg_summary.json`, `microbial_secretion.csv`,
  `host_uptake.csv`, `microbe_to_host.csv`, `interaction_edges.csv`,
  `interaction_matrix.csv`, `member_contribution.csv`, `figure_manifest.json`,
  `interaction_circle.svg`, `interaction_heatmap.svg`, `interaction_bubble.svg`,
  `member_contribution.svg`.
```bash
export MICROBIAL_BIOMASS_GDW="<microbial dry mass in gDW>"
export HOST_BIOMASS_GDW="<host dry-mass basis in gDW>"
export BIOMASS_BASIS_SOURCE="<measurement record, Methods, or citation>"
uv run cmig host-microbe-bigg --host models_human/Human-GEM.xml \
  --model-dir models --recursive \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" --biomass-basis-kind measured \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" \
  --interface-map reviewed_host_interface_map.json --out runs/host_microbe
```

### `cmig host-search-bigg` — rank combinations against a host
Rank microbial combinations by host objective and/or target transfer.
- Required: same biomass-basis set as above, plus `--host`, `--model-dir`,
  `--out`.
- Common: `--min-size`, `--max-size`, `--target`, `--metric
  target_transfer|objective_value|weighted`, `--host-weight`,
  `--target-weight`, `--host-reference`, `--target-reference`,
  `--host-objective`, `--recursive`.
- Outputs: `host_search_summary.json`, `host_search_rankings.csv`,
  `host_search_plot.svg`.
- `--metric weighted` requires positive `--host-weight`, `--target-weight`,
  `--host-reference`, `--target-reference` (dimensionless score). Otherwise use
  `target_transfer` or `objective_value`.
```bash
uv run cmig host-search-bigg --host models_human/Human-GEM.xml \
  --model-dir models --target ac --metric target_transfer \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" --biomass-basis-kind measured \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" --out runs/host_search
```

### `cmig host-map` — build a reviewable interface map
Generate a candidate host↔microbe metabolite interface map from annotations and
normalized BiGG IDs. The output is a **starting point for human review**, then
passed back via `--interface-map`. Check `uv run cmig host-map --help` for exact
flags.

---

## Community solve

### `cmig solve` — MICOM taxonomy community solve
Run a user-provided MICOM taxonomy community solve.
- Required: `--taxonomy`, `--out`.
- Common: `--medium`, `--namespace-decisions`, `--allow-unknown-medium`,
  `--solver`, `--tradeoff-f`, `--targets`, `--fva`, `--fva-metabolites`,
  `--bounds`.
- Outputs: `manifest.json`, `nodes.parquet`, `edges.parquet`, `profile.parquet`.
```bash
uv run cmig solve --taxonomy taxonomy.csv \
  --medium medium_presets/western_diet.csv --solver gurobi \
  --tradeoff-f 0.5 --out runs/solve
```

---

## Dynamics: dFBA and spatial

### `cmig dfba` — well-mixed single-model dynamic FBA
Standard static-optimisation dFBA: each step updates uptake bounds from
extracellular concentrations, solves FBA, and advances biomass + metabolites.
- Required: `--model`, `--out`.
- Common: `--initial`, `--t-end` (default 5.0), `--dt`, `--initial-biomass`,
  `--vmax`, `--km`.
- Outputs: `dfba_summary.json`, `timecourse.parquet`, `dfba_timecourse.csv`,
  `dfba_timecourse.svg`, `dfba_timecourse.tiff`.
- If `--initial` is omitted, an aerobic default preset is used where available
  (`EX_glc__D_e=10`, `EX_o2_e=20`, `EX_ac_e=0`, `EX_lac__D_e=0`). Explicit
  `--initial` values are strict and must exist in the model.
```bash
uv run cmig dfba --model models/iML1515.xml --dt 0.1 --out runs/dfba_iML1515
```

### `cmig dfba-sensitivity` — audit dFBA numerical robustness
Run dFBA across integration steps and half-saturation constants; report every
run plus integration mass-balance residuals so a coarse-step result cannot
silently become the reported result. **Run this before trusting a dFBA
endpoint.**
```bash
uv run cmig dfba-sensitivity --model models/iML1515.xml \
  --dts 0.2,0.1,0.05 --kms 0.005,0.01,0.02 --out runs/dfba_sensitivity
```

### `cmig spatial-preview` — 2D medium gradient preview (design only)
Lightweight COMETS-inspired 2D source/sink diffusion preview. **Not** a spatial
community dFBA engine; it does not solve FBA per grid cell.
- Required: `--out`.
- Common: `--metabolite`, `--width`, `--height`, `--steps`, `--dt`,
  `--diffusion`, `--source-edge`, `--sink-edge`.
- Outputs: `spatial_summary.json`, `spatial_frames.csv`, `spatial_heatmap.svg`,
  `spatial_heatmap.tiff`.
```bash
uv run cmig spatial-preview --metabolite EX_glc__D_e --width 48 --height 48 \
  --source-edge left --sink-edge right --steps 120 --out runs/spatial_glucose
```

---

## Model QC and publication preflight

### `cmig model-review` — import review of a single GEM
Import and review a user-provided GEM before analysis.
```bash
uv run cmig model-review --model /path/to/model.xml --out runs/model_review
```

### `cmig model-quality` — batch quality audit
Audit model formulas, objective feasibility, gene/formula coverage, dead ends,
and optionally blocked reactions, independent of the biological workflow.
```bash
uv run cmig model-quality --model-dir models --recursive \
  --check-blocked-reactions --out runs/model_quality
```

### `cmig publication-benchmark` — combined audit in one manifest
Combines quality audit, a community solve, combination search, optional dFBA
sensitivity, and optional host coupling into one checksummed manifest. See
`docs/PUBLICATION_VALIDATION.md` for a fully specified real-model command.

---

## Inspection, reproducibility, utilities

- `cmig workflows --format json|text` — the GUI-to-CLI workflow map; read first.
- `cmig inspect-run --run-dir <dir> --format json|text` — machine-readable run
  inspection (kind, status, run hash, summary keys, artifacts).
- `cmig golden verify` — MICOM-version golden regression gate.
- `cmig solvers` — solver capability matrix (LP/QP/MILP/available).
- `cmig namespace-suggest` — draft an exchange-namespace decision for a model.
- `cmig sweep` — taxonomy-based parameter sweeps over solver, medium, members,
  abundance, and bounds (`sweep_summary.json`, `sweep.parquet`, `runs/`).
- `cmig sandbox-fixture` — preview or commit a reaction-bound edit on the
  bundled fixture community.
- `cmig version`, `cmig gui` — version string; launch the desktop GUI.

## Fixture demos

Deterministic demos that need no user models — useful for smoke tests and for
learning output shapes:
```bash
uv run cmig solve-fixture --solver gurobi --out runs/solve_fixture
uv run cmig search-fixture --out runs/search_fixture
uv run cmig host-fixture --out runs/host_fixture
uv run cmig dfba-fixture --out runs/dfba_fixture
uv run cmig stats-demo --out runs/stats_demo
```
