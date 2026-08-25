# Round-9 V1 report — community dFBA CLI and cross-run artifact determinism

## What changed and why

### `cmig dfba-community`

Added the proposed Gurobi-only community dFBA command to `cmig/cli/main.py` with the complete
round-8 U6 argument surface:

- required `--taxonomy`, `--t-end`, repeated `--initial EX_MET_m=VALUE`, repeated
  `--initial-biomass MEMBER=VALUE`, and `--out`;
- `--dt`, `--min-dt`, `--km`, `--growth-floor`, `--tradeoff-fraction`;
- repeated `--member-vmax MEMBER:EX_MET_m=VALUE`;
- `--close-untracked-uptake`, `--allow-failed-run`, and Gurobi-only `--solver`.

Repeated mappings preserve member/exchange identifiers, reject non-finite or negative values,
and reject duplicate assignments rather than silently choosing one. Taxonomy model paths are
resolved relative to the taxonomy CSV before MICOM is called.

The command calls the existing `run_community_dfba` integrator without redesigning it and writes:

- `community_dfba_summary.json` — raw scientific status, structured acceptance, initial and final
  state, limitations/warnings, and raw timing telemetry (`community_build_seconds` plus every
  `step_solve_seconds` sample);
- `community_dfba_timecourse.parquet` — the existing distinct long-format community timecourse;
- `community_dfba_events.json` — every structured adaptive-step, clamp, uptake, stall, readout, or
  solver event.

Exit behavior is derived only from the recorded `acceptance.interpretable` value: interpretable
runs exit 0; a completed/stalled but non-interpretable run or explicit solver failure exits 3;
input errors exit 2. `--allow-failed-run` softens 3 to 0 but does not change either the summary's
acceptance or the workflow manifest's failed status.

Added the command to `GUI_CLI_WORKFLOWS`, `RUN_SUMMARY_FILES`, and workflow-map coverage so
`cmig workflows` and `cmig inspect-run` both identify it correctly.

### Additive workflow envelope

Added the new workflow kind `community_dfba` with the single new
`community_dfba_spec` component. Its hash covers:

- the standard versions, solver, deterministic taxonomy/model checksum, and medium marker;
- explicit-Euler/non-negative integration policy and all numerical configuration;
- absolute initial biomasses and their derived initial relative abundances;
- initial shared-pool concentrations and explicit member/exchange vmax overrides;
- untracked-uptake closure and the `death_washout=not_modeled` policy.

Timing, events, warnings, final state, diagnostic, and acceptance remain output data and do not
enter `hash_components`. The new envelope was captured with the documented generator. No existing
workflow kind or frozen 11-component solve hash was changed.

### Measured deterministic artifact kinds

Measured the four round-8 kinds twice through the actual `cmig` console entry point with real
Gurobi and the same synthetic model, medium, baseline, and variant paths; only the output
directories differed. Every declared artifact was byte-identical, so all four were added to
`DETERMINISTIC_ARTIFACT_KINDS` alongside `host_map`:

- `pair`
- `delta`
- `single`
- `minimal_medium`

Added a parametrized regression that reruns every promoted kind twice and requires equal input
hashes, equal per-artifact byte digests, equal combined result digests, and a recorded
`cross_run_comparable=true` claim.

## Quantitative CLI validation

Basis: one real `uv run --no-sync cmig dfba-community` Gurobi invocation using U6's two-member
synthetic producer/consumer scenario. Both members started at `0.01 gDW/L`; shared glucose and
cross-feed pools started at `2.0` and `0.0 mmol/L`; `dt=0.1 h`, `Km=0.01`, `t_end=0.6 h`, explicit
member vmax values were `10 mmol/gDW/h`, and untracked uptake was closed.

- status: `completed`;
- `acceptance.interpretable`: `true`;
- 7 timepoints / 6 solved steps;
- final consumer biomass: `0.2289380182067826 gDW/L`;
- final shared cross-feed concentration: `1.0210854870573405 mmol/L`.

This reproduces U6's reported cross-feeding endpoint to the displayed precision.

The same run retained the following raw operational timing sample. These values are one local
wall-clock observation, not deterministic scientific results and not hash inputs:

- community build: `0.5821359999245033 s`;
- step solves:
  `[0.0048050000332295895, 0.002594333956949413, 0.0028471669647842646,
  0.003074042033404112, 0.0026596669340506196, 0.0036974999820813537] s`;
- mean step solve: `0.0032796183174165585 s`.

Selected `inspect-run --format json` output from that run:

```json
{
  "artifact_integrity": "verified",
  "kind": "community_dfba",
  "result_digest": {
    "actual": "sha256:6c78da1d090ea4bb406d578ec95d187a9d83b2f98c10a4c961ba2fc5e7ad8bac",
    "changed_artifacts": [],
    "cross_run_comparable": false,
    "match": true,
    "missing_artifacts": [],
    "recorded": "sha256:6c78da1d090ea4bb406d578ec95d187a9d83b2f98c10a4c961ba2fc5e7ad8bac"
  },
  "run_hash": "b5d0b8bc8cc1f8d97be01eaec43842c1320fcdd430bd0858a4aa46a08d71a2b1",
  "status": "ok"
}
```

`community_dfba` intentionally remains outside `DETERMINISTIC_ARTIFACT_KINDS`: its required
summary contains raw wall-clock telemetry, so its result digest verifies the artifact set in
place but is not advertised as byte-comparable across reruns.

## Determinism measurement evidence

Basis: two actual console invocations per kind, real Gurobi, one shared generated producer/
consumer taxonomy, one shared glucose medium, and shared synthetic baseline/variant inputs. The
two runs of each kind used different output directories. The table records the complete input hash
and both complete combined result digests.

| Kind | Run hash, run 1 = run 2 | Result digest, run 1 | Result digest, run 2 | Verdict |
| --- | --- | --- | --- | --- |
| `pair` | `05342b8a19affc852edb127821696b7d7822750525721f82e80e42a380f618b3` | `sha256:65689b1a604bfa1d657ac5058f1593fd9a57292ed8c67553b7e66d07a9b0a1c9` | `sha256:65689b1a604bfa1d657ac5058f1593fd9a57292ed8c67553b7e66d07a9b0a1c9` | all bytes identical; promoted |
| `delta` | `67249eb35deffa68146316885b0b97b77acc0801cd8dc175bda229d8883534b6` | `sha256:6981144f7bc9b10a19f7c79088f3e0e486b73b7e2483788d44fa7417793455e4` | `sha256:6981144f7bc9b10a19f7c79088f3e0e486b73b7e2483788d44fa7417793455e4` | all bytes identical; promoted |
| `single` | `9332bb397923ce33284893cb0ddd655ca140269f56e2f89c6c9a84f08482bdc0` | `sha256:5ce8f07112533c25451035c2c6836045ff8fbec19253e9bd1908d518dcc77167` | `sha256:5ce8f07112533c25451035c2c6836045ff8fbec19253e9bd1908d518dcc77167` | all bytes identical; promoted |
| `minimal_medium` | `c0441ff7a7c8d391b200b9d205de4d59898c9d0d7f383d081ac4902a4f2758ea` | `sha256:a66063f06c6a3588d1d7c67a6649c949c77a3c116b2cc29180923d6cf3f17757` | `sha256:a66063f06c6a3588d1d7c67a6649c949c77a3c116b2cc29180923d6cf3f17757` | all bytes identical; promoted |

Per-artifact byte digests were also equal in both runs:

| Kind | Artifact | SHA-256 in both runs |
| --- | --- | --- |
| `pair` | `cross_feeding.csv` | `e8e1d1a5d913c1d719fcd78c5502e671405b1227f975a9329ae7df8dae0b3d4b` |
| `pair` | `matrix.parquet` | `fe3cd4468cd6a137ba6f9948f5a86604eed3c30e13e663c3e76a984c597ab6c3` |
| `pair` | `pair_metrics.csv` | `18065f35c9f47930f3d923d173d67947c3b8290d8cfa4eda5eb0bc6cec18d360` |
| `pair` | `pair_summary.json` | `26860cd80ef403a729c5f9b2a21313e259883f9d9abc1c2f7d02fbe20c8b98d2` |
| `delta` | `delta.csv` | `61adb55767ad288444545ee3578edb040ba0c7c0975be41b5434925bfb3755ae` |
| `delta` | `delta_summary.json` | `101dbbc84cdff5cd373673d86e4fad72b0514e356252fe472fd48d1065b41700` |
| `single` | `exchange_summary.csv` | `d5573adbcb388a1c0e227691856775afd91a09526c35e27b517a01a84cb7abc6` |
| `single` | `fva.csv` | `01d9943fc541e0caa5af5364e96b4151925ca89c6dbd16f6f501e276ef768344` |
| `single` | `reaction_knockouts.csv` | `8c7627203031db63be7d5dfd805024a16923759ce34bd711f60bd7583d92a867` |
| `single` | `single_fluxes.csv` | `12f3e424f1683d378a484a75ddcf4a4ad17f09d4242826af25b36433d50d57b4` |
| `single` | `single_summary.json` | `3c134c77935e6f723e757fec44e1603c08c1820704149ae90dce29d232d01f27` |
| `minimal_medium` | `minimal_medium.csv` | `23bbbe6485f3d57aab78b730014ae9a9413fe9aa3016e741c4503e6867315b84` |
| `minimal_medium` | `minimal_medium_summary.json` | `69e5aa7e915d5cdb3b69304821d8d1af4e68a3633263c506877d70430fca0174` |

No candidate kind had a differing artifact, so none of the four remained unpromoted.

An initial in-process measurement harness was launched from Python stdin. It completed the pair
measurement, then COBRA FVA correctly tried to spawn worker processes and could not re-import a
`<stdin>` main module. That harness was interrupted and its output was not used for the table.
The authoritative measurements above came from separate actual `cmig` console invocations, where
the multiprocessing entry point is valid.

## Envelope gate transcript

Before source changes:

```text
Workflow-envelope serialization gate:
  [OK ] abundance_impact, delta, dfba, gene_ko_search, host_ko_impact, host_map,
        host_microbe_bigg, host_search_bigg, minimal_medium, model_pool_search,
        model_quality, multi_target_model_pool_search, pair, publication_benchmark,
        single, strain_growth, sweep
  [OK ] float normalization probe (NaN / +/-inf / -0.0 / rounding floor)
-> envelope serialization unchanged for 17 workflow kinds
```

After declaring the additive kind and before capture:

```text
Workflow-envelope serialization gate:
  [OK ] all 17 previously captured workflow kinds
  [OK ] float normalization probe (NaN / +/-inf / -0.0 / rounding floor)
  [NEW] community_dfba — not yet covered; re-bless to protect it
        (python -m cmig.core.workflow_envelope_golden)
-> envelope serialization unchanged for 17 workflow kinds
```

Documented capture:

```text
UV_CACHE_DIR=/tmp/cmig-round9-V1-uv-cache \
  uv run --no-sync python -m cmig.core.workflow_envelope_golden
workflow-envelope golden re-blessed -> cmig/core/workflow_envelope_golden.json
  community_dfba  1c791b087543ca004db27a40f8165e0ae9834e9b0fe8f68f70c1984ff0a18077
```

After capture:

```text
Workflow-envelope serialization gate:
  [OK ] abundance_impact, community_dfba, delta, dfba, gene_ko_search,
        host_ko_impact, host_map, host_microbe_bigg, host_search_bigg,
        minimal_medium, model_pool_search, model_quality,
        multi_target_model_pool_search, pair, publication_benchmark,
        single, strain_growth, sweep
  [OK ] float normalization probe (NaN / +/-inf / -0.0 / rounding floor)
-> envelope serialization unchanged for 18 workflow kinds
```

## Verification log

Every project command used
`UV_CACHE_DIR=/tmp/cmig-round9-V1-uv-cache uv run --no-sync`.

- `ruff check .` — passed, no findings.
- `mypy cmig` — passed, `Success: no issues found in 78 source files`.
- Final owned/regression selection:
  `tests/test_round9_dfba_community_cli.py`,
  `tests/test_round9_deterministic_artifacts.py`,
  `tests/test_workflow_map_coverage.py`,
  `tests/test_round8_community_dfba.py`,
  `tests/test_round8_pair_delta_single_cli.py`,
  `tests/test_workflow_manifest.py`,
  `tests/test_workflow_envelope_golden.py`,
  `tests/test_result_digest.py`, and
  `tests/test_inspect_run_workflow_manifest.py` — 180 test nodes passed (the progress output was
  72 + 72 + 36). One expected COBRA warning remained visible for the deliberately infeasible
  one-member depletion endpoint.
