# CMIG — Community Metabolic Interaction GUI

CMIG (**Community Metabolic Interaction GUI**) is a desktop and command-line
platform for community metabolic interaction analysis. It uses user-provided
GEM files and delegates community FBA to MICOM, while CMIG owns the product
layer around model-pool search, host-microbe coupling, namespace checks,
reproducible manifests, tidy outputs, diagnostics, and publication-oriented
figures.

The workflow is intentionally local-file based: CMIG does not download or
curate external model catalogues. Prepare your microbial SBML/JSON/MAT models,
then load them through the GUI or CLI.

## Requirements

- Python 3.10+ and `uv`.
- Gurobi 12.x with a valid license for the full solver workflow
  (`osqp` is available for approximate QP-only community solves).
- macOS, Linux, or Windows with Qt support for the GUI.
- Optional: R 4.3.2 + the checked-in `renv.lock` for the R figure backend
  (matplotlib is the fallback).

CMIG pins `micom==0.39.0`.

## Installation

```bash
git clone https://github.com/jyryu3161/CMIG.git
cd CMIG
uv sync --extra engine --extra gui --extra render --extra stats

# check
uv run cmig version
uv run cmig solvers
```

For a headless (CLI-only) environment, drop `--extra gui --extra stats`.

## GUI mode

```bash
uv run cmig gui          # or: uv run cmig-gui;  add --lang ko for Korean
```

Primary tabs: **Models** (import/review a GEM), **Search** (best-producing
model combinations, strain growth, ratio sweeps, gene-KO ranking), **Host**
(host-microbe coupling), **Dynamics** (well-mixed dFBA, spatial preview),
**Graph** (interaction network), **Profile** (open completed runs — charts,
heatmap, comparison overlays). Less common tools (Community builder, Medium
editor, Sweep, Sandbox, Compare) sit behind `Show Advanced Tools`.

The GUI is a shell over the CLI: every run it launches is a normal CLI run
with a manifest, inspectable afterwards from either side.

## CLI mode

Every analysis is a subcommand of `cmig`; discover them from the tool itself:

```bash
uv run cmig workflows --format json     # machine-readable map of all analyses
uv run cmig <command> --help
```

Representative runs (all write a run directory with a reproducibility
manifest; check any run with `uv run cmig inspect-run --run-dir <dir>`):

```bash
# Solve a community from a taxonomy CSV on a defined medium
uv run cmig solve --taxonomy tax.csv \
  --medium medium_presets/gut_overlay_agora_western.csv \
  --assume-bigg-namespace --solver gurobi --out runs/solve

# Find the best 2-member producer combination for a target metabolite
uv run cmig search --model-dir models/ --target but --out runs/search

# Host-microbe coupling (BiGG-style host + microbial folder)
uv run cmig host-microbe-bigg --host Recon3D.xml --model-dir models/ \
  --target ac --microbial-biomass-gdw 57 --host-biomass-gdw 70 \
  --biomass-basis-kind literature --biomass-basis-source "..." \
  --assume-bigg-namespace --out runs/host

# Well-mixed dFBA for one model
uv run cmig dfba --model models/iML1515.xml.gz --t-end 8 \
  --close-untracked-uptake --out runs/dfba
```

Two flags matter scientifically on every medium-bearing command:
`--medium` **merges** onto the model's default environment, while
`--exact-medium` makes the file the **whole** environment; the manifest
records which mode produced the numbers.

## Documentation

- **Hands-on tutorial** (real commands + real outputs + GUI screenshots,
  produced offscreen): `docs/cmig_hands_on_tutorial.html`
- **Command reference tutorial** (all commands): `docs/cmig_workflow_tutorial.html`
- **User guide** (agent/automation CLI contract, full workflow catalogue,
  medium files, solver provenance, reading `edges.parquet`, scope and
  limitations, repository layout): `docs/USER_GUIDE.md`
- **Publication validation protocol**: `docs/PUBLICATION_VALIDATION.md`

## Development

```bash
uv run ruff check cmig tests
uv run mypy cmig
uv run pytest -q
uv run cmig golden verify            # frozen community_solve hash (needs solver)
uv run cmig golden verify-envelope   # workflow-manifest serialization gate (no solver)
```

If `verify-envelope` reports drift, the serialization changed and every
previously published workflow `run_hash` of the listed kinds now derives
differently from identical inputs. Re-bless only when that is intended
(`uv run python -m cmig.core.workflow_envelope_golden`) and record it as a
contract change.

## License

CMIG-authored code and documentation are licensed under Apache-2.0; see
`LICENSE` and `NOTICE`. External GEMs, Gurobi, Python/R dependencies, and
generated research outputs keep their own terms. The validation models under
`models/` are not Apache-licensed and are excluded from distributions; see
`THIRD_PARTY_NOTICES.md` and `models/MODEL_SOURCES.json`.
