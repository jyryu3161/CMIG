# CMIG workflow reference

Per-command reference for the CMIG CLI. This mirrors the machine-readable map
from `uv run cmig workflows --format json`; when in doubt, **`uv run cmig <command> --help`
is the single ground truth** — the `workflows` map lists each workflow's *common*
options, not every flag that changes the answer. Every analysis command takes
`--out runs/<name>` and should be followed by
`uv run cmig inspect-run --run-dir runs/<name> --format json`.

> **Invocation.** Examples here are spelled `uv run cmig <command>`, matching what
> `cmig workflows` emits. `cmig <command>` and `python -m cmig.cli.main <command>`
> are equivalent against an activated environment or a non-`uv` install.
>
> Run `uv run` **from the directory whose environment was synced**: it resolves the
> nearest project root, so a git worktree or sibling checkout (each carrying its own
> `pyproject.toml`) resolves a *different* project and gets a fresh minimal `.venv`
> with no `engine` extra — `workflows` succeeds, every analysis command fails with
> `… 는 엔진 stack 필요`. `uv run cmig solvers` catches this in one command.

> **Exit codes.** `0` = solved; `2` = input error (medium spec, namespace
> aliases); `3` = artifacts written but the scientific solve failed. Every
> analysis command accepts `--allow-failed-run` to force `0` — which does not
> make the run a result. Always check `$?`.

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
- Required: `--model-dir` (or `--taxonomy`), `--out`, and a target
  (`--target` | `--targets` | `--target-preset`).
- Single-target: `--target but`, `--direction
  max_secretion|min_secretion|max_uptake|min_uptake`.
- Multi-target: `--targets ac,but` or `--target-preset scfa` (=
  `ac,but,lac__D,lac__L,ppa,succ`), with `--multi-metric`, `--target-weights`,
  `--target-directions`. **See "Multi-target scoring" below — the default metric
  will hand you a single-metabolite specialist.**
- Common: `--min-size`, `--max-size`, `--strategy auto|exhaustive|random|ga`,
  `--n-samples`, `--seed`, `--top-k`, `--robustness-fva`, `--growth-fraction`,
  `--medium`, `--allow-unknown-medium`, `--allow-failed-run`, `--solver`,
  `--recursive`.
- Outputs: `search_summary.json`, `search_rankings.csv`,
  `search_member_matrix.csv`, `pool_diagnostics.csv`, `search_plot.svg`,
  `search_scatter.svg`.
- Use `--recursive` when the pool is organised as subfolders
  (`strainA/model.xml`, `strainB/model.xml`).
- `--robustness-fva` adds the target's FVA range per candidate. Without it you
  cannot tell a real ranking from a tie between alternate optima. **It works only in
  single-target mode**: in multi-target mode it is accepted and silently ignored —
  no FVA columns, no warning, exit 0 (`cli/main.py:4151` returns to the multi-target
  path before the flag is read). Known limitation; use `--multi-metric pareto` for
  multi-target trade-off structure instead.
```bash
uv run cmig search --model-dir models --target but --min-size 2 \
  --max-size 2 --top-k 10 --strategy auto --robustness-fva --out runs/search_but
```

#### Multi-target scoring — `--multi-metric`

For any question of the form "most SCFA overall", the choice of metric *is* the
answer.

| Value | Unit / meaning | When to use | Collapses onto a vertex? |
| ----- | -------------- | ----------- | ----------------------- |
| `normalized_weighted` **(default)** | dimensionless min-max over *this run's* candidate set | never for a "total" question; scores are **not comparable across runs** | **yes** |
| `carbon_equivalent` | mmol C gDW⁻¹ h⁻¹ — each target weighted by its carbon number from the model formula | "most carbon routed to SCFA"; absolute and run-comparable | **yes** |
| `raw_sum` | mmol gDW⁻¹ h⁻¹ — plain molar sum | only when the user explicitly wants molar sum; it treats C2 and C4 acids as equivalent | **yes** |
| `pareto` | the **non-dominated trade-off set** via an epsilon-constraint sweep | **"which community is best for total SCFA"** | no |