- `cmig golden verify-envelope` — 18 workflow kinds plus the float-normalization probe passed.
- `cmig golden verify` — Gurobi published solve hash `29844e2910360332...` and OSQP published solve
  hash `a422eb89d019f917...` both passed under installed MICOM 0.39.0; the frozen solve hash did not
  move.
- Real Gurobi console run + `cmig inspect-run --format json` — completed and interpretable;
  `kind=community_dfba`, run hash
  `b5d0b8bc8cc1f8d97be01eaec43842c1320fcdd430bd0858a4aa46a08d71a2b1`, and result digest
  `sha256:6c78da1d090ea4bb406d578ec95d187a9d83b2f98c10a4c961ba2fc5e7ad8bac`
  verified with no changed or missing artifacts.

No GUI code was changed or exercised. QtWebEngine remains unavailable in the worker sandbox as
documented in the common brief; the coordinator's host-side/full randomized suite remains the
integration gate.

## Proposed CHANGELOG entries

- Added `cmig dfba-community`, a Gurobi-only well-mixed MICOM community dFBA command with repeated
  initial-pool, initial-member-biomass, and member-specific vmax inputs; atomic long-format
  Parquet publication; structured events; raw timing telemetry; and acceptance-gated exit codes.
- Added the additive `community_dfba` workflow-envelope kind. Initial absolute/relative biomasses,
  shared-pool concentrations, member vmax values, integration settings, and uptake-closure policy
  are hashed inputs; timing, events, warnings, acceptance, and final state remain outputs.
- Marked `pair`, `delta`, `single`, and `minimal_medium` result digests cross-run comparable after
  two real-Gurobi runs per kind produced byte-identical declared artifacts; added repeat-run
  regression coverage for each promoted kind.

## Integration notes and risks

- Documentation is coordinator-owned. README/user-guide/skill routing should add the exact
  `dfba-community` flag surface, three outputs, Gurobi/full-flux limitation, acceptance semantics,
  and exit-code contract above.
- `community_dfba` is deliberately not cross-run comparable because raw timing telemetry is a
  required summary output. Its result digest still verifies the run's artifact bytes in place.
- The four promoted round-8 kinds were measured under the brief's identical-input condition: the
  same model/medium/baseline/variant paths with different output directories. Their summaries
  retain invocation paths (`medium_source`, `model`, or baseline/variant directories), so moving
  otherwise content-identical inputs to another path can change artifact bytes. No path-normalizing
  schema change was made in this measurement track; consumers should compare repeat runs made from
  the same path-bearing inputs, and a future track can decide whether those summary fields should
  become location-independent provenance.
- Gurobi remains mandatory. The integrator needs a complete member-level pFBA flux vector, and no
  other current backend supplies one honestly.
- The taxonomy checksum is built by the existing deterministic pool checksum path, which sorts by
  member identity and fingerprints every model plus solve-relevant taxonomy metadata.
- `pyproject.toml`, `uv.lock`, docs, README, CHANGELOG, and skill files were not modified.

## Proposals deliberately not implemented

- No OSQP/approximate community-dFBA mode was presented as equivalent to full member pFBA.
- No death, washout, dilution, maintenance decay, spatial grid, diffusion, alternate uptake law,
  or new integrator was added; U6's well-mixed explicit-Euler scientific core was left intact.
- No existing workflow kind, component tuple, envelope hash, or frozen 11-component solve hash was
  redefined.
- No timing normalization was added merely to make `community_dfba` artifacts deterministic; raw
  operational telemetry is retained as required and the kind remains non-comparable.
- No existing pair/delta/single/minimal-medium output schema was rewritten to normalize invocation
  paths. The measured promotion and the relocation caveat are both recorded above.
- No GUI surface or documentation file was changed outside V1 ownership.
