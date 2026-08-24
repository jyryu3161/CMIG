# Round-7 Track T1 — `feat/exact-medium`

Read `REVIEW/round7/COMMON_BRIEF.md` first. You are the ONLY track allowed to touch
`cmig/cli/main.py` and the manifest schema this round.

## Goal

Implement the already-designed-but-unbuilt exact-medium mode:

1. **`--exact-medium` CLI flag** on every subcommand that accepts `--medium`
   (solve, search, strain-growth, abundance-impact, gene-ko-search,
   host-microbe-bigg, host-ko-impact, host-search-bigg, sweep — enumerate from
   the parser, do not trust this list blindly; there is a shared helper
   `_add_allow_unknown_medium` you can mirror). The flag routes to the
   already-existing `apply_medium_translated(..., exact=True)` in
   `cmig/core/medium_spec.py`. Design rationale and intended semantics are
   written down in `medium_presets/PROVENANCE_gut_media.md` §9 and
   `CHANGELOG.md` (the "[Unreleased]" note that says "recorded … not implemented").
2. **`medium_application_mode` manifest field** recorded alongside
   `medium_checksum` in the workflow manifest, sourced from
   `MediumTranslation.application_mode` / `as_provenance()`
   (`cmig/core/medium_spec.py`). This is a manifest schema evolution:
   - follow the documented schema-version procedure in
     `cmig/core/workflow_manifest.py` (bump the schema version, keep old-run
     readability in `inspect-run`),
   - re-bless the envelope goldens the documented way, and record in your report
     exactly which golden files changed and why this is the single intended
     run_hash drift of round 7.
3. **`cmig workflows` map completeness**: add the missing user-facing commands
   (host-map, dfba-sensitivity, model-quality, publication-benchmark,
   render-figure, stats-sweep, stats-demo, namespace-suggest, golden) to the
   workflow map, and add a test asserting every non-fixture subcommand in
   `build_parser()` is represented in the map (so it cannot rot again).
4. **Gut overlay cleanup**: with exact mode available, the 7
   `medium_presets/gut_overlay_*.csv` files can drop their pool-specific closure
   rows per PROVENANCE §9. Only do this if `scripts/build_gut_media.py --check`
   and the medium preset tests can be kept green WITHOUT modifying
   `scripts/build_gut_media.py` beyond its data tables — otherwise leave the
   CSVs alone and record the situation in your report.

## Ownership

- `cmig/cli/main.py`
- `cmig/core/medium_spec.py`
- `cmig/core/workflow_manifest.py` (schema procedure only)
- `medium_presets/gut_overlay_*.csv`, `medium_presets/PROVENANCE_gut_media.md`
  (§9 status update only), `scripts/build_gut_media.py` (data tables only, if
  needed for item 4)
- `fixtures/**/expected/**` envelope goldens (re-bless only, via the documented
  procedure)
- tests: `tests/test_cli_solve_medium.py`, `tests/test_medium_presets_gut.py`,
  new test files you create (name them `tests/test_round7_exact_medium*.py`,
  `tests/test_workflow_map_coverage.py`)

## Verification to include in your report

- A real CLI run showing a gut overlay applied with `--exact-medium` and the
  resulting manifest carrying `medium_application_mode` (`cmig inspect-run`).
- `uv run cmig golden verify-envelope` output BEFORE and AFTER the re-bless.
- Confirmation that runs WITHOUT the new flag produce byte-identical manifests
  to pre-change behavior except for the schema-version/field addition — i.e. the
  default path's semantics did not move.
