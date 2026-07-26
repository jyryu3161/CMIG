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

## Operating principle: preflight → discover → run → verify

CMIG is designed to be driven by agents. Always follow this loop instead of
guessing command names or flags.

0. **Preflight — confirm the environment before a long run.** A genome-scale
   analysis can run for 15+ minutes, so spend two seconds proving the engine
   stack is reachable first:
   ```bash
   uv run cmig version && uv run cmig solvers
   ```
   `solvers` must print a capability matrix with `gurobi … available True`. If
   either command fails with `엔진 stack 필요` / `requires the engine stack`,
   MICOM is not installed in the environment you just resolved and **every
   analysis command will fail** — fix that before running anything.

   `uv run cmig …` is the project's normal invocation and is what
   `cmig workflows` emits. If you are working against an already-activated
   environment or a non-`uv` install, `cmig <command>` and
   `python -m cmig.cli.main <command>` are equivalent — use whichever the
   preflight proves.

   > **Run `uv run` from the directory whose environment was synced.** `uv run`
   > resolves the *nearest* project root and uses that project's `.venv`. A git
   > worktree, a sibling checkout, or a vendored subproject carries its own
   > `pyproject.toml`, so `uv run` there resolves a **different project** and
   > silently provisions a fresh minimal `.venv` with **no `engine` extra** —
   > `cmig workflows` still succeeds while every analysis command dies with
   > `… 는 엔진 stack 필요: uv sync --extra engine`. Worse, that message names a
   > fix that would sync the *wrong* project. Measured: from the synced checkout
   > `uv run` gives `…/CMIG/.venv` with `micom 0.39.0`; from a worktree of the
   > same repo it creates `…/CMIG-wt-*/.venv` with 14 packages and no micom.
   > The preflight above catches this in one command.

1. **Discover.** Read the machine-readable workflow map:
   ```bash
   uv run cmig workflows --format json
   ```
   It maps every GUI analysis surface (e.g. `Search / Find Best Model
   Combination`, `Host / Run Host-Microbe`, `Dynamics / Run dFBA`) to the exact
   `cmig` command, required args, common options, expected artifacts, and one
   copyable example.

   **`workflows` lists a workflow's *common* options, not its
   answer-determining ones.** `uv run cmig <command> --help` is the only
   authoritative flag list, and several flags that change the scientific meaning
   of the result are absent from the `workflows` map — see *Answer-determining
   flags* below. Read `--help` for any command before you run it.
2. **Run** the chosen workflow with an explicit `--out runs/<name>` directory.
3. **Verify.** After every run, inspect the output directory in a stable form:
   ```bash
   uv run cmig inspect-run --run-dir runs/<name> --format json
   ```
   This reports the workflow kind, status, run hash, `result_digest`,
   `artifact_integrity`, and artifacts — the CLI counterpart to opening a run in
   the GUI Profile view. Report `status`, both fingerprints, and the key summary
   numbers back to the user; do not just say "done".

   **Check the analysis command's exit code too — `inspect-run` does not
   re-judge a run.** It reports what the run recorded, and it exits non-zero only
   when the artifacts contradict the manifest. `$?` from the analysis command is
   the verdict; `inspect-run` is the description.

   Read **`status_source`** alongside `status`: it names where the verdict came
   from (`manifest`, `summary`, `derived`, `acceptance.interpretable`,
   `no_status_signal`, …). Two consequences worth knowing:
   - **`unknown` is a real answer.** A recognised summary that records no
     run-level outcome reports `status: unknown` with
     `status_source: no_status_signal` — it does **not** report `ok`. Treat
     `unknown` as "this artifact does not say how the run went", never as a pass.
   - **`status` may legitimately disagree with `manifest.status`.** A run that
     stamps itself `acceptance.interpretable: false` vetoes a rosier manifest
     tier; the reported status wins and `status_source` shows which signal
     condemned it.
   - **The status vocabulary is not closed** — `infeasible` and `stalled` still
     reach `status` verbatim, so do not write a gate that only matches
     `ok`/`degraded`/`failed`/`unknown`. Treat anything unrecognised as not-ok.