All three scalar metrics are **linear** objectives, so the vertex collapse is a
property of the scalarisation itself — different weights only move *which* vertex you
land on. `carbon_equivalent` fixes the units problem (absolute, run-comparable), not
the specialist problem.

The scalarised metrics (`normalized_weighted`, `carbon_equivalent`, `raw_sum`)
are optimised **at a vertex** of the achievable set, so they favour a
single-metabolite specialist. A balanced producer is dominated on the scalar score
while being the biologically interesting answer.

Measured over the 5 bundled models with `--target-preset scfa` and the default
metric: rank 1 was `iHN637+iSFV_1184` with `ac=0, but=0, lac__D=17.44, lac__L=0,
ppa=0, succ=0`, and **all 9 ranked candidates had `ac=0, but=0, ppa=0, succ=0`** —
the whole "total SCFA" ranking was decided by D-lactate alone.

The same pair, same pool, same medium, under each metric:

| metric | ac | but | lac__D | lac__L | ppa | succ |
| ------ | -- | --- | ------ | ------ | --- | ---- |
| `normalized_weighted` | 0 | 0 | **17.44** | 0 | 0 | 0 |
| `carbon_equivalent` | **8.19** | 0 | 0 | 0 | 0 | **10.41** |
| `pareto` rank 1 | **27.75** | 0 | 0 | 0 | 0 | 0 |

`normalized_weighted` says this community makes lactate and no succinate;
`carbon_equivalent` says succinate and no lactate — contradictory claims about one
community, differing only in the weighting. `carbon_equivalent` returned
`but=0, lac__D=0, lac__L=0, ppa=0` for **all 9** of its ranked candidates, so it is
not an escape from the collapse. Non-zero SCFA counts per ranked row:
`normalized_weighted` `[1,1,1,1,1,2,1,1,1]`, `carbon_equivalent`
`[2,2,1,1,2,2,1,2,1]`, `pareto` `[1,4,4,4,4,5,5]`.

`--multi-metric pareto` is a **different code path**, not a different weighting:
an epsilon-constraint sweep per consortium whose N-dimensional non-dominated
subset is reported in absolute units (`strategy:
exhaustive_epsilon_constraint`, `solution_semantics:
epsilon_constrained_lp_non_dominated_set`). It works for any number of targets and
is much slower.

- In `pareto` mode `rank` is a **reporting order** (weighted sum), **not** a claim
  that rank 1 is best — front members are not totally ordered. Present the
  frontier.
- The run reports how many front points are single-metabolite specialists, which
  is the honest measure of how much trade-off the pool offers.
- **Mode ≠ column.** A scalar-metric ranking also has a `pareto` boolean column,
  computed **only for exactly 2 targets**. With more, every cell stays `False`
  meaning "not evaluated" — filtering on `pareto == True` returns nothing, which is
  not a finding.

```bash
# "best combination for total SCFA" — the defensible form
uv run cmig search --model-dir models --target-preset scfa \
  --multi-metric pareto --min-size 2 --max-size 2 --top-k 10 \
  --out runs/search_scfa_pareto
```

### `cmig strain-growth` — single vs community growth
Compare each strain's single-model FBA growth with its member growth inside the
full MICOM community.
- Required: `--model-dir` (or `--taxonomy`), `--out`.
- Common: `--medium`, `--tradeoff-f`, `--single-medium`,
  `--allow-unknown-medium`, `--allow-failed-run`, `--solver`, `--recursive`.
- Outputs: `strain_growth_summary.json`, `strain_growth.csv`,
  `strain_growth_plot.svg`.
- Interpretation: `single_growth` = individual GEM FBA; `community_member_growth`
  = growth after MICOM construction + cooperative tradeoff; `abundance` = member
  abundance used by the community model.
- **`--single-medium` decides what the comparison means.**
  `community` (default) projects the community's effective medium onto each
  member, so the alone-vs-community delta is a controlled interaction effect.
  `model_default` keeps each member's native SBML bounds — that reports **native
  capability, NOT an interaction effect**, because the delta then also contains
  the medium change. Do not read a `model_default` delta as cross-feeding.
- A member whose alone-solve fails is written **blank** in the CSV and is
  excluded from the figure with the excluded count stated — it is not a measured
  zero. Do not read a missing "Single model" bar as obligate syntrophy.
