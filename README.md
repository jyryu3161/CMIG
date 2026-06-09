# CMIG

CMIG is a desktop and command-line platform for community metabolic interaction
analysis. It uses user-provided GEM files and delegates community FBA to MICOM,
while CMIG owns the product layer around model-pool search, host-microbe
coupling, namespace checks, reproducible manifests, tidy outputs, diagnostics,
and publication-oriented figures.

The current workflow is intentionally local-file based. CMIG does not download,
curate, or auto-select external model catalogues. Prepare the microbial SBML,
JSON, or MAT models yourself, then load them through the GUI or CLI.

## What Is Implemented

- MICOM-backed community solve through a single engine wrapper.
- User model-pool search, including combinations such as "choose 2 models from
  a folder and maximize butyrate or acetate production".
- Per-strain growth reports comparing each model alone with its growth inside
  the full MICOM community.
- One-member abundance/ratio sweeps that quantify how changing a selected
  strain's abundance changes community growth, member growth, target exchange,
  and target influence share.
- BiGG-ID direct host-microbe coupling for Recon/Human-GEM style host models and
  user-provided microbial models.
- Search and host-microbe GUI workflows with non-blocking jobs, result tables,
  SVG previews, and figure export.
- Interaction figures for host-microbe runs: circle, heatmap, bubble, and member
  contribution plots, plus source CSV tables.
- Search figures: ranking bar plot and growth-production scatter plot.
- Well-mixed dFBA for a user-provided SBML model, with timecourse tables and
  SVG/TIFF figures.
- A lightweight COMETS-inspired 2D spatial medium preview for source/sink and
  diffusion design without adding a Java COMETS dependency.
- Reproducible run manifests, run hashes, structured diagnostics, tidy Parquet
  outputs, FVA where supported, and regression tests.
- A simplified GUI shell: primary tabs are `Models`, `Search`, `Host`,
  `Dynamics`, and `Profile`; less common tools are behind `Show Advanced Tools`.

## Requirements

- Python 3.10 or newer.
- `uv` for environment and dependency management.
- A Gurobi installation and valid license for the default full solver workflow.
- macOS, Linux, or Windows with Qt support for the GUI.

CMIG pins `micom==0.39.0` and expects Gurobi 12.x through `gurobipy>=12,<13`.
The `osqp` solver path is available for approximate QP-only provenance in core
community solves, but Gurobi is required for the current host-microbe and model
pool product commands.

## Installation

Clone the repository and install the full local environment:

```bash
git clone https://github.com/jyryu3161/CMIG.git
cd CMIG
uv sync --extra engine --extra gui --extra render --extra stats
```

For a smaller headless environment without GUI/statistics extras:

```bash
uv sync --extra engine --extra render
```

Check the installation:

```bash
uv run cmig version
uv run cmig solvers
uv run ruff check cmig tests
uv run mypy cmig
uv run pytest -q
```

## Launch The GUI

CMIG currently exposes the GUI as a Python entry point:

```bash
uv run python - <<'PY'
from PySide6.QtWidgets import QApplication
from cmig.gui.app import build_main_window

app = QApplication([])
window = build_main_window(lang="en")
window.resize(1500, 950)
window.show()
app.exec()
PY
```

The default GUI is focused on the main user workflows:

- `Search`: find high-producing microbial model combinations from a folder.
  It also includes strain growth reports, ratio-impact sweeps, and gene-KO
  ranking for selected model pools.
- `Host`: run host-microbe interaction analysis with a host model and microbial
  model folder.
- `Dynamics`: run single-model well-mixed dFBA and preview spatial medium
  gradients.
- `Profile`: open and inspect completed CMIG runs.
- `Models`: import and review a user-provided GEM.

Use `Show Advanced Tools` only when you need the lower-level editor or preview
tabs.

For a scenario-based installation and workflow tutorial, open
`docs/cmig_workflow_tutorial.html` in a browser.

## CLI For LLM Agents And Automation

Every working GUI analysis surface has a matching CLI workflow. Agents should
start by reading the machine-readable workflow map:

```bash
uv run cmig workflows --format json
```

The output maps GUI surfaces such as `Search / Find Best Model Combination`,
`Host / Run Host-Microbe`, and `Dynamics / Run dFBA` to the equivalent `cmig`
command, required arguments, useful options, expected artifacts, and one
copyable example command.

After a run finishes, inspect the output directory in a stable JSON format:

```bash
uv run cmig inspect-run --run-dir runs/search_butyrate --format json
```

`inspect-run` detects known CMIG summaries such as `search_summary.json`,
`host_microbe_bigg_summary.json`, `dfba_summary.json`, `spatial_summary.json`,
and `manifest.json`, then reports the workflow kind, status, run hash when
available, summary keys, and artifacts. This is the CLI counterpart to opening a
run in the GUI Profile/Open Run view.

## Typical CLI Workflows

### 1. Review a user-provided model

```bash
uv run cmig model-review \
  --model /path/to/model.xml \
  --out runs/model_review
```