CMIG is intentionally **local-file based**: it never downloads, curates, or
auto-selects external model catalogues (AGORA / VMH / Recon / Human-GEM /
BiGG). The user supplies their own SBML / JSON / MAT GEMs. If a request assumes
auto-download, correct it and ask for the local model directory.

## Intent → workflow routing

Match what the user wants to the workflow. Full commands, args, and outputs are
in `references/workflows.md`; read it before assembling a non-trivial command.

| The user wants to…                                              | Command |
| --------------------------------------------------------------- | ------- |
| Rank model combinations that best produce/consume **one** metabolite | `uv run cmig search --target <met>` |
| Rank combinations for **several** metabolites at once (e.g. "total SCFA") | `uv run cmig search --target-preset scfa --multi-metric pareto` — read the first *Critical decision point* below before choosing the metric |
| Compare each strain's growth alone vs inside the community      | `cmig strain-growth` |
| Test how one member's abundance changes a target/growth         | `cmig abundance-impact` |
| Rank single-gene (or reaction) knockouts in a fixed consortium  | `cmig gene-ko-search` |
| Couple a host GEM to microbial secretion/uptake (BiGG-style)    | `cmig host-microbe-bigg` |
| Ask how a **microbial knockout changes the host** (KO → host objective / target delivery delta) | `cmig host-ko-impact` |
| Rank microbial combinations by host objective + target transfer | `cmig host-search-bigg` |
| Build a candidate host↔microbe interface map for review         | `cmig host-map` |
| Solve a MICOM taxonomy community directly                       | `cmig solve` |
| Run well-mixed single-model dynamic FBA                         | `uv run cmig dfba --close-untracked-uptake` |
| Check a dFBA endpoint's numerical robustness                    | `uv run cmig dfba-sensitivity --close-untracked-uptake` |
| Preview a 2D source/sink medium gradient (design only)          | `cmig spatial-preview` |
| Review / QC a user-provided GEM before analysis                 | `cmig model-review`, `cmig model-quality` |
| Run the combined publication audit in one manifest              | `cmig publication-benchmark` — 33 options; read `--help`. **Its bundled dFBA leg cannot take `--close-untracked-uptake`**, so run `dfba-sensitivity` separately if a dFBA endpoint is load-bearing |
| Inspect or reproduce a finished run                             | `cmig inspect-run`, `cmig golden verify`, `cmig golden verify-envelope` |

When the goal is unclear, ask which metabolite, which model directory, and
whether this is an exploratory check or a publication run — the answer changes
which guardrails are mandatory (see below).

## Critical decision points (중요한 지점)

These are the points where a run quietly becomes scientifically invalid. CMIG
enforces most of them with required flags; your job is to set them correctly
and to *explain the choice in the result*, not to route around them. Depth and
exact flags are in `references/scientific-validity.md` — read it before any
host-microbe or publication run.