- **Check `medium_metabolites_unavailable_to_member` per row.** Even under
  `--single-medium community`, a member may lack an exchange for part of the
  projected medium, and this column names what it could not receive. A non-empty
  value means the "controlled" comparison was **not** fully controlled for that
  member, so quote it rather than assuming the projection succeeded.
```bash
uv run cmig strain-growth --model-dir models --single-medium community \
  --out runs/strain_growth
```

### `cmig abundance-impact` — one-member ratio/abundance sweep
Sweep one member's abundance and quantify how it changes community growth,
member growth, and target exchange. **Sensitivity analysis, not causality.**
- Required: `--model-dir` (or `--taxonomy`), `--member`, `--out`.
- Common: `--fractions`, `--target`, `--medium`, `--tradeoff-f`, `--fva`,
  `--allow-unknown-medium`, `--allow-failed-run`, `--solver`, `--recursive`.
- Outputs: `abundance_impact_summary.json`, `abundance_impact.csv`,
  `member_growth_by_abundance.csv`, `abundance_impact_plot.svg`.
- Key fields: `target_member_growth`, `target_member_exchange`,
  `community_target_exchange`, `target_influence_share` (abundance-**weighted**
  community contribution share, not raw per-taxon flux).
- **Pass `--fva`.** It reports the target exchange's FVA interval at each sweep
  point. Without it, a jump between neighbouring abundances cannot be
  distinguished from alternate-optima degeneracy, and reading it as a dose
  response is a wrong conclusion.
- A failed solve at a sweep point is written as NaN with a non-`ok` `status`, and
  the figure excludes it. Check `status` per row before reading the curve.
```bash
uv run cmig abundance-impact --model-dir models --member iML1515 \
  --fractions 0.1,0.25,0.5,0.75 --target ac --fva \
  --out runs/iML1515_ac_ratio
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
- **`--rank-by {effect,remaining}` sets the entire ordering.** `effect` (default)
  ranks by `|delta|` descending — the knockouts that move the target most, which is
  what a suppression screen asks for. `remaining` ranks by highest remaining target
  flux (the older ordering, in which a knockout with no effect can outrank a large
  one). State which you used; the two give different "top knockouts".
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

> **The host GEM is user-supplied.** `/path/to/host_gem.xml` in these examples is
> a placeholder — CMIG never downloads Recon / Human-GEM / BiGG catalogues, and no
> host model ships in the Python distribution. Ask the user for the local path.
> A BiGG-namespace host (Recon3D, RECON1, Human-GEM) is the supported shape; a host
> in another namespace will land almost entirely in the map's `needs_review` /
> `unmatched` partitions, which is a signal to fix the namespace rather than to
> waive the review gate.
>
> Measured on the real Recon3D (10,600 reactions / 5,835 metabolites): a cold
> `cobra.io.read_sbml_model` takes **~6–7 s**, not the ~30–60 s often quoted. Still
> cache the host between arms rather than reloading it in a loop, but do not budget
> a minute per load.

### `cmig host-microbe-bigg` — direct host↔microbe coupling
Run direct BiGG-style host-microbe exchange coupling for Recon / Human-GEM style
host models plus a microbial model folder.
- Required: `--host`, `--model-dir` (or `--taxonomy`),
  `--microbial-biomass-gdw`, `--host-biomass-gdw`, `--biomass-basis-kind`,
  `--biomass-basis-source`, `--out`.
- Common: `--host-objective`, `--microbe-medium`, `--host-medium`,
  `--interface-map` (reviewed map), `--exchange-suffix`,
  `--exclude-metabolites`, `--include-currency-metabolites`,
  `--keep-host-uptake`, `--accept-unreviewed-map`, `--allow-failed-run`,
  `--tradeoff-f`, `--recursive`.
- **`--keep-host-uptake` changes what "host benefit" means.** By default CMIG
  closes pre-existing host exchange uptake before coupling, so the host's gain is
  attributable to the microbes. With this flag the host keeps its background
  medium, and an apparent benefit may simply be that medium.
- **`--include-currency-metabolites` is off by default** for a reason: coupling
  h/h2o/co2 directly makes almost every pair look interacting. Turn it on only
  with a stated rationale.
- Outputs: `host_microbe_bigg_summary.json`, `microbial_secretion.csv`,
  `host_uptake.csv`, `microbe_to_host.csv`, `interaction_edges.csv`,
  `interaction_matrix.csv`, `member_contribution.csv`, `figure_manifest.json`,
  `interaction_circle.svg`, `interaction_heatmap.svg`, `interaction_bubble.svg`,
  `member_contribution.svg`.
```bash
export MICROBIAL_BIOMASS_GDW="<microbial dry mass in gDW>"
export HOST_BIOMASS_GDW="<host dry-mass basis in gDW>"
export BIOMASS_BASIS_SOURCE="<measurement record, Methods, or citation>"
uv run cmig host-microbe-bigg --host /path/to/host_gem.xml \
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
  `--host-objective`, `--interface-map`, `--keep-host-uptake`,
  `--include-currency-metabolites`, `--exclude-metabolites`,
  `--accept-unreviewed-map`, `--allow-failed-run`, `--recursive`.
