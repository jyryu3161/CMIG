# Round-8 U4 report — gut-overlay closure marker

## What changed and why

`cmig/core/medium_spec.py::load_medium` was inspected before choosing the representation. Its CSV
loader requires the `exchange_id` and `uptake_limit` fields and reads those fields by name; it ignores
additional columns. Therefore the loader-compatible annotation-column design was used instead of
duplicating the presets into companion files.

- `scripts/build_gut_media.py` now emits
  `exchange_id,uptake_limit,row_role` for every gut overlay.
  - `row_role=nutrient` means a scientific medium component rather than pool bookkeeping. It covers
    the dietary/source rows, sourced inorganic rows, the explicit anaerobic O2 term, and the already
    disclosed nickel assumption.
  - `row_role=pool_closure` is derived exclusively from the existing `background_closure` origin and
    identifies the zero rows generated from the bundled five-model pool's default media.
- `medium_presets/provenance_rows.csv` repeats `row_role` next to the finer-grained `origin`, making
  the role/origin invariant independently auditable.
- All seven `medium_presets/gut_overlay_*.csv` files were regenerated deterministically. Their
  exchange order and all 717 `(exchange_id, uptake_limit)` string pairs are identical to the
  pre-change files; only the new role annotation was added.
- `medium_presets/PROVENANCE_gut_media.md` now documents the role schema, the pool-specific nature
  and exact counts of the closure rows, a mechanical stripping command, and the safety rule: use a
  stripped file with `--exact-medium`, never with the default merge path.
- `medium_presets/README.md` now distinguishes the two required medium fields from the gut-overlay
  `row_role` extension and points exact-mode/different-pool users to the stripping procedure.
- `tests/test_medium_presets_gut.py` retains all 18 existing scientific tests and adds three:
  complete marker identification, nutrient-only stripping, and a hand-edited closure-row staleness
  failure. The existing oxygen/background tests still protect the measured 81% oxygen-overestimate
  regression.

Role counts in the regenerated files:

| Overlay family | Total rows | `nutrient` | `pool_closure` |
|---|---:|---:|---:|
| AGORA Western | 133 | 124 | 9 |
| AGORA high fibre | 133 | 124 | 9 |
| VMH high-fat/low-carb, each scale | 80 | 68 | 12 |
| VMH high-fibre, each scale | 80 | 68 | 12 |
| MICOM Western | 131 | 118 | 13 |

## Verification log

The sandbox denied access to uv's configured global cache (`~/.cache/uv/sdists-v9/.git`), so all uv
commands used the writable isolated cache `UV_CACHE_DIR=/tmp/cmig-u4-uv-cache`. They still used the
required pre-synced environment via `uv run --no-sync`; no sync or dependency operation was run.

### Deterministic builder and report

```text
$ UV_CACHE_DIR=/tmp/cmig-u4-uv-cache uv run --no-sync python -m scripts.build_gut_media --check --report
exit 0
gut_overlay_agora_western.csv                    133  45  59 120 124  94
gut_overlay_agora_high_fiber.csv                 133  45  59 120 124  94
gut_overlay_vmh_high_fat_low_carb.csv             80  40  45  76  75  54
gut_overlay_vmh_high_fat_low_carb_x100.csv        80  40  45  76  75  54
gut_overlay_vmh_high_fiber.csv                    80  40  45  76  75  54
gut_overlay_vmh_high_fiber_x100.csv               80  40  45  76  75  54
gut_overlay_micom_western.csv                    131  45  60 118 122  97
fibre coverage: 1/24 have an exchange in any bundled model
```

This single invocation proves both that `--check` is green and that `--report` still runs and emits
the established coverage data.

### Row-for-row merge-value identity proof

Before regeneration, the seven original CSVs were copied to
`/tmp/cmig-u4-before.7BbVwk`. A Python `csv.DictReader` comparison checked the ordered sequence of
the original and regenerated `(exchange_id, uptake_limit)` strings, not rounded floats:

```text
gut_overlay_agora_high_fiber.csv: rows=133, ordered_value_rows_identical=True, added_columns=['row_role']
gut_overlay_agora_western.csv: rows=133, ordered_value_rows_identical=True, added_columns=['row_role']
gut_overlay_micom_western.csv: rows=131, ordered_value_rows_identical=True, added_columns=['row_role']
gut_overlay_vmh_high_fat_low_carb.csv: rows=80, ordered_value_rows_identical=True, added_columns=['row_role']
gut_overlay_vmh_high_fat_low_carb_x100.csv: rows=80, ordered_value_rows_identical=True, added_columns=['row_role']
gut_overlay_vmh_high_fiber.csv: rows=80, ordered_value_rows_identical=True, added_columns=['row_role']
gut_overlay_vmh_high_fiber_x100.csv: rows=80, ordered_value_rows_identical=True, added_columns=['row_role']
ALL: files=7, rows=717, ordered_value_rows_identical=True
```

Loading each before/after file through `load_medium` and hashing it through `medium_checksum` also
reported `medium_checksum_unchanged=True` for all seven files. Thus the full shipped files retain
exactly the old default-merge mapping and do not move the medium component of `run_hash`.

### Mechanical closure stripping demonstration

The documented command was executed verbatim:

```bash
awk -F, 'BEGIN { OFS="," } NR == 1 { print $1, $2; next } $3 == "nutrient" { print $1, $2 }' \
  medium_presets/gut_overlay_agora_western.csv > /tmp/cmig-u4-gut-exact.csv
```

The output was then parsed and compared to every source row marked `nutrient`:

```text
output=/tmp/cmig-u4-gut-exact.csv
header=['exchange_id', 'uptake_limit']
source_rows=133 stripped_rows=124 removed_rows=9
nutrient_rows_identical=True
pool_closure_rows_remaining=0
first_rows=[('EX_26dap__M_m', '0.1'), ('EX_2obut_m', '0.1'), ('EX_4abz_m', '0.1')]
```

### Tests and repository gates

```text
$ UV_CACHE_DIR=/tmp/cmig-u4-uv-cache uv run --no-sync python -m pytest tests/test_medium_presets_gut.py
.....................                                                    [100%]
21 passed in 14.87s

$ UV_CACHE_DIR=/tmp/cmig-u4-uv-cache uv run --no-sync ruff check .
All checks passed!

$ UV_CACHE_DIR=/tmp/cmig-u4-uv-cache uv run --no-sync mypy cmig
Success: no issues found in 77 source files

$ UV_CACHE_DIR=/tmp/cmig-u4-uv-cache uv run --no-sync cmig golden verify-envelope
[OK] all 13 workflow kinds
[OK] float normalization probe
envelope serialization unchanged for 13 workflow kinds
```

## Proposed CHANGELOG entry

- Mark every generated gut-overlay row with `row_role=nutrient` or
  `row_role=pool_closure`, making the bundled-model closure block mechanically removable for
  `--exact-medium` and other-pool workflows while preserving all 717 exchange bounds and the safe
  default merge behavior. Extend row provenance, documentation, and staleness/stripping tests for
  the new schema.

No `CHANGELOG.md` edit was made because it is coordinator-owned.

## Integration notes / risks

- The repository-root `README.md` still describes medium CSVs as
  `exchange_id,uptake_limit`. That remains accurate for required fields, but the coordinator may
  want to mention that the shipped gut overlays add the optional `row_role` annotation. I did not
  edit it because it is coordinator-owned.
- No `cmig/**` change is required: `load_medium` already ignores additional CSV fields, and the
  targeted suite proves every annotated overlay still loads and validates.
- The full shipped overlay must remain the default for merge mode. Stripping `pool_closure` and then
  merging would reintroduce permissive defaults, including the historical oxygen leak. A different
  pool should either use the stripped nutrient file with `--exact-medium` or build its own closure
  rows.
- The role name `nutrient` deliberately means “scientific medium component, not pool bookkeeping.”
  It includes the explicit O2 boundary and the disclosed nickel assumption; consumers needing finer
  categories should use `origin` in `provenance_rows.csv`.
- No dependencies, workflow schemas, solve goldens, or files outside U4 ownership were changed.

## Proposals deliberately not implemented

- No loader enforcement or `--strip-pool-closure` CLI option was added because `cmig/**` and the CLI
  are outside U4 ownership; the existing optional-column behavior is sufficient for compatibility.
- No companion exact-mode files were added. They would duplicate 638 scientific rows, create another
  staleness surface, and are unnecessary now that the canonical files carry a filterable marker.
- The closure rows were not removed from the canonical overlays and merge semantics were not
  changed. Both would regress the default-path safety requirement.
- The different-pool closure generator was not generalized: building a closure for a different pool
  requires that pool's models and belongs in a separately scoped tool/loader change.
