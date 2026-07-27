# CMIG — Community Metabolic Interaction GUI

CMIG (**Community Metabolic Interaction GUI**) is a desktop and command-line
platform for community metabolic interaction analysis. It uses user-provided
GEM files and delegates community FBA to MICOM, while CMIG owns the product
layer around model-pool search, host-microbe coupling, namespace checks,
reproducible manifests, tidy outputs, diagnostics, and publication-oriented
figures.

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
- R 4.3.2 plus the checked-in `renv.lock` is optional for the R figure backend;
  matplotlib remains the single-profile fallback.

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

Launch the installed GUI through either entry point:

```bash
uv run cmig gui
# equivalent dedicated entry point
uv run cmig-gui
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
and `manifest.json`, then reports the workflow kind, status, `run_hash`,
`result_digest`, `artifact_integrity`, summary keys, and artifacts. This is the
CLI counterpart to opening a run in the GUI Profile/Open Run view.

### Exit codes

Analysis commands write artifacts even when the science fails, so that a failure
is diagnosable. That makes `$?` — not the presence of output files — the verdict:

| Code | Meaning |
| ---- | ------- |
| `0` | ran, and the scientific solve succeeded (or `--allow-failed-run` was passed) |
| `2` | **input** error — bad medium spec, aliased medium namespaces, a medium id with no exchange counterpart |
| `3` | artifacts written but **the scientific solve did not succeed**; also `inspect-run` when `artifact_integrity` is `mismatch` |

`--allow-failed-run` forces `0`, without making the run a result. It is **not**
universal: it exists on `solve`, `search`, `strain-growth`, `abundance-impact`,
`gene-ko-search`, `sweep`, `dfba-sensitivity` and the three host commands, and is
**rejected** by `dfba`, `model-quality`, `publication-benchmark`, `spatial-preview`
and `model-review`, where it is an argparse error:

```
$ uv run cmig dfba --model models/iHN637.xml --allow-failed-run --out runs/x
cmig: error: unrecognized arguments: --allow-failed-run       # exit 2
```

That is also exit `2`, so an unexpected `2` right after adding the flag means the
flag, not your medium file.

`inspect-run` **describes** a run rather than re-judging it: it exits non-zero only
on `artifact_integrity: mismatch`, so `$?` of the analysis command is the verdict.

Its payload (`schema_version 1.2`) reports `status` together with
**`status_source`**, which names where the verdict came from — `manifest`,
`summary`, `derived`, `acceptance.interpretable`, `host_map_counts`,
`solve.status`, `namespace.blocked`, `inference.status`, `no_status_signal`, or
`unknown`. Three things follow:

- **`unknown` is a real answer.** A recognised summary that records no run-level
  outcome reports `status: unknown` with `status_source: no_status_signal` rather
  than inventing `ok`. `stats-demo` is the clean example — it has no pass/fail
  dimension. Never read `unknown` as a pass.
- **`status` can legitimately disagree with `manifest.status`.** A run that stamps
  itself `acceptance.interpretable: false` vetoes a rosier manifest tier; the veto
  may only make the verdict worse, and it owns `status_source` so you can see which
  signal condemned the run.
- **The status vocabulary is not closed.** `infeasible` and `stalled` still reach
  `status` verbatim, because the legacy alias table maps only `optimal` and
  `completed` to `ok`. Do not write a gate that matches just
  `ok`/`degraded`/`failed`/`unknown`; treat anything unrecognised as not-ok.

### The two fingerprints

- **`run_hash` certifies the INPUTS.** Identical inputs give an identical hash. It
  does not certify the answer — the medium fix below changed published numbers
  under identical hashes by design.
- **`result_digest` certifies the ANSWER**: it fingerprints the artifact bytes the
  run wrote, including figures. `inspect-run` recomputes it and reports
  `artifact_integrity`. A mismatch flips `status` to `failed` and exits `3`.

`result_digest` comes from the workflow manifest (13 workflow kinds).
`cmig solve` writes the legacy solve manifest and therefore has no
`result_digest` — `not recorded` on a fresh solve is expected.

When the environment changes, run **both** gates:

```bash
uv run cmig golden verify            # numeric regression (MICOM / solver versions)
uv run cmig golden verify-envelope   # workflow-manifest serialization drift
```

## Agentic Skill For Claude Code

CMIG ships a Claude Code **agent skill** so that an assistant working in this
repository automatically knows how to drive CMIG correctly — which `cmig`
workflow matches a request, and the scientific-validity guardrails that keep a
run publication-defensible (mandatory host-microbe biomass basis, reviewed
interface maps, solver provenance, and dFBA sensitivity audits).

- The skill lives at `.claude/skills/cmig-metabolic-analysis/`. Claude Code
  loads it automatically for sessions in this repo; no setup is required.
- `SKILL.md` holds the trigger description, the intent→command routing table,
  and the critical decision points. Deeper material is split into
  `references/workflows.md` (per-command reference), `references/scientific-validity.md`
  (the guardrails in depth), and `references/outputs.md` (reading and
  reproducing runs).
- It is also packaged as an installable plugin via `.claude-plugin/marketplace.json`,
  following the [anthropics/life-sciences](https://github.com/anthropics/life-sciences)
  marketplace pattern:

  ```bash
  /plugin marketplace add https://github.com/jyryu3161/CMIG.git
  ```

The skill points agents at `uv run cmig <command> --help` as the authoritative flag
list. `cmig workflows --format json` maps GUI surfaces to commands, but it reports
each workflow's *common* options rather than every flag that changes the answer, so
it is a routing aid and not a flag reference.

Two caveats worth knowing when driving CMIG from the skill:

- The skill carries a per-command reference for the flags that determine the
  answer (`--multi-metric`, `--single-medium`, `--close-untracked-uptake`,
  `--allow-unknown-medium`, `--accept-unreviewed-map`, `--allow-failed-run`, …)
  precisely because those are the ones a `workflows`-only reading misses. Re-check
  them against `--help` whenever the CLI changes.
- The skill opens with a preflight (`uv run cmig version && uv run cmig solvers`)
  because a genome-scale analysis can run 15+ minutes and an environment without
  the `engine` extra fails only once it reaches the solve. It also guards a subtler
  case: `uv run` resolves the **nearest** project root, so running it from a git
  worktree or sibling checkout — each with its own `pyproject.toml` — resolves a
  *different* project and provisions a fresh minimal `.venv` with no `engine`
  extra. `cmig workflows` still succeeds there while every analysis command fails
  with `… 는 엔진 stack 필요`, and that message names a fix that would sync the
  wrong project. Run `uv run` from the checkout whose environment you synced.

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

Add `--robustness-fva` to get each candidate's target FVA range. Without it a
ranking cannot be distinguished from a tie between alternate optima. **This works
only in single-target mode** — in multi-target mode the flag is accepted and silently
ignored (no columns, no warning, exit `0`), so a multi-target ranking currently
cannot be bounded against alternate optima from within the run. Use
`--multi-metric pareto` for trade-off structure there.

#### Several targets at once (e.g. "total SCFA")

`--targets ac,but` or `--target-preset scfa` (=
`ac,but,lac__D,lac__L,ppa,succ`) switches to multi-target search, scored by
`--multi-metric`:

| Metric | Meaning | Use for | Collapses onto a vertex? |
| ------ | ------- | ------- | ----------------------- |
| `normalized_weighted` (default) | dimensionless min-max over *this run's* candidate set | never a "total" claim; the scores are **not comparable across runs** | **yes** |
| `carbon_equivalent` | mmol C gDW⁻¹ h⁻¹ — each target weighted by its carbon number | "most carbon routed to SCFA"; absolute and run-comparable | **yes** |
| `raw_sum` | plain molar sum | only when a molar sum is genuinely wanted; it adds C2 and C4 acids as equals | **yes** |
| `pareto` | the **non-dominated trade-off set**, via an epsilon-constraint sweep in absolute units | **"which community is best for total SCFA"** | no |

All three scalar metrics are linear objectives, so the vertex collapse is a property
of the scalarisation, not of the weighting — different weights only change *which*
vertex you land on. `carbon_equivalent` fixes the units problem, not the specialist
problem.

**A linear weighted sum is optimised at a vertex of the achievable set, so it
systematically favours a single-metabolite specialist over a balanced producer.**
Over the five bundled models, `--target-preset scfa` with the default metric
ranked `iHN637+iSFV_1184` first with `ac=0, but=0, lac__D=17.44, lac__L=0, ppa=0,
succ=0` — and all nine ranked candidates had `ac=0, but=0, ppa=0, succ=0`. The
whole "total SCFA" ranking was decided by D-lactate alone.

The same pair, same pool, same medium, reported under each metric:

| metric | ac | but | lac__D | lac__L | ppa | succ |
| ------ | -- | --- | ------ | ------ | --- | ---- |
| `normalized_weighted` | 0 | 0 | **17.44** | 0 | 0 | 0 |
| `carbon_equivalent` | **8.19** | 0 | 0 | 0 | 0 | **10.41** |
| `pareto` rank 1 | **27.75** | 0 | 0 | 0 | 0 | 0 |

`normalized_weighted` says this community makes lactate and no succinate;
`carbon_equivalent` says succinate and no lactate. Those are contradictory claims
about one community on one medium, differing only in the weighting — and the default
metric reports **zero acetate for the pool's largest acetate producer** (27.75).
`carbon_equivalent` returned `but=0, lac__D=0, lac__L=0, ppa=0` for all nine of its
ranked candidates, so it is not an escape from the collapse either. CMIG emits a
warning about this itself; do not report any scalarised winner as "the best
total-SCFA community".

If you specifically need a single absolute, run-comparable number,
`--multi-metric carbon_equivalent` is the one to use — while remembering it is still
linear and still lands on a vertex. For the honest answer to "which community is
best overall", use `--multi-metric pareto`:

```bash
uv run cmig search \
  --model-dir /path/to/microbial_models \
  --target-preset scfa \
  --multi-metric pareto \
  --min-size 2 --max-size 2 --top-k 10 \
  --out runs/search_scfa_pareto
