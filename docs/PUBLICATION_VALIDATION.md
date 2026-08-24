# CMIG Publication Validation

This is the release-time publication-preflight procedure. Runtime outputs belong under `.run/`,
must not enter a source distribution, and should be archived with the release or paper.

The prior version of this document predated boundary isolation and is not valid evidence.
**VERIFIED AGAINST CODE**, the old host-objective expectation near `368.01` came from undeclared
Recon3D sink/demand uptake. **VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`**, the
corresponding post-policy host objective is `0.0`, an honest null. Do not compare a new run to
`368.01` as though it were a regression target.

## Evidence labels

Every claim below has one of these labels:

- **VERIFIED AGAINST CODE** — checked against the current command help, workflow map, manifest
  contract, or tracked provenance code. This establishes behavior or structure, not a new solver
  result.
- **VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`** — copied from the licensed Gurobi
  scenario record at commit `ac1adf3`. These values are historical controls, not release results.
- **TO RE-RUN AT RELEASE** — requires the release candidate, licensed solver, external model, or
  study-specific input. The exact command is supplied; replace only the declared placeholders.

## Release inputs and preflight

Use the tracked Recon3D acquisition path rather than the unregistered
`fixtures/Human-GEM-v1.19.0.xml` file previously named here. CMIG does not redistribute the model.

```bash
uv sync --all-extras --group dev
uv lock --check
uv run cmig version
uv run cmig solvers
uv run cmig --help
uv run cmig publication-benchmark --help
uv run cmig host-map --help
uv run cmig host-microbe-bigg --help
uv run cmig dfba-sensitivity --help
uv run cmig workflows --format json
uv run cmig golden verify-envelope
uv run cmig golden verify
uv run python scripts/download_human_gems.py
uv run python scripts/download_human_gems.py --verify --counts
```

**TO RE-RUN AT RELEASE.** Record the complete stdout, command exit codes, release commit, operating
system, Python version, CMIG version, solver capability matrix, solver/license version, MICOM and
COBRApy versions, and the two golden-gate results. `data/gems/GEM_SOURCES.json` is the tracked
checksum/count record for Recon3D; the last command must reproduce it before continuing.

Set release-specific paths and scientific bases:

```bash
export HOST_MODEL="data/gems/Recon3D.xml"
export MICROBIAL_MODEL_DIR="<directory containing the intended microbial GEM pool>"
export MICROBIAL_BIOMASS_GDW="<study microbial dry mass in gDW>"
export HOST_BIOMASS_GDW="<host dry-mass basis represented by the host model in gDW>"
export BIOMASS_BASIS_SOURCE="<measurement record, Methods section, or literature citation>"
export DFBA_INITIAL="<complete comma-separated exchange=concentration list>"
```

**VERIFIED AGAINST CODE.** `measured` or `literature` biomass bases need positive numeric values and
a traceable source. `validation` is for engineering checks and forces the result to remain
non-publication-ready. Recon3D's shipped objective is `BIOMASS_maintenance`, which is maintenance,
not growth; any growth claim must explicitly select `BIOMASS_reaction` on a command that exposes
`--host-objective`.

## Review the host interface

```bash
uv run cmig host-map \
  --host "$HOST_MODEL" \
  --model-dir "$MICROBIAL_MODEL_DIR" \
  --out .run/publication-validation/host-map
```

**TO RE-RUN AT RELEASE.** Review
`.run/publication-validation/host-map/host_interface_map.json` entry by entry. Resolve every
`needs_review` entry, especially D/L stereoisomers, and record the reviewer and date. The old
expectation of 204 matches among 520 candidates is retired; map counts depend on the exact host and
microbial pool and must be reported from this release run.

**VERIFIED AGAINST CODE.** `host-map` emits a review draft. An annotation match is a computational
candidate, not authorization to couple that metabolite. `--accept-unreviewed-map` is a recorded
waiver and is not used in this procedure.

## Integrated benchmark

Run the integrated bundle with the reviewed map and without `--keep-host-uptake`:

