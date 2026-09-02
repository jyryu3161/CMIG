# CMIG Usage

How to install CMIG, run it from the graphical interface or the command line,
and work on it. This document is the practical companion to the
[README](../README.md); [USER_GUIDE.md](USER_GUIDE.md) is the reference manual
that documents every workflow, output schema and limitation in full.

Contents:

- [Requirements](#requirements)
- [Installation](#installation)
- [Graphical interface](#graphical-interface)
- [Command line](#command-line)
- [Media: the two flags that change the answer](#media-the-two-flags-that-change-the-answer)
- [Reading a run back](#reading-a-run-back)
- [Worked example: a butyrate-producing consortium](#worked-example-a-butyrate-producing-consortium)
- [Development](#development)
- [Getting help](#getting-help)

## Requirements

| | |
| --- | --- |
| Python | 3.10, 3.11 or 3.12, with [`uv`](https://docs.astral.sh/uv/) |
| Solver | Gurobi 12.x with a valid license for the full workflow. `osqp` covers approximate QP-only community solves; `cmig solvers` reports what is usable |
| Operating system | macOS, Linux or Windows. The graphical interface additionally needs Qt support |
| Figures (optional) | R 4.3.2 with the checked-in `renv.lock` for the R backend; matplotlib is the automatic fallback |

CMIG pins `micom==0.39.0`, because the community solver version is part of every
reproducibility record.

## Installation

```bash
git clone https://github.com/jyryu3161/CMIG.git
cd CMIG
uv sync --extra engine --extra gui --extra render --extra stats
```

Verify the install and see which solvers the environment actually offers:

```bash
uv run cmig version
uv run cmig solvers
```

The extras are separable. A headless server that only runs analyses needs
`--extra engine --extra render`; drop `--extra gui` and `--extra stats` there.
Without `--extra engine` the package still imports, so the pure-logic core can
be inspected on a machine with no solver at all.

## Graphical interface

```bash
uv run cmig gui              # equivalently: uv run cmig-gui
uv run cmig gui --lang ko    # Korean interface
```

| Tab | Purpose |
| --- | --- |
| **Models** | Import a GEM, review its structure, and see the namespace audit |
| **Search** | Best-producing model combinations, per-strain growth, abundance sweeps, gene-knockout ranking |
| **Host** | Host-microbe coupling and its interface map |
| **Dynamics** | Well-mixed dFBA and the spatial medium preview |
| **Graph** | Interaction network of a completed community solve |
| **Profile** | Open a finished run: charts, heatmap and comparison overlays |

Less common tools — community builder, medium editor, parameter sweep,
constraint sandbox and scenario compare — sit behind **Show Advanced Tools**.

The interface is a shell over the command line: every run it launches is an
ordinary CLI run that writes an ordinary manifest, so anything started in the
GUI can be inspected, re-run or scripted afterwards, and vice versa.

## Command line

Every analysis is a subcommand. Discover them from the tool itself rather than
from a list that can go stale:

```bash
uv run cmig workflows --format text   # readable catalogue
uv run cmig workflows                 # JSON, for scripting and agents
uv run cmig <command> --help
```

Representative runs. Each writes a run directory containing its outputs and a
reproducibility manifest.

```bash
# Fetch a model pool from AGORA2 — the only commands that reach the network
uv run cmig agora2-list --genus Roseburia --limit 5
uv run cmig agora2-fetch --genus Roseburia,Faecalibacterium \
  --one-per-genus --format json --out models/agora2_pool

# Check that a medium can actually support the pool, before trusting any ranking
uv run cmig medium-gap --model-dir models/agora2_pool \
  --medium medium_presets/gut_overlay_agora_western.csv --exact-medium \
  --allow-unknown-medium --out runs/medium_gap

# Community solve from a taxonomy CSV on a defined medium
uv run cmig solve --taxonomy tax.csv \
  --medium medium_presets/gut_overlay_agora_western.csv --exact-medium \
  --assume-bigg-namespace --solver gurobi --out runs/solve

# Rank model combinations by production of a target metabolite
uv run cmig search --model-dir models/agora2_pool --target but \
  --min-size 3 --max-size 3 --strategy exhaustive --out runs/search

# Host-microbe coupling (BiGG-style host plus a microbial folder). The biomass
# basis is mandatory and must be provenanced: coupling fluxes are meaningless
# without the gDW each side is expressed per.
uv run cmig host-microbe-bigg --host data/gems/Recon3D.xml --model-dir models/ \
  --microbial-biomass-gdw 57 --host-biomass-gdw 70 \
  --biomass-basis-kind literature \
  --biomass-basis-source "Sender et al. 2016, PLoS Biol, doi:10.1371/journal.pbio.1002533" \
  --interface-map runs/host_map/host_interface_map.json --out runs/host

# Well-mixed dFBA for one model
uv run cmig dfba --model models/iML1515.xml.gz --t-end 8 \
  --close-untracked-uptake --out runs/dfba
```

### Exit codes

`$?`, not the presence of output files, is the verdict — analyses write
artifacts even when the science fails, so that a failure is diagnosable.

| Code | Meaning |
| --- | --- |
| `0` | The analysis ran and the scientific solve succeeded |
| `2` | Input error: a bad medium spec, an unresolvable identifier, a missing file. No analysis was attempted |
| `3` | Artifacts were written but the **scientific solve did not succeed**. `--allow-failed-run` forces `0` without making the run a result |

## Media: the two flags that change the answer

Two flags on every medium-bearing command decide what the organism's environment
actually is, and they routinely change the conclusion:

- `--medium FILE` **merges** the declared nutrients onto whatever the model's own
  SBML already leaves open. Many published GEMs ship with every exchange open, so
  a merged medium is often not a constraint at all.
- `--exact-medium` makes the file the **whole** environment: every other boundary
  supplier is closed first, and the closure is measured rather than assumed.

The manifest records which mode produced the numbers. Prefer `--exact-medium`
for anything you intend to report, and run `cmig medium-gap` first if a solve
comes back at zero growth — it names the nutrients the diet is missing and
distinguishes them from model-internal reactions a diet file cannot supply.

## Reading a run back

```bash
uv run cmig inspect-run --run-dir runs/solve
uv run cmig inspect-run --run-dir runs/solve --format json
```

`inspect-run` describes a run rather than re-judging it. It reports the run
status together with `status_source`, which names where that verdict came from,
so a disagreement between a summary and its manifest is visible instead of
silently resolved. `unknown` is a real answer and must never be read as a pass.
The full status vocabulary and its guarantees are in
[USER_GUIDE.md](USER_GUIDE.md#exit-codes).

## Worked example: a butyrate-producing consortium

Finding the three-member combination from a model pool that produces the most
butyrate, end to end:

```bash
# 1. A diverse pool of named isolates, as fast-loading cobra JSON
uv run cmig agora2-fetch \
  --genus Faecalibacterium,Roseburia,Eubacterium,Anaerostipes,Coprococcus,Butyrivibrio \
  --exclude-match "uncultured_|_ERR[0-9]|_sp_" \
  --one-per-genus --format json --out models/agora2_pool

# 2. Confirm the diet supports the pool; supplement it if not
uv run cmig medium-gap --model-dir models/agora2_pool \
  --medium medium_presets/gut_overlay_agora_western.csv --exact-medium \
  --allow-unknown-medium --out runs/medium_gap

# 3. Rank every 3-member combination
uv run cmig search --model-dir models/agora2_pool --target but \
  --min-size 3 --max-size 3 --strategy exhaustive --top-k 20 \
  --medium runs/medium_gap/medium_gap_supplemented.csv --exact-medium \
  --out runs/butyrate_3
```

Step 2 writes `medium_gap_supplemented.csv` only when the diet actually needed
supplementing; if every strain already grew, use the original medium file in
step 3. Rows the gap analysis added are marked `row_role: gap_supplement` and
are not part of the published diet — keep that distinction in any write-up.

Two things decide whether the ranking means anything. `--strategy auto` is
exhaustive only while the number of combinations stays at or below
`--exhaustive-max` (default 100) and switches to a genetic algorithm above it,
so pass `--strategy exhaustive` when you need a certified optimum — choosing 3
of 20 models is already 1,140 combinations. And a consortium that cannot grow is
quarantined rather than ranked, so an empty or short ranking is a statement about
the medium, not about the target.

[USER_GUIDE.md](USER_GUIDE.md#2-search-a-microbial-model-pool) covers the search
strategies, the two-step prescreen for larger pools and its cross-feeding blind
spot.

## Development

```bash
uv run ruff check cmig tests         # lint
uv run mypy cmig                     # strict type check
uv run pytest                        # full suite (randomized order)
```

Two reproducibility gates guard contracts that ordinary tests cannot see:

```bash
uv run cmig golden verify            # frozen community-solve hash (needs a solver)
uv run cmig golden verify-envelope   # manifest serialization gate (no solver needed)
```

If `verify-envelope` reports drift, the manifest serialization changed and every
previously published `run_hash` of the listed workflow kinds now derives
differently from identical inputs. That is a contract change: re-bless it only
when it is intended, with
`uv run python -m cmig.core.workflow_envelope_golden`, and record it in
[CHANGELOG.md](../CHANGELOG.md).

Before publishing results, work through
[PUBLICATION_VALIDATION.md](PUBLICATION_VALIDATION.md).

## Getting help

- `uv run cmig <command> --help` for any command's flags and their meaning.
- [USER_GUIDE.md](USER_GUIDE.md) for the reference manual, including the scope
  and limitations section — read it before reporting a modelling result.
- [Issue tracker](https://github.com/jyryu3161/CMIG/issues) for bugs and feature
  requests. A run directory's `manifest.json` is the most useful thing to attach.