```

`pareto` takes a different code path from the scalar metrics: an
epsilon-constraint sweep over every consortium, whose non-dominated subset is
computed in N dimensions and reported in absolute units
(`solution_semantics: epsilon_constrained_lp_non_dominated_set`). It works for any
number of targets, and it is markedly slower than the scalar metrics because it
solves an LP per consortium per epsilon level.

Two things to carry into the write-up:

- **Front members are not totally ordered.** In `pareto` mode `rank` is a
  *reporting order* (weighted sum), not a claim that rank 1 is best. Present the
  frontier and let the reader choose the trade-off.
- The run reports how many front points are themselves single-metabolite
  specialists, so you can say how much genuine trade-off the pool actually offers.

Note a separate use of the same word: when you use a **scalar** metric, the
rankings table also carries a `pareto` boolean column, and that column is only
computed for **exactly two** targets. With more targets every cell stays `False`,
meaning "not evaluated" rather than "dominated". Do not filter a 6-target scalar
ranking on `pareto == True` — it will be empty.

Multi-target search writes a different artifact set from single-target search:
`pool_taxonomy.csv`, `search_rankings.csv`, `search_summary.json`,
`search_plot.svg`, `search_plot.tiff`, `pool_diagnostics.csv`, and
`search_unevaluated.csv` when any candidate could not be evaluated. There is no
`search_member_matrix.csv` or `search_scatter.svg` in this mode.

Read `search_unevaluated.csv` before the ranking: unevaluable candidates get no
rank and are excluded from `top_ranked`, so absence from the ranking does not mean
a low score. A common cause appears in the **`flux_basis`** column as
`per_target_capability_not_simultaneous` — the combination can make each target
individually but not all at once. (`diagnostic` holds the solver message beside it,
and `missing_targets` names the target that failed.)

Note also that **`status: degraded` is the normal outcome** whenever any candidate is
unevaluable — the measured `--target-preset scfa` run reported `degraded` purely
because 1 of 10 candidates failed, while all 9 ranked rows were `optimal`. Check the
unevaluated partition before treating `degraded` as a problem with the ranking.

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

`--single-medium` decides whether the alone-vs-community delta is an interaction
effect at all:

- `community` (default) projects the community's effective medium onto each member,
  so the comparison is controlled and the delta is attributable to interaction.
- `model_default` keeps each member's native SBML bounds. That reports **native
  capability, not an interaction effect** — the delta then also contains the medium
  change, and must not be read as cross-feeding.

A **blank** `single_growth` is a failed alone-solve, not a measured zero. Those
members are excluded from the figure with the excluded count stated; a missing
"Single model" bar is not evidence of obligate syntrophy.

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
  --fva \
  --out runs/iML1515_ac_ratio
```