- **A "total SCFA" question must not be answered with the default
  scalarisation.** `cmig search` accepts several targets (`--targets ac,but` or
  `--target-preset scfa`, which expands to `ac,but,lac__D,lac__L,ppa,succ`), and
  by default scores them with `--multi-metric normalized_weighted` — a linear
  weighted sum. A linear scalarisation is optimised **at a vertex** of the
  achievable set, so it systematically returns a **single-metabolite
  specialist** (in practice the highest-flux acid, acetate) rather than a
  balanced SCFA producer. Reporting that winner as "the best total-SCFA
  community" is a wrong conclusion, not a rounding error.
  - For "which community makes the most SCFA overall", use
    **`--multi-metric pareto`**, a *different code path*: an epsilon-constraint
    sweep per consortium whose N-dimensional **non-dominated set** is reported in
    absolute units. It works for any number of targets and is much slower than
    the scalar metrics. Present the frontier and let the user pick the trade-off;
    do not silently collapse it. In this mode `rank` is a **reporting order**
    (weighted sum), *not* a claim that rank 1 is best — say so. The run also
    reports how many front points are themselves single-metabolite specialists.
  - **Mode ≠ column.** A *scalar*-metric ranking also carries a `pareto` boolean
    column, computed **only for exactly two targets**. With more targets every
    cell stays `False`, meaning "not evaluated", not "dominated" — filtering a
    6-target scalar ranking on `pareto == True` returns nothing, which is not a
    finding.
  - `--multi-metric carbon_equivalent` gives an **absolute, run-comparable** total
    in mmol C gDW⁻¹ h⁻¹ by weighting each target by its carbon number from the
    model formula. Use it when the question is genuinely "most carbon as SCFA" —
    but **it is still a linear scalarisation and still collapses onto a vertex.**
    Measured on the same pool, every one of its 9 ranked candidates returned
    `but=0, lac__D=0, lac__L=0, ppa=0`; it merely collapses onto a *different*
    vertex (acetate + succinate) than `normalized_weighted` does (D-lactate).
    Choosing it fixes the *units* problem, not the *specialist* problem.
  - `--multi-metric raw_sum` **adds C2 and C4 acids as if they were the same
    quantity** — only use it if the user explicitly wants molar sum, and say so.
    It is linear too, so the same vertex collapse applies.
  - **Only `pareto` escapes the collapse.** All three scalar metrics are linear
    objectives; the vertex behaviour is a property of linear scalarisation, not of
    any particular weighting. If the user's question is "which community is best
    overall", no choice of weights answers it — the frontier does.
  - `normalized_weighted` is min-max normalised **over the candidate set of that
    run**, so its scores are *not comparable across runs*. Never compare a
    normalized_weighted score between two searches.
  - Per-target direction matters: `--target-directions` overrides `--direction`
    per target, so "produce butyrate but consume lactate" is expressible. If you
    leave it unset every target uses the single `--direction`.
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
  - Entries the wizard cannot settle are flagged `needs_review`, and the host
    commands **refuse to couple** while any remain. `--accept-unreviewed-map`
    overrides that; it is not a formality. The specific hazard it waives is
    **D/L stereoisomer confusion** — annotation matching can pair `lac__D` with
    `lac__L`, which makes the host grow on a molecule it cannot transport. If you
    pass it, the run is warned and the entries are named: surface both.
- **A custom medium is only trustworthy in a post-fix run.** CMIG applies a
  medium by translating it to the community's exchange *reactions* per
  metabolite, so a currently-closed exchange **does get opened**. An earlier
  implementation gated on the already-open uptakes, which silently applied
  almost nothing (acetate, butyrate, lactate, succinate and glycerol among the
  nutrients that never took effect) while the manifest still stamped the
  requested `medium_checksum` and minted a `run_hash` certifying it.
  - **Any pre-fix run that used `--medium` is invalid and must be re-run.** Its
    numbers were produced under a medium that was never applied. Tell the user
    this rather than reusing the cached result — and note the `run_hash` will not
    reveal it, because the fix deliberately changed published numbers *without*
    moving any hash (`solve --medium` moved 0.881561 → 1.125065 under an
    identical hash).
  - **How to tell them apart:** a post-fix run records
    `provenance.medium_policy: "exchange_reactions_by_metabolite_v2"`. Check it
    with `uv run cmig inspect-run --run-dir <dir> --format json`. Absent or
    `open_uptakes_exact_key_v1` ⇒ re-run.
  - **Do not hedge namespaces.** Listing the same metabolite under two
    namespaces (e.g. both `EX_glc__D_m` and `EX_glc__D_e`) is now rejected as a
    spec-level input error (exit 2) in both `solve` and `search`. Pick one.
  - **`--allow-unknown-medium` costs more than it looks.** Without it, a medium
    id with no counterpart in the community is a hard input error (exit **2**).
    With it, those nutrients are **dropped** and the run continues: measured on a
    2-member community with one bogus id, the run exits **0** with
    `status: degraded`, a `medium_unapplied` diagnostic naming the dropped id —
    and a `medium_checksum` still computed over the **full requested** medium.
    So `$?` says success and the hash certifies a medium that was only partly
    applied. Use it only to diagnose a medium file, never for a reported result,
    and always quote the dropped ids.
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
- **A dFBA run is not a substrate/Km experiment until untracked uptake is
  closed.** By default CMIG tracks only the exchanges named by `--initial`
  (default: glucose, oxygen, acetate, D-lactate). Every *other* uptake left open
  by the model's default medium has **no concentration**, so it is never
  depleted and no Michaelis-Menten term applies to it — biomass can rise while
  the tracked substrate is untouched. Pass **`--close-untracked-uptake`** (or
  track those exchanges explicitly with `--initial`). Reproduction on a bundled
  model:
  ```bash
  uv run cmig dfba --model models/iML1515.xml --dt 0.1 --out runs/dfba_plain
  # -> exit 0, status "completed", final_biomass 0.6654843209450042
  # -> n_untracked_uptake: 14, and warnings says a Km sweep is NOT interpretable
  ```
  The run *succeeds and reports a biomass number* while its own `warnings` field
  says the experiment is uninterpretable. Auditing `--dt`/`--km` on that setup
  produces a "robust across Km" conclusion that is meaningless, because Km was
  never rate-limiting.