- `--include-currency-metabolites` and `--keep-host-uptake` carry the **same
  caveats as for `host-microbe-bigg`** above: the former makes nearly any pair look
  interacting, the latter lets the host's background medium masquerade as microbial
  benefit. Both change what the ranking means.
- Outputs: `host_search_summary.json`, `host_search_rankings.csv`,
  `host_search_plot.svg`.
- `--metric weighted` requires positive `--host-weight`, `--target-weight`,
  `--host-reference`, `--target-reference` (dimensionless score). Otherwise use
  `target_transfer` or `objective_value`.
- **Check each row's `evaluation_status` and the summary's
  `n_candidates_failed`.** A non-optimal host LP is a failed candidate: it is
  published as NaN rather than a ranked 0.0, and the figure states the excluded
  count. A row whose `warnings` cell says the host objective is not a result must
  not be read as a ranking.
```bash
uv run cmig host-search-bigg --host /path/to/host_gem.xml \
  --model-dir models --target ac --metric target_transfer \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" --biomass-basis-kind measured \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" --out runs/host_search
```

### `cmig host-ko-impact` — microbial knockout → host effect
Knock out a gene or reaction in **one** named microbial member, hold every other
input identical, and report the delta in the host objective and in target
delivery to the host. This is the workflow for "how does perturbing a microbe
change the host" — do not assemble it out of `gene-ko-search` plus
`host-microbe-bigg`, which do not hold the arms identical.
- Required: `--host`, `--model-dir` (or `--taxonomy`), `--member`, the full
  biomass-basis set (`--microbial-biomass-gdw`, `--host-biomass-gdw`,
  `--biomass-basis-kind`, `--biomass-basis-source`), `--out`.
- Common: `--ko-level gene|reaction` (reaction is the default), `--genes`,
  `--reactions`, `--target`, `--tradeoff-f`, `--microbe-medium`, `--host-medium`,
  `--interface-map`, `--host-objective`, `--exchange-suffix`,
  `--exclude-metabolites`, `--include-currency-metabolites`,
  `--keep-host-uptake`, `--accept-unreviewed-map`, `--allow-failed-run`.
- Outputs: `host_ko_impact_summary.json` **and `host_ko_impact.csv`** (the per-arm
  tidy table — read this for the actual deltas), kind `host_ko_impact`.
- GUI surface: `Host / Knockout Impact`.
```bash
uv run cmig host-ko-impact --host /path/to/Recon3D.xml --model-dir models \
  --member iML1515 --ko-level reaction --reactions ACKr --target ac \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" --biomass-basis-kind literature \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" \
  --interface-map reviewed_host_interface_map.json --out runs/host_ko_ackr
```

### `cmig host-map` — build a reviewable interface map
Generate a candidate host↔microbe metabolite interface map from annotations and
normalized BiGG IDs. The output is a **starting point for human review**, then
passed back via `--interface-map`.
- Required: `--host`, `--model-dir` (or `--taxonomy`), `--out`. Optional:
  `--recursive`. That is the complete flag set.
