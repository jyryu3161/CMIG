# Round-8 U6 report — well-mixed MICOM community dFBA

## What changed and why

### Community integrator

Added `cmig/core/dfba_community.py` and re-exported its public surface from
`cmig.core.dfba`:

- `CommunityDfbaConfig`
- `CommunityDfbaTimepoint`
- `CommunityDfbaEvent`
- `CommunityDfbaAcceptance`
- `CommunityDfbaResult`
- `run_community_dfba`

`run_community_dfba` builds one MICOM community once. At every step it:

1. derives MICOM abundances from the current per-member biomass concentrations;
2. rebinds every member-to-pool tracked uptake bound with
   `vmax * S / (Km + S)`;
3. rebinds the tracked environmental reaction to the abundance-weighted aggregate
   capacity;
4. solves through the existing public `MicomEngine.cooperative_tradeoff` surface;
5. integrates each member as `dX_i/dt = mu_i * X_i` and the shared pool as
   `dS_m/dt = sum_i(v_i,m * X_i)`.

This is the exact single-model Euler balance when there is one member. The state trajectory is
deterministic for fixed models/configuration/solver. Build and solve wall-clock measurements are
returned separately and do not influence the scientific state.

Adaptive step halving preserves concentration non-negativity. If `min_dt` would still consume
more mass than is present, growth and all tracked exchange fluxes are scaled by the same limiting
fraction, matching the existing single-model honesty convention. Adaptive steps, emergency
clamps, tolerance-scale clamps, untracked uptake, stalling, and solver failures are structured
events rather than silent changes.

The result has a structured `acceptance.interpretable` verdict. It is false for solver failures,
initial-condition stalls, untracked environmental uptake, non-full member flux reports, or a
negative tracked concentration. Untracked uptake is retained as an exchange-to-peak-rate mapping
and also produces a detailed warning. `close_untracked_uptake=True` closes all environmental
imports outside the tracked set before integration.

Death and washout are deliberately not modeled. This limitation is present on every result;
negative member growth is rejected instead of being silently interpreted as death.

The prototype requires Gurobi because concentration integration needs a complete member-level
pFBA flux vector. OSQP/QP-only approximate output is rejected before building.

### Community timecourse and atomic publication

Extended `cmig/io/dfba_output.py` with:

- `COMMUNITY_DFBA_TIMECOURSE_KIND = "community_dfba_timecourse"`;
- a distinct community schema containing `kind`, `entity_type`, and nullable `member` columns;
- long-format member biomass/growth rows and shared-pool concentration rows;
- `write_community_timecourse`, which uses `cmig.io.atomic.atomic_write_parquet`.

A reader cannot mistake this table for the four-column single-model timecourse. The existing
single-model `write_timecourse` was also switched from direct `pq.write_table` publication to the
same atomic primitive; its schema and bytes remain otherwise unchanged.

### Scientific tests

Added `tests/test_round8_community_dfba.py` with real MICOM/Gurobi tests for:

- a two-member synthetic producer/consumer cross-feed;
- a one-member `micom.data.test_taxonomy()` reduction against `simulate_dfba` through glucose
  depletion;
- a genuinely infeasible internal network that stops with an explicit structured solver
  diagnostic;
- untracked nutrient uptake and failed interpretability;
- emergency non-negativity clamp event recording;
- distinct community timecourse schema and atomic Parquet publication.

## Quantitative validation

### Cross-feeding dependence

Basis: synthetic producer biomass consumes one glucose unit and necessarily secretes two
`xfeed` units; the consumer has no biomass substrate except `xfeed`. Both start at `0.01 gDW/L`,
the shared pool starts at `glucose=2.0`, `xfeed=0.0`, `dt=0.1 h`, `Km=0.01`, Gurobi, six steps.
Untracked imports were closed.

At `t = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6] h`:

- consumer biomass with producer:
  `[0.010000000000, 0.010000000000, 0.016655574043, 0.030665134949,
  0.058937096597, 0.115588450649, 0.228938018207] gDW/L`;
- shared `xfeed` concentration:
  `[0.000000000000, 0.019900497512, 0.052945923457, 0.118135872739,
  0.247846609755, 0.506277295102, 1.021085487057] mmol/L`.

The pool rises during the first step while consumer biomass remains at its initial condition;
consumer growth begins only after producer secretion is available. The matched consumer-only
control stalled at `t=0` and remained exactly `0.01 gDW/L`. The assertion tolerance for control
growth is `1e-10 gDW/L`, about two orders above the configured Gurobi feasibility tolerance after
scaling by the `0.01 gDW/L` initial biomass; the observed producer-dependent effect is
`0.218938 gDW/L`, so the qualitative signature has very large margin.

