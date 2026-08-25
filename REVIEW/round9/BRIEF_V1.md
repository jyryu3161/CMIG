# Round-9 Track V1 — `feat/dfba-community-cli`

Read `REVIEW/round9/COMMON_BRIEF.md` first. You are the sole owner of
`cmig/cli/main.py` and the workflow-manifest/envelope modules this round.

## Goal

1. **`cmig dfba-community`.** Round-8 U6 delivered the library
   (`cmig/core/dfba_community.py::run_community_dfba`) and wrote the exact CLI +
   manifest proposal in `REVIEW/round8/report_U6.md` §Integration notes —
   implement that proposal faithfully:
   - the argument surface as proposed (`--taxonomy`, `--t-end`, `--dt`,
     `--min-dt`, `--km`, `--growth-floor`, `--tradeoff-fraction`, repeated
     `--initial EX_MET_m=VALUE`, repeated `--initial-biomass MEMBER=VALUE`,
     repeated `--member-vmax MEMBER:EX_MET_m=VALUE`,
     `--close-untracked-uptake`, `--allow-failed-run`, `--out`; `--solver`
     gurobi-only until another backend supplies full member fluxes);
   - outputs `community_dfba_summary.json`,
     `community_dfba_timecourse.parquet`, `community_dfba_events.json`, with
     raw timing telemetry in the summary;
   - exit 0 only when `acceptance.interpretable` is true; 3 for a completed but
     non-interpretable run or explicit solver failure; 2 for input errors;
     `--allow-failed-run` may soften 3→0 but never alters the recorded verdict;
   - a new **additive** workflow kind `community_dfba` with the proposed
     `community_dfba_spec` component (initial biomasses/concentrations and
     member vmax are hashed inputs; timing/events/acceptance are outputs and
     must NOT enter the hash); envelope gate 17 OK + 1 NEW before the
     documented golden capture, 18 OK after;
   - workflow-map entry (the coverage test will force it).
2. **`cross_run_comparable` measurement.** `workflow_manifest.py` marks kinds in
   `DETERMINISTIC_ARTIFACT_KINDS` as cross-run comparable; the four round-8
   kinds (`pair`, `delta`, `single`, `minimal_medium`) were left out pending
   measurement. Measure: run each kind twice on identical inputs (real Gurobi,
   the synthetic pair fixtures round-8 used) and compare artifact bytes/digests.
   Add to the deterministic set ONLY the kinds that measured byte-identical,
   with a regression test per promoted kind; record the evidence (both digests)
   in your report. A kind that is not byte-stable stays out, with the differing
   artifact named.

## Ownership

- `cmig/cli/main.py`; `cmig/core/workflow_manifest.py`;
  `cmig/core/workflow_envelope_golden.py` + `.json` (documented procedure)
- `cmig/core/dfba_community.py` and `cmig/io/dfba_output.py` (glue only —
  do not redesign U6's integrator)
- tests: `tests/test_round9_dfba_community_cli.py` (new),
  `tests/test_workflow_map_coverage.py`, `tests/test_round8_community_dfba.py`
  (additive only), determinism regression tests

## Verification to include in your report

- A real `cmig dfba-community` Gurobi run reproducing U6's cross-feeding
  scenario through the CLI, with `inspect-run` output (kind, run_hash,
  result_digest verified).
- Envelope gate transcript before/during/after the additive capture.
- The determinism measurement table for the four kinds.