- Outputs: `host_interface_map.json`, `host_exchange_map.csv`,
  `host_map_summary.json`, `manifest.json`.
- The map is partitioned: `interface_map` holds **exact id matches only** (safe to
  pass through), `needs_review` holds annotation/normalized **guesses**, and
  `unmatched` holds secretions with no host counterpart. The host commands
  **refuse to couple** while any `needs_review` entry remains;
  `--accept-unreviewed-map` waives that and the run is warned with the entries
  named.
- **Size the review from `host_map_summary.json`:** if `n_annotation` and
  `n_normalized` are both 0, every match was exact and there is nothing to
  adjudicate. Measured on the real Recon3D against iHN637:
  `63 exact / 0 annotation / 0 normalized / 32 unmatched` of 95 secretions, with
  `needs_review: {}`.
- **The hazard the gate exists for is D/L stereoisomers.** *Annotation* matching
  can pair `lac__D` with `lac__L`, which opens a host exchange for a molecule the
  host cannot transport. The exact-match path is unaffected (Recon3D maps
  `lac__D_e → EX_lac__D_e` and `lac__L_e → EX_lac__L_e` correctly), so the risk is
  confined to the `needs_review` block — review stereo descriptors there
  specifically.
- `host_map` is a deterministic-artifact kind, so re-running it on identical
  inputs reproduces byte-identical output.
```bash
uv run cmig host-map --host /path/to/Recon3D.xml --model-dir models \
  --recursive --out runs/host_map
```

---

## Community solve

### `cmig solve` — MICOM taxonomy community solve
Run a user-provided MICOM taxonomy community solve.
- Required: `--taxonomy`, `--out`.
- Common: `--medium`, `--namespace-decisions` | `--assume-bigg-namespace`,
  `--allow-unknown-medium`, `--allow-failed-run`, `--solver {gurobi,osqp}`,
  `--tradeoff-f`, `--targets` (preset name, e.g. `scfa`), `--fva`,
  `--fva-metabolites`, `--bounds`.
- Outputs: `manifest.json`, `nodes.parquet`, `edges.parquet`, `profile.parquet`.
- **`cmig solve` writes a `manifest_scope: solve` manifest, not a workflow
  manifest**, so it carries `run_hash` but **no `result_digest`**. `inspect-run`
  reports `result_digest: not recorded` with
  `result_digest_absent_reason: solve_manifest_never_records_one` even for a
  brand-new run — expected here, not evidence of tampering.
- **`edges.parquet.weight` is a per-taxon magnitude** (`mmol gDW_taxon⁻¹ h⁻¹`),
  not abundance-weighted, and is **not** comparable to `profile.parquet.net_flux`
  (community basis). See "Reading `edges.parquet`" in `references/outputs.md`
  before comparing any two edges.
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
  `--vmax`, `--km`, `--min-dt`, `--growth-floor`, `--solver {gurobi,osqp}`,
  **`--close-untracked-uptake`**.
- Outputs: `dfba_summary.json`, `timecourse.parquet`, `dfba_timecourse.csv`,
  `dfba_timecourse.svg`, `dfba_timecourse.tiff`.
- If `--initial` is omitted, an aerobic default preset is used where available
  (`EX_glc__D_e=10`, `EX_o2_e=20`, `EX_ac_e=0`, `EX_lac__D_e=0`). Explicit
  `--initial` values are strict and must exist in the model.
- **`--close-untracked-uptake` is required for a substrate/Km experiment.**
  Untracked uptake exchanges left open by the model's default medium have no
  concentration, so they are never depleted and no Michaelis-Menten term applies
  — biomass can rise while the tracked substrate is untouched. Without the flag
  the run still reports `status: completed` and a biomass number while its own
  `warnings` field says the experiment is not interpretable. Always read
  `n_untracked_uptake` and `warnings` from `dfba_summary.json`.
```bash
# measured on the bundled model: 14 untracked uptake substrates without the flag
uv run cmig dfba --model models/iML1515.xml --dt 0.1 \
  --close-untracked-uptake --out runs/dfba_iML1515
```

