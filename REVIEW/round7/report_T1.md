# Round-7 T1 report — `feat/exact-medium`

Date: 2026-08-24

## What changed and why

### Exact-medium CLI mode

- Added `--exact-medium` to every top-level parser that accepts a microbial/community medium:
  `solve`, `search`, `strain-growth`, `abundance-impact`, `gene-ko-search`,
  `host-microbe-bigg`, `host-ko-impact`, `host-search-bigg`, and `sweep`.
- The flag scopes the existing `apply_medium_translated(..., exact=True)` behavior to one CLI
  invocation. Existing service/core callers need no out-of-ownership signature changes, and the
  scope is reset after each command. Gene-KO thread-pool tasks receive independent copies of that
  context so `--jobs > 1` cannot compare an exact baseline against merge-mode knockout arms.
- The default remains `merge_onto_model_default`; no-flag scientific behavior is unchanged.

### Workflow manifest schema evolution

- Bumped `WORKFLOW_MANIFEST_SCHEMA_VERSION` from `1.1` to `1.2`.
- Added `medium_application_mode` alongside `checksum` in the hashed workflow `medium` component.
  Its values use the same `MediumTranslation.application_mode` vocabulary exposed by
  `MediumTranslation.as_provenance()`:
  - `merge_onto_model_default`
  - `exact_boundary_isolation`
  - `null` when no custom medium is applied
- `inspect-run` remains tolerant of schema-1.1 workflow manifests whose medium component lacks the
  new field; this is covered by a regression test.

This is the **single intended round-7 run-hash drift**. One generated golden file changed:

- `cmig/core/workflow_envelope_golden.json`

It was rewritten only by the documented command
`python -m cmig.core.workflow_envelope_golden`. All 13 workflow-kind canonical payloads and the
float-normalization probe gained the one new medium subfield, so their stored hashes moved. No
solve golden under `fixtures/**/expected/**`, no frozen 11-component solve-hash serializer, and no
solver result artifact changed.

### `cmig workflows` completeness

- Added the nine brief-required user-facing commands: `host-map`, `dfba-sensitivity`,
  `model-quality`, `publication-benchmark`, `render-figure`, `stats-sweep`, `stats-demo`,
  `namespace-suggest`, and `golden`.
- Also mapped the existing `host-generic` and `host-benchmark` analysis commands so the coverage
  invariant is literal: every non-fixture top-level analysis command is represented. Bootstrap/UI
  commands (`version`, `solvers`, `workflows`, `gui`) are deliberately not analysis-map entries.
- Added a parser-derived coverage test and advertised `--exact-medium` in every affected map entry.

### Gut-overlay status

- Updated `medium_presets/PROVENANCE_gut_media.md` §9 with the implemented exact-mode and schema
  status.
- Kept all seven `medium_presets/gut_overlay_*.csv` files byte-unchanged. The builder emits closure
  rows in `_append_environment`, not from a data table, and the preset tests require those rows to
  protect default merge semantics. Removing only the CSV rows makes builder `--check` fail;
  suppressing them requires a generator-logic change beyond T1's permitted “data tables only” edit.

## Verification log

The sandbox could not read the default uv cache and a local-cache sync did not complete. Commands
therefore used the already-synced parent venv while pinning imports to this worktree:

```text
PYTHONPATH=. VIRTUAL_ENV=/Users/jaeyongryu/Projects/CMIG/.venv \
  UV_CACHE_DIR=/tmp/cmig-round7-t1-uv-cache uv run --active --no-sync <command>
```

### Environment and quality gates

