# Round-8 Track U1 — `feat/pair-delta-single-cli`

Read `REVIEW/round8/COMMON_BRIEF.md` first. You are the ONLY track allowed to
touch `cmig/cli/main.py`, `cmig/core/workflow_manifest.py`, `cmig/core/golden.py`,
and `cmig/core/workflow_envelope_golden.json` this round.

## Background

Spec §10's three baseline analyses are fully implemented as libraries but
unreachable: `cmig/core/pair.py` + `cmig/core/matrix.py` (AN-PAIR — consumers
are tests only), `cmig/core/delta.py` (AN-DELTA — GUI Compare tab only, no CLI),
`cmig/core/single_model.py` + `cmig/core/medium.py` (AN-SINGLE and
minimal-medium — library only). Round-5's final report explicitly deferred two
real defects here because they are unreachable from the CLI: the
`growth_feasible` and `analyze_pair` **medium mismatch**, saying they "must land
together as one API redesign". This track is that redesign plus the CLI surface.

## Goal

1. **Fix the medium mismatch as one coherent API.** Find the round-5 findings
   (`REVIEW/FINAL_REPORT_ROUND5_2026-07-26.md`, `REVIEW/round5/`) describing how
   `growth_feasible` and `analyze_pair` apply media inconsistently with the
   product path. Redesign so every entry point applies media through the same
   `apply_medium_translated` pipeline the product commands use (including
   `--exact-medium` semantics and the namespace gate where model ids are
   involved). Document the before/after contract in your report.
2. **New subcommands**, following the existing command conventions exactly
   (`--out` run directory, workflow manifest, `inspect-run` compatibility,
   exit 0/2/3, `--allow-failed-run` where the convention admits it,
   `--medium`/`--exact-medium`/`--allow-unknown-medium` where a medium applies):
   - `cmig pair` — mono vs co-culture for a 2-member set: growth deltas,
     interaction typing, cross-feeding summary; `--per-medium` matrix mode
     driving `cmig/core/matrix.py` across a list of media.
   - `cmig delta` — CLI counterpart of the GUI Compare tab over two completed
     run directories (baseline vs variant), reusing `cmig/core/delta.py`;
     README claims "every working GUI analysis surface has a matching CLI
     workflow" and this is the missing one.
   - `cmig single` — single-model FBA/pFBA/FVA, reaction KO, exchange summary
     via `cmig/core/single_model.py`/`cmig/core/fva.py` (read-only use of
     `fva.py`; do not change its API).
   - `cmig minimal-medium` — cardinality-minimal medium + limiting nutrients
     via `cmig/core/medium.py`.
3. **Workflow manifests for the new commands.** Add the new workflow kinds via
   the documented additive procedure in `cmig/core/workflow_manifest.py`
   (component tuples, canonical payloads) and extend
   `cmig/core/workflow_envelope_golden.json` with the documented generator
   command. Existing kinds' serialization must remain byte-identical —
   `golden verify-envelope` must stay green for all previous kinds before AND
   after; only the additive new kinds appear. No schema-version bump unless an
   existing kind's serialization must change (avoid that).
4. **Workflow map**: register every new user-facing command —
   `tests/test_workflow_map_coverage.py` will force this. Advertise the medium
   flags in the map entries as round 7 did for `--exact-medium`.

## Ownership

- `cmig/cli/main.py`
- `cmig/core/pair.py`, `delta.py`, `single_model.py`, `medium.py`, `matrix.py`
- `cmig/core/workflow_manifest.py`, `cmig/core/golden.py`,
  `cmig/core/workflow_envelope_golden.json` (procedures only)
- `cmig/synthetic_pair.py`, `fixtures/pair_acetate_butyrate/**`
- tests: `tests/test_pair.py`, `tests/test_workflow_map_coverage.py`, new
  `tests/test_round8_pair_delta_single*.py`
- Do NOT touch `cmig/core/fva.py` (read-only), `cmig/core/tidy.py`/
  `interactions.py` (U2), `cmig/core/sweep.py` (U3), `cmig/core/dfba.py` (U6),
  `cmig/gui/**` (U5)

## Verification to include in your report

- Real CLI demonstrations of each new command on the bundled models/fixtures
  (Gurobi is available), with `inspect-run` output showing kind, run_hash, and
  `result_digest` integrity.
- Envelope gate output before adding kinds, after adding kinds pre-golden-update
  (expected: only the NEW kinds unknown/absent, old kinds OK), and after the
  golden update (all OK).
- A demonstration that the redesigned medium path gives a different (and now
  correct) answer than the old mismatch would have, with numbers and basis.