### `cmig dfba-sensitivity` — audit dFBA numerical robustness
Run dFBA across integration steps and half-saturation constants; report every
run plus integration mass-balance residuals so a coarse-step result cannot
silently become the reported result. **Run this before trusting a dFBA
endpoint** — and pass `--close-untracked-uptake` here too, or you are auditing
Km sensitivity on an experiment where Km is not rate-limiting.
- Options: `--dts`, `--kms`, `--initial`, `--initial-biomass`, `--vmax`,
  `--t-end`, `--min-dt`, `--growth-floor`, `--solver {gurobi,osqp}`,
  `--close-untracked-uptake`, `--allow-failed-run`. (No `--km`/`--dt` singular —
  use the plural sweep forms.)
- Outputs: `dfba_sensitivity.json`, `dfba_sensitivity.csv` (note: **not**
  `dfba_sensitivity_summary.json`).
- Read `acceptance.interpretable` and `acceptance.not_interpretable_because`.
  The grid is rejected if **any** row is infeasible or **all** rows stalled, and
  the command **exits 3** when it is not interpretable.
- `inspect-run` now reflects that verdict: `acceptance.interpretable: false` is a
  **veto** that reports `status: failed` with
  `status_source: acceptance.interpretable`, and it overrides a rosier manifest
  tier (which matters for `publication-benchmark`, whose dFBA sub-run manifest is
  derived from `dfba_completed`/`dfba_balance_passed` only). Still check `$?`.
- **`--close-untracked-uptake` must be paired with a complete `--initial`.**
  `dfba-sensitivity` accepts `--initial` (same syntax as `dfba`). Closing untracked
  uptake removes *every* nutrient you did not name, including nitrogen, phosphate,
  sulfate and trace metals — so the default four-substrate `--initial` starves the
  model and the whole grid stalls. Measured on `models/iML1515.xml`:

  ```bash
  # WRONG — closes 22 exchanges, starves the model
  uv run cmig dfba-sensitivity --model models/iML1515.xml \
    --dts 0.2,0.1 --kms 0.01,0.02 --close-untracked-uptake --out runs/bad
  # exit 3; n_stalled 4/4; every final_biomass 0.01 (= initial biomass, no dynamics)
  # "every run stalled before producing dynamics … a --close-untracked-uptake run
  #  needs every required nutrient in --initial"
  ```

  Derive the list from a plain run's `untracked_uptake` field, then supply all of
  them non-limiting:

  ```bash
  uv run cmig dfba-sensitivity --model models/iML1515.xml \
    --dts 0.2,0.1 --kms 0.01,0.02 --close-untracked-uptake \
    --initial "EX_glc__D_e=10,EX_o2_e=20,EX_ac_e=0,EX_lac__D_e=0,\
EX_nh4_e=100,EX_pi_e=100,EX_so4_e=100,EX_k_e=100,EX_ca2_e=100,EX_cl_e=100,\
EX_fe2_e=100,EX_mg2_e=100,EX_mn2_e=100,EX_zn2_e=100,EX_cu2_e=100,\
EX_cobalt2_e=100,EX_ni2_e=100,EX_mobd_e=100" \
    --out runs/dfba_sensitivity
  # exit 0; interpretable True; no_untracked_uptake True; 4/4 completed
  # final_biomass 0.0536 (dt 0.1) vs 0.0503 (dt 0.2) — a real step-size signal
  ```

  Only the second form is an interpretable Km/dt audit. Note the ~6 % dt
  dependence it exposes: that is the artifact this audit exists to catch.

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
sensitivity, and optional host coupling into one checksummed manifest with a
`publication_ready` flag. See `docs/PUBLICATION_VALIDATION.md` for a fully specified
real-model command, and **read `uv run cmig publication-benchmark --help` before
using it — it exposes 33 options**, more than any other command, spanning every
sub-analysis it bundles. This reference does not reproduce that surface.

Two limits to know before you route a publication run here:

- **It cannot satisfy the dFBA guardrail.** `publication-benchmark` accepts **no
  `--close-untracked-uptake`** (verified: 0 hits in `--help`). Its bundled dFBA
  sensitivity therefore runs with untracked uptake left open, which is exactly the
  configuration that makes a substrate/Km result uninterpretable. If your claim
  depends on a dFBA endpoint, run `cmig dfba-sensitivity` **separately** with
  `--close-untracked-uptake` and a complete `--initial`, and cite that run — do not
  rely on the bundle's dFBA leg.
