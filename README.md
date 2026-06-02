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
- BiGG-ID direct host-microbe coupling for Recon/Human-GEM style host models and
  user-provided microbial models.
- Search and host-microbe GUI workflows with non-blocking jobs, result tables,
  SVG previews, and figure export.
- Interaction figures for host-microbe runs: circle, heatmap, bubble, and member
  contribution plots, plus source CSV tables.
- Search figures: ranking bar plot and growth-production scatter plot.
- Reproducible run manifests, run hashes, structured diagnostics, tidy Parquet
  outputs, FVA where supported, and regression tests.
- A simplified GUI shell: primary tabs are `Models`, `Search`, `Host`, and
  `Profile`; less common tools are behind `Show Advanced Tools`.

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
- `Host`: run host-microbe interaction analysis with a host model and microbial
  model folder.
- `Profile`: open and inspect completed CMIG runs.
- `Models`: import and review a user-provided GEM.

Use `Show Advanced Tools` only when you need the lower-level editor or preview
tabs.

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

### 3. Run host-microbe coupling

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

### 4. Run a MICOM taxonomy solve

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

### 5. Run fixture demos

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