Pass `--fva` so each sweep point carries the target exchange's FVA interval.
Without it, a jump between neighbouring abundances cannot be distinguished from
alternate-optima degeneracy, and reading it as a dose response is a wrong
conclusion. Overlapping intervals mean alternate optima, not a trend.

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
- `target_influence_share`: the selected member's **abundance-weighted**
  community contribution share (per-taxon flux × abundance, over the community
  total). It is not raw per-taxon flux — see *Reading `edges.parquet`* below for
  why that distinction matters.

Rows whose `status` is not `ok` carry NaN rather than `0.0` and are excluded from
the figure. Check `status` per row before reading the curve.

### 5. Run host-microbe coupling

Example with a Recon/Human-GEM style host model and a microbial model folder:

```bash
export MICROBIAL_BIOMASS_GDW="<study microbial dry mass in gDW>"
export HOST_BIOMASS_GDW="<host dry-mass basis represented by the host fluxes in gDW>"
export BIOMASS_BASIS_SOURCE="<measurement record, Methods section, or literature citation>"

uv run cmig host-microbe-bigg \
  --host /path/to/Human-GEM.xml \
  --model-dir /path/to/microbial_models \
  --recursive \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" \
  --biomass-basis-kind measured \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" \
  --interface-map /path/to/reviewed_host_interface_map.json \
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

CMIG first uses metabolite annotations and normalized BiGG identifiers, but
annotation matches are still computational suggestions. Generate a candidate map
with `cmig host-map`, review it, and pass it with `--interface-map` for a
publication run. Biomass bases are explicit because microbial and host-specific
fluxes cannot be compared or transferred without their gDW scaling assumptions.
CMIG therefore has no biomass default: both positive values, their basis kind,
and a measurement record or citation are mandatory. `--biomass-basis-kind
validation` is available for software tests but marks the result as
non-publication-ready.

Entries the mapping wizard cannot settle carry `needs_review`, and the host
commands **refuse to couple** while any remain. `--accept-unreviewed-map` waives
that gate; the run is warned and the entries are named. The specific hazard it
waives is **D/L stereoisomer confusion** — BiGG spells stereo descriptors as
`__D`/`__L`, and an annotation match can pair `lac__D` with `lac__L`, which opens
a host exchange for a molecule the host cannot transport. Review stereo
descriptors explicitly.

Two more options change what "host benefit" means:

- `--keep-host-uptake` leaves pre-existing host exchange uptake open. By default
  CMIG closes it before coupling, so the host's gain is attributable to the
  microbes; with this flag an apparent benefit may just be the host's background
  medium.
- `--include-currency-metabolites` allows direct h/h2o/co2 coupling. It is off by
  default because it makes almost any pair look like it interacts.

`host-search-bigg --metric weighted` never adds raw quantities with different
units. It requires explicit positive weights and `--host-reference` plus
`--target-reference`, and ranks the resulting dimensionless normalized score.
Use `target_transfer` or `objective_value` when no defensible reference scales
exist. Check each row's `evaluation_status` and the summary's
`n_candidates_failed`: a non-optimal host LP is published as NaN rather than a
ranked `0.0`, and `host_search_unevaluated.csv` holds the excluded candidates.

### 5b. Measure a microbial knockout's effect on the host

Use this when the question is "how does perturbing a microbe change the host".
`host-ko-impact` knocks out a gene or reaction in one named member, holds every
other input identical across the arms, and reports the delta in the host objective
and in target delivery to the host. Do not assemble this from `gene-ko-search`
plus `host-microbe-bigg`, which do not hold the arms identical.

```bash
uv run cmig host-ko-impact \
  --host /path/to/Recon3D.xml \
  --model-dir /path/to/microbial_models \
  --member iML1515 \
  --ko-level reaction \
  --reactions ACKr \
  --target ac \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" \
  --biomass-basis-kind literature \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" \
  --interface-map /path/to/reviewed_host_interface_map.json \
  --out runs/host_ko_ackr