```text
uv run pytest --version
-> initially blocked by sandbox access to ~/.cache/uv

<prefix> pytest --version
-> pytest 9.0.3

<prefix> ruff check .
-> All checks passed!

<prefix> pytest -q tests/test_cli_solve_medium.py tests/test_medium_presets_gut.py \
  tests/test_round7_exact_medium.py tests/test_workflow_map_coverage.py
-> 35 passed

<prefix> pytest -q tests/test_cli_solve_medium.py tests/test_medium_presets_gut.py \
  tests/test_round7_exact_medium.py tests/test_workflow_map_coverage.py \
  tests/test_workflow_envelope_golden.py tests/test_medium_namespace_bridge.py
-> 88 passed

<prefix> python scripts/build_gut_media.py --check
-> exit 0; all seven overlays and provenance_rows.csv current

git diff --check
-> clean
```

### Envelope gate before schema evolution

```text
<prefix> cmig golden verify-envelope
Workflow-envelope serialization gate:
  [OK ] abundance_impact
  [OK ] dfba
  [OK ] gene_ko_search
  [OK ] host_ko_impact
  [OK ] host_map
  [OK ] host_microbe_bigg
  [OK ] host_search_bigg
  [OK ] model_pool_search
  [OK ] model_quality
  [OK ] multi_target_model_pool_search
  [OK ] publication_benchmark
  [OK ] strain_growth
  [OK ] sweep
  [OK ] float normalization probe (NaN / ±inf / -0.0 / rounding floor)
-> envelope serialization unchanged for 13 workflow kinds
```

After adding the field and before re-blessing, the same command reported all 13 kinds plus the
float probe as drifted. The first canonical difference was exactly
`"medium_application_mode":"merge_onto_model_default"`; this was the expected guardrail failure.

### Re-bless and envelope gate after schema evolution

```text
<prefix> python -m cmig.core.workflow_envelope_golden
-> workflow-envelope golden re-blessed
-> 13 workflow hashes plus float-normalization probe rewritten

<prefix> cmig golden verify-envelope
Workflow-envelope serialization gate:
  [OK ] abundance_impact
  [OK ] dfba
  [OK ] gene_ko_search
  [OK ] host_ko_impact
  [OK ] host_map
  [OK ] host_microbe_bigg
  [OK ] host_search_bigg
  [OK ] model_pool_search
  [OK ] model_quality
  [OK ] multi_target_model_pool_search
  [OK ] publication_benchmark
  [OK ] strain_growth
  [OK ] sweep
  [OK ] float normalization probe (NaN / ±inf / -0.0 / rounding floor)
-> envelope serialization unchanged for 13 workflow kinds
```

### Real exact-medium CLI and `inspect-run`

A four-model methods-demonstration pool was used (the bundled pool is not a gut community). `iAF987`
was excluded because the provenance document records it as infeasible on every defined medium. The
shipped overlay has a zero-valued pool-closure row `EX_n2_m` unavailable to this four-model subset,
so the solve used `--allow-unknown-medium`; the dropped row and degraded status are reported rather
than hidden.

```text
<prefix> cmig solve \
  --taxonomy /tmp/cmig-round7-t1-demo.PBioHp/taxonomy.csv \
  --medium medium_presets/gut_overlay_vmh_high_fiber_x100.csv \
  --exact-medium --allow-unknown-medium --assume-bigg-namespace \
  --solver gurobi --out /tmp/cmig-round7-t1-demo.PBioHp/exact
-> exit 0
-> growth 0.0847 h^-1 (Gurobi 12.0.3, MICOM 0.39.0)
-> run_hash 6b807ba858358e58846cb7735118a3b4a59f79b1a957da275c76873163abe802

<prefix> cmig inspect-run --run-dir /tmp/cmig-round7-t1-demo.PBioHp/exact --format json
-> status: degraded (EX_n2_m not applied; requested limit was 0.0)
-> manifest.provenance.medium_application_mode: exact_boundary_isolation
-> manifest.provenance.n_undeclared_boundary_suppliers: 0
-> manifest.provenance.boundary_isolation.complete: true
```

A real workflow-manifest producer was also exercised:

```text
<prefix> cmig abundance-impact \
  --taxonomy /tmp/cmig-round7-t1-workflow.O0Heei/taxonomy.csv \
  --member iHN637 --fractions 0.25 --target ac \
  --medium medium_presets/gut_overlay_vmh_high_fiber_x100.csv \
  --exact-medium --allow-unknown-medium --solver gurobi \
  --out /tmp/cmig-round7-t1-workflow.O0Heei/exact
-> exit 0; run_hash 26953390ec63ea078c6df2807d34abc20b3f0406ad9ce04484132531d6c0edaa

<prefix> cmig inspect-run --run-dir /tmp/cmig-round7-t1-workflow.O0Heei/exact --format json
-> manifest_schema_version: 1.2
-> components.medium.medium_application_mode: exact_boundary_isolation
-> artifact_integrity: verified
-> result_digest match: true
```

### Default-path compatibility

The identical no-flag merge solve was run once from the untouched parent checkout and once from
this worktree, using the same taxonomy, overlay, Gurobi environment, and arguments. Both reported
growth `0.0847`, run hash `6b807ba858358e58…`, and byte-identical solve manifests:

```text
cmp before/manifest.json after/manifest.json
-> exit 0

sha256(before/manifest.json) = ee9c79c97e40c56dfbc7417b2a7044dbe88c7f6533f0ad829209e6b46467b9b7
sha256(after/manifest.json)  = ee9c79c97e40c56dfbc7417b2a7044dbe88c7f6533f0ad829209e6b46467b9b7
```

Thus the no-flag application semantics and solve-manifest bytes did not move. Workflow manifests
move only through schema `1.2`, the added hashed medium subfield, and the run hashes derived from
that field—the single deliberate envelope drift described above.

## Integration notes and risks

- `CHANGELOG.md` is outside T1 ownership. Its `[Unreleased]` Added entry still says exact-medium is
  “not implemented”; the coordinator should update that stale sentence when integrating this track.
- `cmig/core/workflow_envelope_golden.json` is the actual documented re-bless target even though the
  brief's ownership shorthand names `fixtures/**/expected/**`; no solve fixtures changed.
- Exact selection is scoped with a `ContextVar` because the stable service/search/host APIs are
  outside T1 ownership. The CLI path is covered, including parallel gene-KO workers. Direct callers
  of those lower APIs continue to select exact mode with their existing explicit `exact=True` API.
- Solve run hashes remain the frozen 11-component contract; solve manifests distinguish exact from
  merge in non-hashed provenance. Workflow manifests hash the mode under schema 1.2.
- The failed five-member demonstration was not treated as a result: it exited 3 with
  `solver_failed` because `iAF987` is infeasible on the defined overlay, consistent with §5 of the
  provenance document.

## Proposals deliberately not implemented

- Did not remove the seven overlay closure blocks because the brief's builder/test condition could
  not be satisfied without changing generator logic beyond the permitted data-table edits.
- Did not edit `scripts/build_gut_media.py`, the overlay CSVs, `CHANGELOG.md`, service APIs, search
  internals, host-coupling APIs, `pyproject.toml`, or `uv.lock`.
- Did not change the frozen solve hash schema or re-capture solver goldens.
- Did not push any remote.

## Git infrastructure blocker

The requested startup command was attempted exactly and Git rejected `.` as a commit:

```text
git checkout -B feat/exact-medium .
fatal: '.' is not a commit and a branch 'feat/exact-medium' cannot be created from it
```

The intended equivalent (`git checkout -B feat/exact-medium`) and every staging/commit attempt were
then blocked because this linked worktree's Git metadata is outside the writable sandbox:

```text
fatal: Unable to create
'/Users/jaeyongryu/Projects/CMIG/.git/worktrees/round7-T1-exact-medium/index.lock':
Operation not permitted
```

The Orca managed bridge was also unavailable (`runtime.state: stale_bootstrap`, app not running).
Consequently the implementation and this report are complete in the worktree, but the requested
branch rename and commits cannot be recorded from this sandbox. The worktree remains on
`jyryu3161/round7-T1-exact-medium` with the changes unstaged.