- **It also rejects `--allow-failed-run`**, so it cannot be made to exit 0 on a
  failed sub-analysis.
- Its dFBA sub-run derives its manifest status from `dfba_completed` /
  `dfba_balance_passed` only, so that manifest can read `status: ok` while
  `acceptance.interpretable` beside it is `false`. `inspect-run`'s
  `acceptance.interpretable` veto is what catches this — check `status_source`.

---

## Inspection, reproducibility, utilities

- `uv run cmig workflows --format json|text` — the GUI-to-CLI workflow map (15
  workflows, `schema_version 1.0`); read first, but treat `--help` as ground
  truth for flags.
- `uv run cmig inspect-run --run-dir <dir> --format json|text` — machine-readable run
  inspection: kind, status (+ `status_source`), `run_hash`, `result_digest`,
  `artifact_integrity`, the `edges.weight basis:` disclosure, summary, and
  artifacts. Exits 3 on `artifact_integrity: mismatch`.
- `cmig golden verify` — MICOM/solver-version golden regression gate; compares
  hashes, parametrized over gurobi and osqp.
- `cmig golden verify-envelope` — the workflow-manifest analogue: catches
  serialization drift that would silently move published workflow hashes. Run it
  alongside `golden verify` whenever the environment changes.
- `cmig solvers` — solver capability matrix (LP/QP/MILP/available). It lists
  `highs`, which **no command's `--solver` accepts**; availability is not
  selectability.
- `cmig namespace-suggest` — draft an exchange-namespace decision for a model.
- `cmig sweep` — taxonomy-based parameter sweeps over solver, medium, members,
  abundance, and bounds (`sweep_summary.json`, `sweep.parquet`, `runs/`).
  Options: `--tradeoff-fs`, `--solvers`, `--mediums`, `--member-sets`,
  `--abundance-variants`, `--bounds-variants`, `--fva`, `--fva-metabolites`,
  `--metric`, `--allow-unknown-medium`, `--allow-failed-run`,
  `--assume-bigg-namespace`. Sweep status is **derived from the rows**, so a
  sweep in which every condition failed exits 3 — check `$?` and per-condition
  `status` rather than the summary alone.
- `cmig render-figure` — render a run's tidy profile to a publication figure (R
  ggplot2, matplotlib fallback).
- `cmig model-quality`, `cmig model-review`, `cmig publication-benchmark` — see
  above.
- `cmig host-generic`, `cmig host-benchmark` — generic host smoke solve and
  Human-GEM/Recon3D benchmark; not part of the reviewed host-coupling path.
- `cmig sandbox-fixture` — preview or commit a reaction-bound edit on the
  bundled fixture community.
- `cmig version`, `cmig gui` — version string; launch the desktop GUI.

## Fixture demos

Deterministic demos that need no user models — useful for smoke tests and for
learning output shapes:
```bash
uv run cmig solve-fixture --solver gurobi --out runs/solve_fixture
uv run cmig search-fixture --out runs/search_fixture
uv run cmig search-advanced-fixture --out runs/search_advanced_fixture
uv run cmig host-fixture --out runs/host_fixture
uv run cmig dfba-fixture --out runs/dfba_fixture
uv run cmig sweep-fixture --out runs/sweep_fixture
uv run cmig stats-demo --out runs/stats_demo
```

`search-advanced-fixture` runs in seconds and writes
`search_advanced_summary.json` with keys `strategy`, `targets`, `pareto_frontier`,
`top_ranked` and `warnings` — the cheap way to learn the multi-target output shape.
Its fixture uses **exactly 2 targets** (`ac`, `but`), which is why a
`pareto_frontier` is present; that is the 2-target case discussed above, not the
general `--multi-metric pareto` mode.

Prefer it over a real search while iterating: `--target-preset scfa` over the 5
bundled genome-scale models took **13–18 minutes per metric** on this machine, so
choose the metric before you launch, not after.