```

The same biomass-basis and interface-map rules apply. Output:
`host_ko_impact_summary.json` and `host_ko_impact.csv` — the per-arm tidy table
holding the actual deltas (workflow kind `host_ko_impact`). GUI surface:
`Host / Knockout Impact`.

### 6. Run a MICOM taxonomy solve

If you already have a MICOM-compatible taxonomy CSV:

```bash
uv run cmig solve \
  --taxonomy /path/to/taxonomy.csv \
  --medium medium_presets/gut_overlay_agora_western.csv \
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
  --close-untracked-uptake \
  --out runs/dfba_user_model
```

If `--initial` is omitted, CMIG uses an aerobic default preset where available:
`EX_glc__D_e=10`, `EX_o2_e=20`, `EX_ac_e=0`, and `EX_lac__D_e=0`. Explicit
`--initial` values are strict and must exist in the model. The default horizon is
`--t-end 5.0`, so the generated figure is an analysis preview rather than a
very short smoke-test trace.

**`--close-untracked-uptake` is required for a substrate/Km experiment.** CMIG
tracks concentrations only for the exchanges named by `--initial`. Every other
uptake left open by the model's default medium has no concentration, so it is
never depleted and no Michaelis-Menten term applies — biomass can rise while the
tracked substrate is untouched. Without the flag, the run still reports
`status: completed` and a biomass number while its own `warnings` field says the
experiment is not interpretable. On `models/iML1515.xml` at `--dt 0.1` this is 14
untracked uptake substrates. Always read `n_untracked_uptake` and `warnings` from
`dfba_summary.json`.

Useful outputs:

- `dfba_summary.json`
- `timecourse.parquet`
- `dfba_timecourse.csv`
- `dfba_timecourse.svg`
- `dfba_timecourse.tiff`

Audit numerical sensitivity to both the integration step and uptake half-saturation
constant before interpreting a dFBA endpoint:

```bash
uv run cmig dfba-sensitivity \
  --model /path/to/model.xml \
  --dts 0.2,0.1,0.05 \
  --kms 0.005,0.01,0.02 \
  --close-untracked-uptake \
  --out runs/dfba_sensitivity
