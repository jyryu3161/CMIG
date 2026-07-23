---
name: cmig-metabolic-analysis
description: >-
  Operate CMIG (Community Metabolic Interaction GUI) to run and interpret
  microbial community metabolic interaction analyses. Use this skill whenever
  the task involves CMIG or its `cmig` CLI/GUI, MICOM-backed community FBA,
  ranking GEM/SBML model-pool combinations for a target metabolite (e.g.
  butyrate / acetate / propionate / short-chain fatty-acid production or
  uptake), host-microbe metabolic coupling, per-strain vs community growth,
  one-member abundance/ratio sweeps, single-gene or reaction knockout ranking,
  well-mixed dFBA, spatial medium previews, or inspecting/reproducing CMIG run
  outputs and manifests. Trigger even when the user does not say "CMIG" by
  name but clearly wants microbial community metabolic modelling, cross-feeding
  analysis, community FBA, GEM model-pool search, host-microbe interaction, or
  metabolite-production optimisation over cobra/SBML models — and for Korean
  requests such as 미생물 군집 대사 분석, 대사 상호작용, 균주 조합 탐색,
  숙주-미생물 상호작용, 대사물질 생산 최적화. This skill routes the request to
  the correct `cmig` workflow AND enforces the scientific-validity guardrails
  (biomass basis, reviewed interface maps, solver provenance, sensitivity
  audits) that keep results publication-defensible.
---

# CMIG — Community Metabolic Interaction Analysis

CMIG is a desktop + CLI platform for **community metabolic interaction
analysis**. It delegates community FBA to **MICOM** and owns the product layer
around model-pool search, host-microbe coupling, namespace checks, reproducible
manifests, tidy outputs, diagnostics, and publication-oriented figures.

Your job with this skill is to **operate CMIG correctly**, not to re-implement
metabolic modelling by hand. CMIG already encodes the hard scientific choices
as explicit, mandatory flags. The failure mode to avoid is producing a number
that *looks* like a result but silently skipped a validity guardrail (wrong
biomass basis, unreviewed interface map, approximate solver reported as exact,
an un-audited dFBA endpoint). Those outputs are not publishable, and the point
of this skill is to keep every run defensible.

## Operating principle: discover → run → verify

CMIG is designed to be driven by agents. Always follow this loop instead of
guessing command names or flags.

1. **Discover.** Read the machine-readable workflow map first:
   ```bash
   uv run cmig workflows --format json
   ```
   It maps every GUI analysis surface (e.g. `Search / Find Best Model
   Combination`, `Host / Run Host-Microbe`, `Dynamics / Run dFBA`) to the exact
   `cmig` command, required args, common options, expected artifacts, and one
   copyable example. For any command, `uv run cmig <command> --help` is the
   authoritative flag list. Treat these two as ground truth over your memory.
2. **Run** the chosen workflow with an explicit `--out runs/<name>` directory.
3. **Verify.** After every run, inspect the output directory in a stable form:
   ```bash
   uv run cmig inspect-run --run-dir runs/<name> --format json
   ```
   This reports the workflow kind, status, run hash (when present), summary
   keys, and artifacts — the CLI counterpart to opening a run in the GUI
   Profile view. Report `status`, the run hash, and the key summary numbers
   back to the user; do not just say "done".

CMIG is intentionally **local-file based**: it never downloads, curates, or
auto-selects external model catalogues (AGORA / VMH / Recon / Human-GEM /
BiGG). The user supplies their own SBML / JSON / MAT GEMs. If a request assumes
auto-download, correct it and ask for the local model directory.

## Intent → workflow routing

Match what the user wants to the workflow. Full commands, args, and outputs are
in `references/workflows.md`; read it before assembling a non-trivial command.

| The user wants to…                                              | Command |
| --------------------------------------------------------------- | ------- |
| Rank model combinations that best produce/consume a metabolite  | `cmig search` |
| Compare each strain's growth alone vs inside the community      | `cmig strain-growth` |
| Test how one member's abundance changes a target/growth         | `cmig abundance-impact` |
| Rank single-gene (or reaction) knockouts in a fixed consortium  | `cmig gene-ko-search` |
| Couple a host GEM to microbial secretion/uptake (BiGG-style)    | `cmig host-microbe-bigg` |
| Rank microbial combinations by host objective + target transfer | `cmig host-search-bigg` |
| Build a candidate host↔microbe interface map for review         | `cmig host-map` |
| Solve a MICOM taxonomy community directly                       | `cmig solve` |
| Run well-mixed single-model dynamic FBA                         | `cmig dfba` |
| Check a dFBA endpoint's numerical robustness                    | `cmig dfba-sensitivity` |
| Preview a 2D source/sink medium gradient (design only)          | `cmig spatial-preview` |
| Review / QC a user-provided GEM before analysis                 | `cmig model-review`, `cmig model-quality` |
| Run the combined publication audit in one manifest              | `cmig publication-benchmark` |
| Inspect or reproduce a finished run                             | `cmig inspect-run`, `cmig golden verify` |

