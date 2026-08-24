# Round-8 Track U4 — `feat/gut-media-generator`

Read `REVIEW/round8/COMMON_BRIEF.md` first. Fully independent data/tooling
track: finish the gut-overlay work that round-7 T1 correctly declined under
its "data tables only" ownership.

## Background

The seven `medium_presets/gut_overlay_*.csv` files carry pool-specific
background-closure rows (`uptake_limit = 0` for every exchange the bundled
5-model pool would otherwise leave open). They exist because `--medium` is a
merge overlay. Since round 7, `--exact-medium` makes the file the whole
environment — exact-mode users do not need the closure rows, and the rows tie
the overlays to one specific model pool. T1's analysis
(`REVIEW/round7/report_T1.md` §Gut-overlay status, and
`medium_presets/PROVENANCE_gut_media.md` §9) found the rows are emitted by
generator logic (`scripts/build_gut_media.py::_append_environment`), not from a
data table, and the preset tests require them to keep the default merge path
safe.

## Goal

1. **Restructure the generator** (`scripts/build_gut_media.py`) so the closure
   block becomes an explicit, marked, separable section of each overlay —
   e.g. a `row_role` (or equivalent) column distinguishing `nutrient` rows from
   `pool_closure` rows, or split companion files — such that:
   - the default merge path keeps EXACTLY today's semantics (every closure row
     still applies; the 81% oxygen-overestimate protection must not regress);
   - an exact-mode user (or another model pool's user) can mechanically
     identify and strip the pool-specific closure block, and the provenance
     document explains how;
   - `scripts/build_gut_media.py --check` remains a working staleness gate for
     the new structure, and `--report` still works.
   Check first how `cmig/core/medium_spec.py` parses overlay CSVs: if an added
   column would break the loader, prefer the companion-file or marker-comment
   design instead — the loader is NOT yours to change (record any needed loader
   change as an integration note for the coordinator/U1).
2. **Regenerate the seven overlays deterministically** with the new structure;
   values must be identical row-for-row for the merge path (show a
   before/after diff summary proving only structure/annotation changed, not a
   single bound value).
3. **Update the provenance document** (`medium_presets/PROVENANCE_gut_media.md`)
   §9 and wherever the closure block is described: what the closure block is,
   which pool it is specific to, how exact-mode users should treat it.
4. **Tests**: `tests/test_medium_presets_gut.py` must keep every existing
   scientific assertion (18 tests) and gain assertions that (a) the closure
   block is completely identified by the new marker, (b) stripping it yields a
   pure literature-nutrient overlay, (c) the builder `--check` gate catches a
   hand-edited closure row.

## Ownership

- `scripts/build_gut_media.py`
- `medium_presets/**` (CSVs, provenance docs, sources README)
- tests: `tests/test_medium_presets_gut.py`
- Do NOT touch: `cmig/**` (the medium loader belongs to U1's files —
  integration note only), `README.md`/`CHANGELOG.md` (coordinator).

## Verification to include in your report

- `scripts/build_gut_media.py --check` green on the regenerated files.
- The row-for-row value-identity proof for the merge path.
- A demonstration (commands + output) of mechanically stripping the closure
  block and what the resulting file contains.
- `uv run --no-sync python -m pytest tests/test_medium_presets_gut.py` green.