```

The output includes every run plus integration mass-balance residuals, so a
coarse-step result cannot silently become the reported result. Pass
`--close-untracked-uptake` here too — otherwise you are auditing Km sensitivity on
an experiment in which Km was never rate-limiting.

Outputs are `dfba_sensitivity.json` and `dfba_sensitivity.csv`. Read
`acceptance.interpretable` and `acceptance.not_interpretable_because`: the grid is
rejected if **any** row is infeasible or **all** rows stalled, and the command
exits `3` when it is not interpretable.

**Pair `--close-untracked-uptake` with a complete `--initial`.** Closing untracked
uptake removes every nutrient you did not name — nitrogen, phosphate, sulfate, trace
metals — so the default four-substrate `--initial` starves the model. On
`models/iML1515.xml`, `--close-untracked-uptake` alone closed 22 exchanges and gave
exit `3` with 4/4 rows stalled at `final_biomass 0.01` (the initial value, no
dynamics). Adding the 14 nutrients listed in a plain run's `untracked_uptake` field
gave exit `0`, `interpretable: True`, 4/4 completed, and a genuine step-size signal
(`final_biomass` 0.0536 at `dt 0.1` vs 0.0503 at `dt 0.2`). `dfba-sensitivity`
accepts `--initial` with the same syntax as `dfba`.

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

### 10. Publication preflight

Audit model formulas, objective feasibility, gene/formula coverage, dead ends,
and optionally blocked reactions independently of the biological workflow:

```bash
uv run cmig model-quality \
  --model-dir /path/to/microbial_models \
  --recursive \
  --check-blocked-reactions \
  --out runs/model_quality