- **Then audit the endpoint's numerical sensitivity.** The endpoint can still
  depend on the integration step `--dt` and the half-saturation constant `--km`,
  so run `uv run cmig dfba-sensitivity --close-untracked-uptake` across a range of
  `--dts` and `--kms`. Read `acceptance.interpretable` and
  `acceptance.not_interpretable_because` in `dfba_sensitivity.json` — the grid is
  rejected if **any** row is infeasible or **all** rows stalled, and the command
  exits 3 when it is not interpretable. Also note `--initial` values are strict
  and must exist in the model.
- **Knockout screens must not silently sample a subset.** In
  `gene-ko-search`, `--max-genes 0` evaluates every target. If `--max-genes`
  truncates the set, CMIG records a `warnings` entry and `n_genes_total`, and
  `--gene-selection id|random` plus `--seed` make truncation reproducible.
  Prefer `--max-genes 0` for a complete screen; if you cap it, surface the
  warning and the evaluated-of-total count.
- **`spatial-preview` is a design tool, not a spatial FBA engine.** It models
  diffusion / source / sink medium layout only; it does **not** solve FBA on
  each grid cell. Never describe its output as spatial community dFBA results.
- **`edges.parquet.weight` is a PER-TAXON flux — never rank members by it.**
  Edge weights are `mmol gDW_taxon⁻¹ h⁻¹`, *unweighted by abundance*, and they
  are unsigned magnitudes. A low-abundance member therefore shows a large edge
  while contributing little to the community, so **the ranking inverts against
  true community contribution.** Measured on a real 2-member solve
  (*C. ljungdahlii* iHN637 at abundance 0.1, *E. coli* iML1515 at 0.9), acetate
  secretion:

  | member  | abundance | `edges.weight` | × abundance (community basis) |
  | ------- | --------- | -------------- | ----------------------------- |
  | iHN637  | 0.1       | 3.876102       | 0.387610                      |
  | iML1515 | 0.9       | 0.459437       | **0.413494**                  |

  By edge weight iHN637 looks like the dominant acetate producer by 8.4×; by
  community contribution iML1515 is actually the larger contributor. To compare
  members, **multiply each weight by that member's abundance** — that sum
  reproduces `profile.parquet.net_flux` (0.801104 here) for metabolites well above
  the 1e-6 noise floor — measured 23/25 to <1e-9, with `mobd` and `btn` off by
  ~1e-8, and 19 of 44 edge metabolites having no profile row at all. Also exclude
  `edge_type == cross_feeding` rows: they are a mass-conserving *proportional
  allocation*, not a measured pairwise transfer (`identifiable: false`). The run
  discloses all of this in `manifest.json → edge_attribution`, which
  `uv run cmig inspect-run --format text` prints as the `edges.weight basis:` line —
  read it before quoting any edge magnitude.