### One-member agreement and depletion

Basis: the first MICOM test-taxonomy E. coli model versus the same bundled
`e_coli_core.xml.gz` through the existing single-model integrator; Gurobi, `dt=0.1 h`,
`Km=0.01`, `X0=0.01 gDW/L`, glucose `10 mmol/L`. Oxygen, ammonium, phosphate, water, proton, and
CO2 pools were also tracked at `1000 mmol/L`, and every other environmental uptake was closed, so
this comparison has no untracked nutrient support.

Both paths produced the same 59 timepoints and stopped at `t=5.3601562499999975 h` after glucose
depletion (the single path reported `infeasible`; the engine wrapper reported the MICOM primal
readout as structured `solver_failed`). Measured agreement over all paired timepoints:

- maximum absolute biomass difference: `2.1760371282653068e-14 gDW/L`;
- maximum absolute glucose difference: `1.8590684547348246e-13 mmol/L`;
- final biomass: community `0.8836260291224489`, single `0.8836260291224419 gDW/L`;
- final glucose: community `0.0003428963424561034`, single
  `0.0003428963424819626 mmol/L`;
- maximum time difference: zero at the test's `1e-12 h` check.

Tests allow `1e-10` absolute error for biomass and glucose. This is roughly 500 times the largest
measured cross-path difference, while remaining far below a biologically meaningful change.
Adaptive-step and terminal solver-failure events are both asserted.

### Build-once versus naive rebuild cost

Basis: warmed one-member MICOM test-taxonomy/Gurobi process. The build-once run integrated ten
`0.1 h` steps. The naive comparison independently rebuilt the identical one-member community and
solved one `0.1 h` step ten times. Values below are one local wall-clock sample and are operational,
not deterministic scientific results:

- build-once community construction: `0.095225 s`;
- build-once mean solve: `0.007325 s/step`;
- build-once amortized `(one build + ten solves) / ten`: `0.016847 s/step`;
- naive mean rebuild: `0.100543 s/step`;
- naive mean solve after each rebuild: `0.011993 s/step`;
- naive mean `(rebuild + solve)`: `0.112535 s/step`;
- observed naive/build-once amortized ratio: `6.68x`.

`CommunityDfbaResult` retains the raw build duration and all per-step solve durations so callers
can measure their own models and hardware without treating this sample as a universal benchmark.

## Verification log

The worktree-local `uv run --no-sync` initially failed before command execution because uv tried
to open sandbox-inaccessible `/Users/jaeyongryu/.cache/uv/sdists-v9/.git`. The common-brief shared
venv fallback alone hit the same uv cache path. All project commands therefore used the required
`uv run --no-sync` form with:

```text
UV_CACHE_DIR=/tmp/cmig-u6-uv-cache
UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv
PYTHONPATH=.
```

Final gates:

- `uv run --no-sync ruff check .` — passed, no findings.
- `uv run --no-sync mypy cmig` — passed, `Success: no issues found in 78 source files`.
- `uv run --no-sync pytest -q tests/test_round8_community_dfba.py tests/test_dfba.py
  tests/test_community_fva.py tests/test_round7_atomic_io.py` — 37 passed. The three expected
  COBRA infeasibility warnings and one OSQP pending-deprecation warning remained visible.
- `uv run --no-sync cmig golden verify-envelope` — all 13 existing workflow kinds plus the float
  normalization probe passed; envelope serialization unchanged.

An additional full `pytest -q` attempt did not report a test assertion failure but the process
exited with signal code 133 during the GUI portion. `pytest -vv` localized the crash to
`tests/test_gui_round5_p2.py::test_search_results_are_cleared_when_answer_inputs_change`; that
test also exits 133 with no output when run alone in this worktree environment. It does not import
or exercise the U6 files. This is recorded as an environment/integration issue rather than claimed
as a green full-suite run.

## Proposed CHANGELOG entries

- Added a build-once, well-mixed MICOM community dFBA library prototype with per-member biomass,
  shared extracellular pools, member-specific Michaelis-Menten uptake bounds, adaptive
  non-negative integration, structured event/timing telemetry, and explicit interpretability
  gating for solver degradation and untracked nutrients.
- Added a distinct `community_dfba_timecourse` long-format schema and atomic Parquet publisher for
  per-member biomass/growth and shared-pool concentrations.