When the goal is unclear, ask which metabolite, which model directory, and
whether this is an exploratory check or a publication run — the answer changes
which guardrails are mandatory (see below).

## Critical decision points (중요한 지점)

These are the points where a run quietly becomes scientifically invalid. CMIG
enforces most of them with required flags; your job is to set them correctly
and to *explain the choice in the result*, not to route around them. Depth and
exact flags are in `references/scientific-validity.md` — read it before any
host-microbe or publication run.

- **Host-microbe biomass basis is mandatory — there is no default.** Microbial
  and host-specific fluxes cannot be compared or transferred without their gDW
  scaling assumptions, so `host-microbe-bigg` and `host-search-bigg` require
  *both* `--microbial-biomass-gdw` and `--host-biomass-gdw` (positive),
  `--biomass-basis-kind`, and `--biomass-basis-source`. Use `measured` or
  `literature` for real study results. `--biomass-basis-kind validation` exists
  only for software tests and **explicitly marks the result "not
  publication-ready"** — never present a `validation` run as a scientific
  finding.
- **Annotation-based interface maps are suggestions, not truth.** CMIG matches
  metabolites by annotation and normalized BiGG IDs, but those are computational
  guesses. For any publication host-microbe run, generate a candidate map with
  `cmig host-map`, have it reviewed, and pass the reviewed file via
  `--interface-map`. Do not treat an auto-generated mapping as final.
- **Never add quantities with different units.** `host-search-bigg --metric
  weighted` refuses to combine host objective and target transfer unless you
  give positive, finite `--host-weight`, `--target-weight`, `--host-reference`,
  and `--target-reference`, so the score is dimensionless. If no defensible
  reference scales exist, use `--metric target_transfer` or `objective_value`
  instead — do not fabricate reference values to satisfy the weighted metric.
- **Solver provenance changes what the numbers mean.** `gurobi` is the
  canonical full-flux workflow. `osqp` is QP-only *approximate* provenance for
  supported community solves. Community FVA and the host/search product
  workflows currently require Gurobi. Always report which solver produced a
  number; never present an `osqp` approximate result as an exact flux.
- **A dFBA endpoint is not trustworthy until its sensitivity is audited.** The
  reported endpoint can depend on the integration step `--dt` and the uptake
  half-saturation constant `--km`. Before interpreting a dFBA result, run
  `cmig dfba-sensitivity` across a range of `--dts` and `--kms` so a
  coarse-step artifact cannot silently become the reported result. Also note
  `--initial` values are strict and must exist in the model.
- **Knockout screens must not silently sample a subset.** In
  `gene-ko-search`, `--max-genes 0` evaluates every target. If `--max-genes`
  truncates the set, CMIG records a `warnings` entry and `n_genes_total`, and
  `--gene-selection id|random` plus `--seed` make truncation reproducible.
  Prefer `--max-genes 0` for a complete screen; if you cap it, surface the
  warning and the evaluated-of-total count.
- **`spatial-preview` is a design tool, not a spatial FBA engine.** It models
  diffusion / source / sink medium layout only; it does **not** solve FBA on
  each grid cell. Never describe its output as spatial community dFBA results.
- **Abundance sweeps are sensitivity, not causality.** `abundance-impact`
  rescales one member's abundance under the same models and medium. Report it as
  a sensitivity analysis, not proof of ecological causation.

## Environment notes

- Commands run through `uv` (e.g. `uv run cmig ...`). The engine extra provides
  MICOM; the GUI, render, and stats extras are optional (`uv sync --extra
  engine --extra gui --extra render --extra stats`).
- The default full workflow expects **Gurobi 12.x** with a valid license and
  pins `micom==0.39.0`. Check availability with `uv run cmig solvers`.
- Reproducibility is a first-class feature: runs emit manifests and run hashes;
  `cmig inspect-run` reads them back, and `cmig golden verify` is the
  MICOM-version regression gate. Preserve `--out` directories you want to cite.

## References

- `references/workflows.md` — per-command reference: purpose, required args,
  useful options, key outputs, and a copyable example for every workflow.
- `references/scientific-validity.md` — the guardrails above in depth, with the
  rationale and the exact flags, for host-microbe and publication runs.
- `references/outputs.md` — how to read run directories, `inspect-run` kinds,
  summary/figure artifacts, and how to reproduce or cite a run.