### 2. Search a microbial model pool

Example: choose the best 2-model combinations from a folder for butyrate
production.

```bash
uv run cmig search \
  --model-dir /path/to/microbial_models \
  --target but \
  --min-size 2 \
  --max-size 2 \
  --top-k 10 \
  --strategy auto \
  --out runs/search_butyrate
```

Useful outputs:

- `search_summary.json`
- `search_rankings.csv`
- `search_member_matrix.csv`
- `pool_diagnostics.csv`
- `search_plot.svg`
- `search_scatter.svg`

Use `--recursive` if your model pool is organized as subfolders, for example
`strainA/model.xml`, `strainB/model.xml`.

### 2b. Rank gene or reaction knockouts in a model combination

Screen single-gene (or single-reaction) knockouts in a fixed consortium and rank
them by their effect on target production, relative to the un-knocked baseline.

```bash
uv run cmig gene-ko-search \
  --model-dir /path/to/microbial_models \
  --members iML1515,iHN637 \
  --target but \
  --max-genes 0 \
  --top-k 20 \
  --out runs/gene_ko_but
```

Key options:

- `--member`: knock out genes in one named member only. Omit it to screen every
  `--members` model (`screening_scope: all_members`).
- `--ko-level gene|reaction`: knock out genes through their GPR (default), or
  knock out reactions directly. Use `--reactions` with `--ko-level reaction` (and
  `--genes` with the gene level) to evaluate an explicit id list; both require
  `--member`. Automatic reaction enumeration skips exchange reactions and the
  objective/biomass reaction (knocking those out is not an informative metabolic
  perturbation); list them with `--reactions` if you want them included.
- `--gene-selection id|random` and `--seed`: when targets are not listed
  explicitly, pick them in id order (default) or as a deterministic random
  sample. Either way, if `--max-genes` truncates the set, the run records an
  explicit `warnings` entry and `n_genes_total` so a screen never silently
  inspects an arbitrary subset. `--max-genes 0` evaluates every target.
- `--jobs N`: evaluate knockouts with `N` worker threads (default `1`). Results
  are independent of `--jobs`; the speedup depends on your solver's thread
  safety, so validate on your environment before relying on `--jobs > 1`.

Useful outputs:

- `gene_ko_summary.json` (baseline, `warnings`, `ko_level`, `gene_selection`,
  `seed`, `n_genes_total`, ranked knockouts)
- `gene_ko_rankings.csv`
- `gene_ko_plot.svg`
- `gene_ko_plot.tiff`

The figure shows each knockout's target-flux delta versus baseline, colored by
whether the knockout improves or reduces the target, with failed evaluations
marked and the baseline flux, evaluated-of-total count, and selection method in
the subtitle.

### 3. Estimate strain-specific growth

Use this when you want to check expected growth for each microbial model, both
alone and inside the full MICOM community.

```bash
uv run cmig strain-growth \
  --model-dir /path/to/microbial_models \
  --out runs/strain_growth
```

Useful outputs:

- `strain_growth_summary.json`
- `strain_growth.csv`
- `strain_growth_plot.svg`
- `strain_growth_plot.tiff`

Interpretation:

- `single_growth` is the FBA growth of the individual GEM.
- `community_member_growth` is the member growth rate after MICOM community
  construction and cooperative tradeoff.
- `abundance` is the member abundance used by the community model.

### 4. Sweep one strain ratio/abundance

Use this when a mixed community already exists and you want to test whether
raising one member's relative abundance changes its influence on a target
metabolite.

```bash
uv run cmig abundance-impact \
  --model-dir /path/to/microbial_models \
  --member iML1515 \
  --fractions 0.1,0.25,0.5,0.75 \
  --target ac \
  --out runs/iML1515_ac_ratio
```

CMIG applies each fraction by setting the selected member's abundance to that
value and rescaling the remaining members to fill the rest of the community.
MICOM then recomputes community growth, member growth, and exchange fluxes.
This is a sensitivity analysis under the same model set and medium, not proof
of ecological causality.

Useful outputs:

- `abundance_impact_summary.json`
- `abundance_impact.csv`
- `member_growth_by_abundance.csv`
- `abundance_impact_plot.svg`
- `abundance_impact_plot.tiff`

Key fields:

- `target_member_growth`: growth of the selected member at each abundance.
- `target_member_exchange`: selected member's exchange flux for `--target`.
- `community_target_exchange`: total community exchange flux for `--target`.
- `target_influence_share`: selected member's absolute target flux divided by
  total absolute member target flux.

### 5. Run host-microbe coupling

Example with a Recon/Human-GEM style host model and a microbial model folder:

```bash
uv run cmig host-microbe-bigg \
  --host /path/to/Recon3D.xml \
  --model-dir /path/to/microbial_models \
  --recursive \
  --out runs/host_microbe
```

Useful outputs:

- `host_microbe_bigg_summary.json`
- `microbial_secretion.csv`
- `host_uptake.csv`
- `microbe_to_host.csv`
- `interaction_edges.csv`
- `interaction_matrix.csv`
- `member_contribution.csv`
- `figure_manifest.json`
- `interaction_circle.svg`
- `interaction_heatmap.svg`
- `interaction_bubble.svg`
- `member_contribution.svg`

The direct coupling assumes compatible BiGG-style exchange identifiers. CMIG does
not perform Recon-specific interface curation or external model import.

### 6. Run a MICOM taxonomy solve

If you already have a MICOM-compatible taxonomy CSV:

```bash
uv run cmig solve \
  --taxonomy /path/to/taxonomy.csv \
  --medium medium_presets/western_diet.csv \
  --solver gurobi \
  --tradeoff-f 0.5 \
  --out runs/solve
```

Useful outputs include `nodes.parquet`, `edges.parquet`, `profile.parquet`, and
`manifest.json`.

### 7. Run well-mixed dFBA

CMIG's dFBA implementation follows the standard static optimization approach:
at each time step, uptake bounds are updated from extracellular concentrations,
FBA is solved, and biomass plus extracellular metabolites are advanced in time.

```bash
uv run cmig dfba \
  --model /path/to/model.xml \
  --dt 0.1 \
  --out runs/dfba_user_model
```

If `--initial` is omitted, CMIG uses an aerobic default preset where available:
`EX_glc__D_e=10`, `EX_o2_e=20`, `EX_ac_e=0`, and `EX_lac__D_e=0`. Explicit
`--initial` values are strict and must exist in the model. The default horizon is
`--t-end 5.0`, so the generated figure is an analysis preview rather than a
very short smoke-test trace.

Useful outputs:

- `dfba_summary.json`
- `timecourse.parquet`
- `dfba_timecourse.csv`
- `dfba_timecourse.svg`
- `dfba_timecourse.tiff`

### 8. Preview a spatial medium gradient

This is a lightweight design tool inspired by COMETS spatial layouts. It is not
a full spatial community dFBA engine. Use it to check source/sink and diffusion
settings before running heavier analyses.

```bash
uv run cmig spatial-preview \
  --metabolite EX_glc__D_e \
  --width 48 \
  --height 48 \
  --source-edge left \
  --sink-edge right \
  --steps 120 \
  --out runs/spatial_glucose_preview
```

Useful outputs:

- `spatial_summary.json`
- `spatial_frames.csv`
- `spatial_heatmap.svg`
- `spatial_heatmap.tiff`

### 9. Run fixture demos

```bash
uv run cmig solve-fixture --solver gurobi --out runs/solve_fixture
uv run cmig search-fixture --out runs/search_fixture
uv run cmig host-fixture --out runs/host_fixture
uv run cmig dfba-fixture --out runs/dfba_fixture
uv run cmig stats-demo --out runs/stats_demo
```

## Medium Files

Medium files can be CSV or JSON. Built-in examples live in `medium_presets/`.
For user commands, pass them with `--medium`, `--host-medium`, or
`--microbe-medium` depending on the workflow.

## Solver Provenance

- `gurobi`: canonical full-flux workflow.
- `osqp`: QP-only approximate provenance for supported community solve paths.
- Community FVA and product host/search workflows currently require Gurobi.

CMIG records solver choice and flux provenance in run outputs so cached or
published results can be interpreted correctly.

## Development

Run the standard checks:

```bash
uv run ruff check cmig tests
uv run mypy cmig
uv run pytest -q
```

Golden-version gate:

```bash
uv run cmig golden verify
```

The test suite includes headless core tests, MICOM-backed tests, solver
provenance tests, GUI offscreen smoke tests, and real workflow regressions.

## Scope And Limitations

- CMIG expects users to provide their own GEM files.
- CMIG does not automatically download AGORA, VMH, Recon, Human-GEM, or BiGG
  model collections.
- Host-microbe coupling is implemented for BiGG-style direct exchange matching.
- dFBA currently supports well-mixed single-model simulations. Full spatial
  community dFBA with biomass propagation, extracellular reactions, and
  evolution-like COMETS modules is out of scope for the current CMIG engine.
- `spatial-preview` models diffusion/source/sink media design only; it does not
  solve FBA on every grid cell.
- The GUI has been tested in offscreen mode; final manual desktop QA may still
  be useful before distribution.
- README examples assume Gurobi is installed and licensed.

## Repository Layout

- `cmig/core/`: domain logic and solver-facing workflows.
- `cmig/service/`: application service facade and non-blocking job runner.
- `cmig/gui/`: PySide6 desktop UI.
- `cmig/cli/`: command-line entry point.
- `cmig/io/`: run output, checksums, manifests, and import helpers.
- `cmig/render/`: figure rendering helpers.
- `tests/`: regression and workflow tests.
- `medium_presets/`: example medium definitions.
- `docs/`: design and project-management notes.

## License

The project license is currently marked as TBD in `pyproject.toml`.