- Community dFBA now explicitly records that death and washout are not modeled and currently
  requires Gurobi full member-level pFBA fluxes.
- Switched the existing single-model dFBA Parquet writer to atomic file replacement without
  changing its schema.

## Integration notes and risks

### Exact proposed CLI (not implemented; `cmig/cli/main.py` is U1-owned)

Proposed command surface:

```text
cmig dfba-community \
  --taxonomy TAXONOMY.csv \
  --solver gurobi \
  --t-end HOURS \
  [--dt 0.1] [--min-dt 0.0001] [--km 0.01] \
  [--growth-floor 0.000001] [--tradeoff-fraction 1.0] \
  --initial EX_MET_m=MMOL_PER_L [--initial EX_OTHER_m=MMOL_PER_L ...] \
  --initial-biomass MEMBER=GDW_PER_L \
      [--initial-biomass OTHER_MEMBER=GDW_PER_L ...] \
  [--member-vmax MEMBER:EX_MET_m=MMOL_PER_GDW_PER_H ...] \
  [--close-untracked-uptake] [--allow-failed-run] \
  --out OUT_DIR
```

The wrapper should parse repeated mappings without changing their identifiers, call only
`run_community_dfba`, write `community_dfba_summary.json`,
`community_dfba_timecourse.parquet`, and `community_dfba_events.json`, and expose raw timing in the
summary. Default exit should be 0 only when `result.acceptance.interpretable` is true, 3 for a
completed/stalled but non-interpretable run or an explicit solver failure, and 2 for input errors.
`--allow-failed-run` may override exit 3 to 0 but must never alter the recorded acceptance verdict.
The prototype's `--solver` choice should be Gurobi only until another backend supplies a complete,
honestly labeled member flux vector.

### Proposed workflow manifest (not implemented; U1-owned)

Add a new additive workflow kind `community_dfba`; do not overload the existing single-model
`dfba` kind or reserialize existing envelopes. Its canonical envelope should include the standard
version/dependency/solver/model-medium components plus:

```json
{
  "community_dfba_spec": {
    "integrator": "explicit_euler_adaptive_nonnegative",
    "t_end": "<float>",
    "dt": "<float>",
    "min_dt": "<float>",
    "km": "<float>",
    "growth_floor": "<float>",
    "tradeoff_fraction": "<float>",
    "initial_biomasses": {"<member>": "<float>"},
    "initial_concentrations": {"<EX_*_m>": "<float>"},
    "member_vmax": {"<member>": {"<EX_*_m>": "<float>"}},
    "close_untracked_uptake": "<bool>",
    "death_washout": "not_modeled"
  }
}
```

The model checksum must cover every taxonomy model and member identity in deterministic member
order. Initial relative abundances derived from biomass should be recorded, but initial absolute
biomasses must also remain a hash component because they change the dynamics. Timing telemetry,
events, warnings, and acceptance are outputs and must not enter the input hash.

### Other integration risks

- `MicomEngine` intentionally converts MICOM optimization/readout exceptions to
  `status="solver_failed"`; it does not expose a trustworthy underlying infeasible status. The
  known-infeasible test therefore pins explicit stop/diagnostic behavior without relabeling the
  failure. A future engine API could expose a solver-status cause separately, but U6 did not
  change the 22-importer engine surface.
- Default `member_vmax` uses the initial environmental import limit when available and otherwise
  the connected MICOM member-exchange limit. Cross-feeding experiments should set explicit
  per-member caps for metabolites absent from the starting medium, as the synthetic test does.
- Wall-clock timing varies with model size, solver warm state, license/server state, and hardware;
  it is deliberately excluded from acceptance and trajectory calculations.
- The isolated Qt signal-133 failure described in the verification log remains for coordinator
  triage and is outside U6 ownership.

## Proposals deliberately not implemented

- No CLI, CLI parser, GUI, workflow-manifest kind, workflow-envelope golden, README, or CHANGELOG
  edit was made because those files are owned by other round-8 tracks/the coordinator.
- No spatial grid, diffusion, region mask, death, maintenance-decay, dilution, or washout model was
  added. The feature is strictly well mixed.
- No alternate uptake law (linear, pseudo-Monod), implicit integrator, or multi-rate solver was
  added.
- No OSQP or approximate-flux community integration was presented as equivalent to full pFBA.
- No dependency or lockfile changes were made.
- No solve golden was re-blessed and no existing workflow hash/envelope was changed.