```bash
uv run cmig publication-benchmark \
  --model-dir "$MICROBIAL_MODEL_DIR" \
  --assume-bigg-namespace \
  --search-target ac \
  --search-min-size 2 \
  --search-max-size 2 \
  --dfba-model models/iML1515.xml \
  --dfba-t-end 2 \
  --dfba-dts 0.2,0.1,0.05 \
  --dfba-kms 0.005,0.01,0.02 \
  --host "$HOST_MODEL" \
  --host-name Recon3D \
  --host-version BiGG-Recon3D-retrieved-2026-07-26 \
  --host-source-url http://bigg.ucsd.edu/static/models/Recon3D.xml.gz \
  --host-doi 10.1038/nbt.4072 \
  --host-interface-map .run/publication-validation/host-map/host_interface_map.json \
  --microbial-biomass-gdw "$MICROBIAL_BIOMASS_GDW" \
  --host-biomass-gdw "$HOST_BIOMASS_GDW" \
  --biomass-basis-kind measured \
  --biomass-basis-source "$BIOMASS_BASIS_SOURCE" \
  --out .run/publication-validation/integrated
```

**TO RE-RUN AT RELEASE.** Archive the entire output directory and record the analysis command's
exit code before inspecting the output. Then run:

```bash
uv run cmig inspect-run \
  --run-dir .run/publication-validation/integrated \
  --format json
```

Record `status`, `status_source`, `run_hash`, `result_digest`, `artifact_integrity`, warnings,
limitations, checksums, solver/dependency versions, timings, each component status, and every
reported numeric result. There is deliberately no frozen expected model objective, community
growth, search flux, map count, solve time, or dFBA endpoint in this document.

**VERIFIED AGAINST CODE.** `publication-benchmark` does not expose
`--close-untracked-uptake`. Therefore its bundled dFBA leg cannot establish that a substrate/Km
experiment is isolated from untracked nutrient supply. `overall_passed` or `publication_ready`
does not waive that limitation.

**VERIFIED AGAINST CODE.** The integrated command also does not expose `--host-objective`.
Recon3D's integrated host leg therefore uses its shipped `BIOMASS_maintenance` objective and must
be labelled as maintenance, never growth. The separate host-isolation control below is the command
that explicitly tests `BIOMASS_reaction`.

## Separate load-bearing dFBA audit

When the dFBA endpoint will be quoted, run the numerical audit separately with a complete tracked
medium:

```bash
uv run cmig dfba-sensitivity \
  --model models/iML1515.xml \
  --initial "$DFBA_INITIAL" \
  --close-untracked-uptake \
  --t-end 2 \
  --dts 0.2,0.1,0.05 \
  --kms 0.005,0.01,0.02 \
  --out .run/publication-validation/dfba-sensitivity
```

**TO RE-RUN AT RELEASE.** Report every grid-row status and endpoint together with
`acceptance.interpretable` and `acceptance.not_interpretable_because`. Do not reuse the old claims
that 9/9 rows completed, residuals were zero, or one time step was about 9.5% below another; all
must be recomputed with the complete `DFBA_INITIAL` and current boundary isolation.

**VERIFIED AGAINST CODE.** With `--close-untracked-uptake`, any intended nutrient omitted from
`--initial` is closed. A stalled or infeasible grid remains an invalid endpoint even though
diagnostic artifacts were written.

## Post-round-6 host-isolation control

The release candidate must also reproduce the host null with an explicit growth objective. Use a
three-member directory containing only `iHN637`, `iML1515`, and `iYO844` for this engineering
control:

```bash
export ROUND6_THREE_MEMBER_DIR="<directory containing only iHN637, iML1515, and iYO844>"

uv run cmig host-microbe-bigg \
  --host "$HOST_MODEL" \
  --model-dir "$ROUND6_THREE_MEMBER_DIR" \
  --solver gurobi \
  --tradeoff-f 0.5 \
  --host-objective BIOMASS_reaction \
  --microbe-medium medium_presets/gut_overlay_vmh_high_fiber_x100.csv \
  --allow-unknown-medium \
  --microbial-biomass-gdw 1.0 \
  --host-biomass-gdw 1.0 \
  --biomass-basis-kind validation \
  --biomass-basis-source "round-6 engineering control; unit gDW bases" \
  --out .run/publication-validation/round6-host-isolation-control
```

**VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`.** On the round-6 environment this control
gave microbial community growth `0.0847149208736683`, `host_status: optimal`, and
`host_objective: 0.0`; the medium investigation identified `EX_n2_m` as the unmatched row. The host
value is the expected honest null. **VERIFIED AGAINST CODE**, using
`--allow-unknown-medium` records that dropped id and makes the run degraded. The obsolete
pre-isolation value near `368.01` was independent of the microbiome and must never be restored as a
target.

**TO RE-RUN AT RELEASE.** The release result must preserve the qualitative contract above. Record
the fresh numeric community growth rather than assuming bit identity across a changed solver or
dependency environment. Confirm both provenance markers through `inspect-run`:

```bash
uv run cmig inspect-run \
  --run-dir .run/publication-validation/round6-host-isolation-control \
  --format json
```

Expected current marker values, **VERIFIED AGAINST CODE**, are
`boundary_isolation_policy: boundary_reactions_v1` and
`host_isolation_policy: all_boundary_uptake_v2`. Their absence identifies a pre-fix run.

**VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`.** The five-member bundled pool fails on the
shipped gut overlays both in standalone solve and host coupling. That is a pool/medium limitation,
not evidence that the host path is over-constrained. Exit 3 and `status: failed` are the honest
outcome; do not publish a fabricated zero for a failed solve.

## Claim-by-claim acceptance ledger

| Claim | Evidence basis | Release action |
|---|---|---|
| Undeclared host sinks/demands are closed, not just `EX_*` uptake | **VERIFIED AGAINST CODE** | Inspect both isolation markers and warnings. |
| The old host objective near `368.01` is invalid; the controlled host growth objective is `0.0` | **VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`** | Re-run the explicit host-isolation control. |
| Three-member VMH control can continue after explicitly dropping `EX_n2_m` | **VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`** | Confirm degraded status and named dropped id. |
| Five-member gut-overlay failure is a pool/medium limitation | **VERIFIED AGAINST `REVIEW/SCENARIO_RESULTS_ROUND6.md`** | If re-tested, preserve exit 3 and diagnostic; do not coerce a number. |
| Interface-map counts and matched metabolites | **TO RE-RUN AT RELEASE** | Review and archive the fresh map; no frozen count. |
| Model objectives, community growth, search ranking/fluxes, host objective, timings | **TO RE-RUN AT RELEASE** | Report directly from the release artifacts with basis and solver. |
| dFBA endpoint and `dt×Km` sensitivity | **TO RE-RUN AT RELEASE** | Use the separate closed-uptake audit and report interpretability. |
| CLI flags and required biomass provenance | **VERIFIED AGAINST CODE** | Keep the captured `--help` outputs with the archive. |
| Workflow input and artifact fingerprints are different guarantees | **VERIFIED AGAINST CODE** | Report both `run_hash` and `result_digest`; require verified artifact integrity. |

## Output contract and interpretation limits

**VERIFIED AGAINST CODE.** `publication_benchmark.json` is the bundle's final commit marker. It
contains the computational/publication acceptance fields, scientific-input and dependency
provenance, checksums, timings, limitations, and component summaries. Subdirectories contain the
lossless JSON and flat outputs for the component workflows.

- Constraint-based predictions are conditional on reconstruction, objective, medium, abundance,
  biomass basis, boundary policy, and solver configuration.
- A deterministic parameter grid is not a biological replicate. CMIG blocks sweep p-values unless
  independent replicate ids are supplied and explicitly confirmed.
- Member transfer allocations are not causal or uniquely identifiable.
- A generic Recon3D cell is not a gut epithelium. A validation-basis run is an engineering result,
  not a publication-ready biological estimate.
- Any pre-round-6 host-objective, defined-medium, minimal-medium, or closed-uptake dFBA run on a
  model with sinks/demands must be re-run; its old numeric result is not release evidence.