- **`strain-growth`'s alone-leg medium decides whether the result is an
  interaction effect at all.** `--single-medium community` (default) projects the
  community's effective medium onto each member, so alone-vs-community is a
  controlled comparison. `--single-medium model_default` keeps each member's
  native SBML bounds, which reports **native capability, not an interaction
  effect** — the difference then conflates a medium change with cross-feeding.
  State which one you used, and do not read `model_default` deltas as
  cross-feeding. Even under `community`, check each row's
  `medium_metabolites_unavailable_to_member`: a non-empty value means that member
  could not receive part of the projected medium, so the comparison was not fully
  controlled for it.
- **Abundance sweeps are sensitivity, not causality.** `abundance-impact`
  rescales one member's abundance under the same models and medium. Report it as
  a sensitivity analysis, not proof of ecological causation. Pass **`--fva`** so
  each sweep point carries the target exchange's FVA interval: without it, a jump
  between neighbouring abundances is indistinguishable from alternate-optima
  degeneracy, and reading it as a dose response is a wrong conclusion.

## Answer-determining flags the workflow map does not list

`cmig workflows` reports each workflow's *common* options. These change what the
number **means**, and are easy to miss because they default to the permissive
choice. Always decide them explicitly.

| Command | Flag | Why it decides the answer |
| ------- | ---- | ------------------------- |
| `search` | `--targets` / `--target-preset scfa` | multi-target mode; without it only one metabolite is ranked |
| `search` | `--multi-metric` | `normalized_weighted` (default) collapses onto a single-metabolite specialist; use `pareto` or `carbon_equivalent` |
| `search` | `--target-directions` | per-target produce/consume; otherwise all targets share `--direction` |
| `search` (**single-target only**) | `--robustness-fva` | without it a ranking cannot be told from alternate optima. **Silently inert in multi-target mode** — accepted, no columns, no warning, exit 0 |
| `strain-growth` | `--single-medium` | `model_default` reports native capability, **not** an interaction effect |
| `abundance-impact` | `--fva` | separates a dose response from alternate-optima degeneracy |
| `dfba`, `dfba-sensitivity` | `--close-untracked-uptake` | without it a substrate/Km experiment is not interpretable |
| `solve`, `search`, `strain-growth`, `abundance-impact`, `sweep` | `--allow-unknown-medium` | silently drops nutrients; run exits 0 as `degraded` |
| `solve`, `sweep`, `publication-benchmark` | `--assume-bigg-namespace` | waives the namespace-decision review gate |
| host commands | `--accept-unreviewed-map` | waives the D/L stereoisomer review gate |
| host commands | `--keep-host-uptake` | leaves pre-existing host uptake open, so "host benefit" may be background medium |
| `solve`, `search`, `strain-growth`, `abundance-impact`, `gene-ko-search`, `sweep`, `dfba-sensitivity`, and the 3 host commands | `--allow-failed-run` | makes a failed scientific run exit 0. **Not accepted by `dfba`, `model-quality`, `publication-benchmark`, `spatial-preview`, `model-review`** — passing it there is an argparse error (exit 2) |
| `gene-ko-search` | `--rank-by {effect,remaining}` | sets the entire KO ordering: `effect` (default) ranks by \|delta\|, `remaining` by highest remaining target flux |

## Exit codes — a failed run is non-zero

Round-5 hardening made this a contract. Do not read artifacts without checking
`$?`:

| Code | Meaning |
| ---- | ------- |
| `0` | ran, and the scientific solve succeeded (or `--allow-failed-run` was passed) |
| `2` | **input** error — bad medium spec, aliased namespaces, missing exchange counterpart |
| `3` | artifacts were written but **the scientific solve did not succeed**, or `inspect-run` found `artifact_integrity: mismatch` |