```

The integrated `publication-benchmark` command combines quality audit, a
community solve, combination search, optional dFBA sensitivity, and optional
host coupling in one checksummed manifest. A fully specified real-model command
and reviewed results are recorded in `docs/PUBLICATION_VALIDATION.md`.

## Medium Files

Medium files are CSV (`exchange_id,uptake_limit`) or JSON, with `uptake_limit >= 0`
an unsigned magnitude in **mmol gDW-1 h-1** applied as `lower_bound = -uptake_limit`.
Pass them with `--medium`, `--host-medium`, or `--microbe-medium` depending on the
workflow.

**`--medium` is an overlay, not a replacement.** CMIG merges the file onto whatever
the community already offers (`exact=False`), so any metabolite the file does not name
keeps MICOM's permissive default — including `EX_o2_m = 999999.0`, i.e. an aerobic
colon. Measured on a 3-member community, the legacy glucose-only preset gives
community growth 1.2678 h⁻¹ with that inherited oxygen and 0.6990 h⁻¹ once oxygen is
named at 0.001: an 81 % overestimate from one missing row. A `uptake_limit` of `0` is
legal and is how a CSV closes an exchange under merge semantics.

Presets live in `medium_presets/`. Prefer the literature-grounded gut overlays, which
all name oxygen explicitly and carry a background-closure block:
`gut_overlay_agora_western.csv` and `gut_overlay_agora_high_fiber.csv` (AGORA
Supplementary Table 12, already in mmol gDW⁻¹ h⁻¹ — the reference pair),
`gut_overlay_vmh_high_fiber.csv` / `gut_overlay_vmh_high_fat_low_carb.csv` (VMH diets,
converted; the more sensitive contrast), `gut_overlay_micom_western.csv` (MICOM's
published medium verbatim). Every value, its source, its unit conversion, its
per-model exchange coverage and the fibre-coverage limitation are recorded in
`medium_presets/PROVENANCE_gut_media.md`; each row's origin is in
`medium_presets/provenance_rows.csv`. Regenerate with
`python -m scripts.build_gut_media`.

`western_diet.csv` and `high_fiber.csv` are single-row glucose files with no cited
source, 134× and 76× the corresponding published AGORA bounds; they are retained only
as a smoke fixture and **must not be cited as diets** (audit in
`PROVENANCE_gut_media.md` §1).

The format is `exchange_id,uptake_limit` with `uptake_limit >= 0` — an unsigned
magnitude in **mmol gDW⁻¹ h⁻¹**, which CMIG maps internally to
`lower_bound = -uptake_limit`. Literature diets are usually quoted per person per
day; show the conversion arithmetic and its assumptions rather than pasting a
number.

A medium is applied by translating it to the community's exchange **reactions**
per metabolite, so an exchange that is currently closed **does get opened**.

> ### Re-run any earlier run that used `--medium`
>
> An earlier implementation gated medium application on the *already-open*
> uptakes, so most nutrients — acetate, butyrate, lactate, succinate and glycerol
> among them — were silently never applied, while the manifest still stamped the
> requested `medium_checksum` and a `run_hash` certifying it. **Those runs are
> invalid and must be re-run.**
>
> The hash will not reveal it: the fix deliberately changed published numbers
> without moving any hash (`solve --medium` moved `0.881561` → `1.125065` under an
> identical `run_hash`). Detection is via the non-hashed provenance marker:
>
> ```bash
> uv run cmig inspect-run --run-dir runs/<name> --format json   # provenance.medium_policy
> ```
>
> A trustworthy run records `exchange_reactions_by_metabolite_v2`. Absent, or
> `open_uptakes_exact_key_v1`, means re-run.

Two further rules:

- **Do not list one metabolite under two namespaces.** Giving both
  `EX_glc__D_m` and `EX_glc__D_e` is rejected as an input error (exit `2`) in both
  `solve` and `search`. It previously picked a silent winner, and reordering
  identical CSV rows changed community growth under an identical checksum.
- **`--allow-unknown-medium` drops nutrients.** Without it, a medium id with no
  counterpart in the community is a hard input error (exit `2`). With it, those
  ids are dropped and the run continues — measured: exit `0`, `status: degraded`,
  a `medium_unapplied` diagnostic naming the dropped ids, and a `medium_checksum`
  still computed over the **full requested** medium. Use it to diagnose a medium
  file, not to produce a reported result.

## Solver Provenance

- `gurobi`: canonical full-flux workflow.
- `osqp`: QP-only approximate provenance for supported community solve paths.
- Community FVA and product host/search workflows currently require Gurobi.

CMIG records solver choice and flux provenance in run outputs so cached or
published results can be interpreted correctly.

`uv run cmig solvers` also reports `highs` as available, but no command's
`--solver` accepts it: the choices are `{gurobi, osqp}` for `solve`, `dfba`,
`dfba-sensitivity` and `sandbox-fixture`, and `{gurobi}` only for `search`,
`strain-growth`, `abundance-impact`, `gene-ko-search`, `model-quality`,
`publication-benchmark` and the host workflows. Availability in the matrix is not
selectability.

## Reading `edges.parquet`

`edges.parquet.weight` is an unsigned **per-taxon** flux
(`mmol gDW_taxon⁻¹ h⁻¹`). It is not abundance-weighted and **not comparable to
`profile.parquet.net_flux`**, which is community-basis.

Because per-taxon flux scales roughly as 1/abundance, comparing raw edge weights
**inverts** member rankings. Measured on a two-member solve (iHN637 at abundance
0.1, iML1515 at 0.9), acetate secretion:

| member  | abundance | `edges.weight` | × abundance |
| ------- | --------- | -------------- | ----------- |
| iHN637  | 0.1       | 3.876102       | 0.387610    |
| iML1515 | 0.9       | 0.459437       | **0.413494**|

Edge weights say iHN637 dominates by 8.4×; community contribution says iML1515
does. To compare members: keep only `edge_type in {secretion, uptake}` (exclude
`cross_feeding`, which is a mass-conserving proportional allocation rather than a
measurement), sign each row by direction, and multiply by the member's abundance.
The sum then matches that metabolite's `profile.parquet.net_flux` (`0.801104`
above) for metabolites well above the engine's 1e-6 noise floor. It is not a blanket
invariant: in the same run 23 of 25 overlapping metabolites agreed to <1e-9 while
`mobd` and `btn` were off by ~1e-8, and 19 of the 44 metabolites in `edges.parquet`
had no `profile.parquet` row to reconcile against at all.

`manifest.json → edge_attribution` states this, and
`uv run cmig inspect-run --format text` prints it as the `edges.weight basis:`
line. Edge width in the interaction figures is per-taxon flux for the same reason.

## Development

Run the standard checks:

```bash
uv run ruff check cmig tests
uv run mypy cmig
uv run pytest -q
uv build
uv run python scripts/audit_distribution.py dist/*
```

Golden-version gate:

```bash
uv run cmig golden verify
```

Workflow-envelope gate — `golden verify` protects the frozen 11-component
`community_solve` hash; this protects the workflow-manifest serialization every
other command's `run_hash` is derived from. Needs no solver and no license:

```bash
uv run cmig golden verify-envelope
```

If it reports drift, the serialization changed and every previously published
workflow `run_hash` of the listed kinds now derives differently from identical
inputs. Re-bless only when that is intended, and record it as a contract change:

```bash
uv run python -m cmig.core.workflow_envelope_golden
```

The test suite includes headless core tests, MICOM-backed tests, solver
provenance tests, GUI offscreen smoke tests, and real workflow regressions.

## Scope And Limitations

- CMIG expects users to provide their own GEM files.
- CMIG does not automatically download AGORA, VMH, Recon, Human-GEM, or BiGG
  model collections.
- Host-microbe coupling maps authoritative metabolite annotations where available,
  but publication use still requires review of the generated interface map.
- dFBA currently supports well-mixed single-model simulations. Full spatial
  community dFBA with biomass propagation, extracellular reactions, and
  evolution-like COMETS modules is out of scope for the current CMIG engine.
- `spatial-preview` models diffusion/source/sink media design only; it does not
  solve FBA on every grid cell.
- The GUI has been tested in offscreen mode; final manual desktop QA may still
  be useful before distribution.
- README examples assume Gurobi is installed and licensed.
- **The bundled `models/` pool is not a gut community.** iML1515 (*E. coli*) is
  the only common gut resident; iYO844 (*B. subtilis*) is soil/transient, iAF987
  (*Geobacter metallireducens*) is a sediment metal reducer, iSFV_1184
  (*Shigella flexneri*) is a pathogen, and iHN637 (*Clostridium ljungdahlii*) is
  an industrial acetogen. Any result over this pool is a **methods
  demonstration, not gut biology** — say so wherever it appears, and do not let a
  figure imply otherwise.
- `edges.parquet.weight` is a per-taxon flux and its magnitude can invert against
  true community contribution. See *Reading `edges.parquet`*; the value itself is
  a known-open item, only the unit disclosure has landed.
- The `pareto` **column** on a scalarised ranking is only computed for exactly two
  targets; with more, every cell stays `False`, meaning "not evaluated" rather
  than "dominated". The `--multi-metric pareto` **mode** is unaffected and works
  for any number of targets.
- Atomic writes cover text artifacts; parquet and figure writers are not yet
  atomic.

## Repository Layout

- `cmig/core/`: domain logic and solver-facing workflows.
- `cmig/service/`: application service facade and non-blocking job runner.
- `cmig/gui/`: PySide6 desktop UI.
- `cmig/cli/`: command-line entry point.
- `cmig/io/`: run output, checksums, manifests, and import helpers.
- `cmig/render/`: figure rendering helpers.
- `cmig/render_r/`: R scripts and a pinned `renv.lock` for figure reproduction.
- `tests/`: regression and workflow tests.
- `scripts/`: release/distribution audits and the gut-media builder.
- `medium_presets/`: medium definitions, mirrored source data (`sources/`) and provenance.
- `docs/`: design and project-management notes.

## License

CMIG-authored code and documentation are licensed under Apache-2.0; see `LICENSE`
and `NOTICE`. External GEMs, Gurobi, Python/R dependencies, and generated research
outputs keep their own terms. In particular, the validation models under
`models/` are not Apache-licensed and are excluded from wheels and source
distributions; see `THIRD_PARTY_NOTICES.md` and `models/MODEL_SOURCES.json`.