`--allow-failed-run` exists for pipelines that want the artifacts anyway; it
turns a 3 into a 0 and **does not make the run a result**. Every analysis command
has it, including `sweep`. If you pass it, say so and quote the failure.

## Verifying a result: two fingerprints, not one

The honest split, as recorded in the code:

- **`run_hash` certifies the INPUTS.** Identical inputs ⇒ identical hash. It
  does *not* certify the answer: the medium fix changed published numbers under
  identical hashes by design.
- **`result_digest` certifies the ANSWER** — it fingerprints the artifact bytes
  the run actually wrote, including figures. `cmig inspect-run` recomputes it and
  reports `artifact_integrity: verified | mismatch | not_recorded`. A mismatch
  flips `status` to `failed` and exits 3.

Report both. Two caveats to state honestly rather than paper over:

- `result_digest` is written by the **workflow manifest**, which covers 13 kinds
  (`model_pool_search`, `multi_target_model_pool_search`, `strain_growth`,
  `abundance_impact`, `gene_ko_search`, `host_microbe_bigg`, `host_search_bigg`,
  `host_ko_impact`, `sweep`, `dfba`, `model_quality`, `host_map`,
  `publication_benchmark`). **`cmig solve` does not emit one** — `inspect-run` on a
  solve run reports `result_digest: not recorded` with
  `result_digest_absent_reason: solve_manifest_never_records_one`, even for a
  brand-new run. Do not read that as tampering. The other reasons are
  `no_manifest`, `workflow_manifest_predates_result_digests` (the only case where
  "predates" is true) and `manifest_declares_no_scope`; read the field rather than
  inferring a cause.
- `cmig golden verify` is the MICOM/solver-version regression gate;
  `cmig golden verify-envelope` is its workflow-manifest analogue, catching
  serialization drift that would silently move published workflow hashes. Run
  both when the environment changes.

## Environment notes

- `uv run cmig …` is the normal invocation. The engine extra must be synced
  (`uv sync --extra engine`); the GUI, render, and stats extras are optional
  (`uv sync --extra engine --extra gui --extra render --extra stats`). Run `uv run`
  from the checkout you synced — see the preflight above.
- The default full workflow expects **Gurobi 12.x** with a valid license and
  pins `micom==0.39.0`. Check availability with `uv run cmig solvers`.
- `cmig solvers` reports `highs` as available, but **no command exposes it**:
  `--solver` accepts `{gurobi, osqp}` (`solve`, `dfba`, `dfba-sensitivity`,
  `sandbox-fixture`) or `{gurobi}` only (`search`, `strain-growth`,
  `abundance-impact`, `gene-ko-search`, `model-quality`,
  `publication-benchmark`, and the host commands). Availability in the matrix is
  not selectability.
- Reproducibility is a first-class feature: runs emit manifests, run hashes and
  result digests; `cmig inspect-run` reads them back. Preserve `--out`
  directories you want to cite.
- **The bundled `models/` pool is not a gut community.** iML1515 (*E. coli*) is
  the only common gut resident; *B. subtilis* (iYO844) is soil/transient,
  *Geobacter* (iAF987) is a sediment metal reducer, *Shigella* (iSFV_1184) is a
  pathogen, *C. ljungdahlii* (iHN637) is an industrial acetogen. Results over
  this pool are a methods demonstration, not gut biology — say so, and never let
  a figure imply otherwise.

## References

- `references/workflows.md` — per-command reference: purpose, required args,
  useful options, key outputs, and a copyable example for every workflow.
- `references/scientific-validity.md` — the guardrails above in depth, with the
  rationale and the exact flags, for host-microbe and publication runs.
- `references/outputs.md` — how to read run directories, `inspect-run` kinds,
  summary/figure artifacts, and how to reproduce or cite a run.
