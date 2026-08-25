# Round-9 V4 report — `feat/gui-medium-tools`

## What changed and why

- Rebuilt `cmig.gui.editors.MediumEditor` as the specification-required medium-editing surface
  while retaining its original table contract in columns 0 and 1
  (`exchange_id`, `uptake_limit`). The tab remains behind **Show Advanced Tools**.
- Added a preset picker for the nine actual medium CSVs under `medium_presets/` (the
  `provenance_rows.csv` audit table is deliberately not presented as a medium). A selected file is
  loaded through the real `cmig.core.medium_spec.load_medium` loader before anything is displayed.
  Legacy two-column presets keep the role column hidden. Gut overlays expose their additive
  `row_role` column; `pool_closure` rows have a yellow background and the documented warning that
  removing them is safe only with exact-medium semantics, including use with another pool.
- Added a **Nutrients only** view. It hides and excludes only rows explicitly marked
  `pool_closure` from the in-memory `MediumSpec`; it never writes a preset. The GUI refuses to run
  that filtered view in merge mode because doing so would reopen undeclared model-default
  suppliers. Returning to the full view restores the closure rows from the unchanged table.
- Added clipboard CSV paste for `exchange_id,uptake_limit[,row_role]`, with or without the header.
  The normalized paste is validated by the real core loader via a temporary CSV. Blank ids, wrong
  column counts, invalid roles, duplicate ids, non-numeric/non-finite/negative limits, and
  namespace-alias conflicts are not dropped: the status names source row numbers and exchange ids.
  The table is replaced only after the complete paste validates.
- Replaced the old single-model `strain-growth` Check Growth wiring with the requested community
  `cmig solve` workflow. The user selects a taxonomy CSV and an explicit namespace policy, chooses
  merge or exact medium, and may explicitly allow unknown medium ids. The current table is written
  to a job-local temporary medium file and passed to the in-process CLI through `JobRunner`.
  Growth, scientific status, application mode, recorded diagnostics, and every CLI-recorded
  dropped medium id are shown. Non-zero CLI results with artifacts retain and display those
  artifacts but are not labelled complete or adopted as a comparison baseline.
- Added before/after external-profile comparison. The most recent successful Check Growth is kept
  as the baseline. A later successful check with a modified medium and the same taxonomy,
  namespace policy, and application mode is compared through the existing
  `cmig.core.delta.compute_delta` plus `ExternalProfileView.show_delta_overlay`; no profile math was
  added to the GUI. Editing/filtering the medium again clears that medium-owned overlay
  immediately. A taxonomy/mode change is explicitly labelled non-comparable instead of producing
  a misleading overlay.
- Added a `cmig minimal-medium` hook for one selected SBML/JSON/MAT model. Minimum growth and
  aerobic/anaerobic mode are explicit; the current medium, exact/merge choice, unknown-id policy,
  and namespace policy are forwarded unchanged to the CLI. The result table displays every
  emitted component, candidate uptake, and the CLI's leave-one-out limiting-nutrient label, plus
  achieved growth, status, warnings, and component counts. Failed scientific results retain their
  summary without being called complete.
- Added real Korean translations for every new visible control, warning, dialog, result, and job
  message in the existing en/ko `I18N` catalogue.
- Added `tests/test_round9_gui_medium_tools.py` for all five requested features and updated the
  three obsolete App Shell growth-check assertions from single-model `strain-growth` to taxonomy
  `solve` behavior.

The GUI remains a presentation and CLI-routing layer: solve, medium application, minimal-medium,
and profile-delta analysis all remain in the existing CLI/core implementations.

## Verification log

Every invocation used the required pre-synced environment with
`UV_CACHE_DIR=/tmp/cmig-round9-V4-uv-cache uv run --no-sync`; no sync, dependency, git, or remote
operation was run.

### Focused offscreen acceptance

- `QT_QPA_PLATFORM=offscreen ... pytest -q tests/test_round9_gui_medium_tools.py -p no:randomly`
  - **PASS — 6 passed.** Covers real-loader preset routing, conditional row roles and visual
    distinction, nutrients-only safety/file integrity, loader-backed CSV paste with named invalid
    rows, `cmig solve` argv/mode/dropped-id display, before/after overlay and edit invalidation,
    `minimal-medium` argv/results, and Korean strings.
- `QT_QPA_PLATFORM=offscreen ... pytest -q tests/test_gui_editors_builder.py
  tests/test_gui_views.py tests/test_round9_gui_medium_tools.py -p no:randomly`
  - **PASS — 24 passed.** Covers the original editor contract, profile overlay machinery, and the
    new track suite together.
- Controller/widget suite with a verification-only `/tmp` QWidget substitute for WebEngine:
  `QT_QPA_PLATFORM=offscreen PYTHONPATH=/tmp ... pytest -q
  -p cmig_round9_v4_webengine_stub tests/test_gui_round5_p2.py tests/test_gui_launcher.py
  tests/test_gui_editors_builder.py tests/test_gui_views.py tests/test_app_shell.py
  tests/test_round9_gui_medium_tools.py -p no:randomly --maxfail=1`
  - **PASS — 96 passed.** The substitute changed no workspace file and only prevented Chromium
    construction; all MediumEditor, JobRunner, CLI argv, completion polling, App Shell, read-only,
    and view/controller assertions executed normally.

### Required QtWebEngine distinction

- The real-WebEngine attempt
  `QT_QPA_PLATFORM=offscreen ... pytest -vv tests/test_gui_render.py -p no:randomly --maxfail=1`
  collected eight tests and terminated during the first
  `test_widget_constructs_and_renders_without_error` before pytest could emit a result summary.
- An earlier un-stubbed window attempt emitted repeated Chromium
  `SCDynamicStoreCreate failed with Error: 1100 - Permission denied` messages and could not finish
  a controller test. This is the managed-macOS QtWebEngine restriction named in
  `COMMON_BRIEF.md`/`ORCHESTRATION_NOTES.md`, not a MediumEditor/widget failure. The coordinator
  must rerun the full real-WebEngine GUI set on the host.

### Preset byte-integrity proof

A single offscreen audit recorded SHA-256 for every `medium_presets/*.csv`, loaded and toggled all
nine picker-visible presets, then recorded the hashes again and compared the complete listings:

```text
loaded_presets=9 total_rows=719
preset_bytes_unchanged=yes
```

The 719-row basis is the sum of data rows in the nine picker-visible medium files (all CSVs except
the provenance audit table). `cmp` found no before/after hash-list difference. The focused test
also asserts byte identity on a role-bearing preset after nutrients-only filtering.

### Repository gates

- `... ruff check .`
  - **PASS** — `All checks passed!`
- `... mypy cmig`
  - **PASS** — `Success: no issues found in 78 source files`
- `... cmig golden verify-envelope`
  - **PASS** — all 17 existing workflow kinds plus the float-normalization probe are OK;
    serialization is unchanged.

## Manual acceptance steps

### 1. Presets and nutrients-only view

1. Launch `cmig gui`, enable **Show Advanced Tools**, and open **Medium**.
2. Select `gut_overlay_agora_western.csv` and click **Load preset**. Verify 133 validated rows,
   the visible **Row role** column, yellow `pool_closure` rows, and the exact/other-pool warning.
3. Toggle **Nutrients only**. Verify the nine `pool_closure` rows disappear and the UI refuses a
   merge-mode run. Select **Exact medium** and verify the filtered medium becomes runnable.
4. Toggle back and verify the closure rows return. Re-hash the selected preset before and after if
   independently checking the no-write guarantee.

### 2. CSV paste

1. Copy and click **Paste CSV** with:

   ```csv
   exchange_id,uptake_limit,row_role
   EX_glc__D_m,3,nutrient
   EX_o2_m,0,pool_closure
   ```

2. Verify two rows appear and the closure role is styled.
3. Paste `EX_bad_m,-1,nutrient`, then a duplicate-id pair. Verify each request is rejected and the
   message names its source row and exchange id; the previously valid table is preserved.

### 3. Check Growth

1. Select a real taxonomy CSV and either a reviewed namespace-decision file or the explicit BiGG
   confirmation. Choose merge or exact mode; enable unknown-id relaxation only deliberately.
2. Click **Check Growth**. Verify Runtime & Jobs shows a non-blocking growth job and the window
   remains responsive.
3. On completion, verify growth, scientific status, selected application mode, diagnostics, and
   either `Dropped medium IDs: none` or the full recorded id list. Verify the temporary run is in
   Project Explorer and its tidy profile opens in **Profile**.

### 4. Before/after profile

1. Complete one successful Check Growth, change one uptake limit, and run Check Growth again with
   the same taxonomy, namespace policy, and application mode.
2. Verify **Profile** shows the light **Previous medium check** versus solid **Current medium
   check** overlay and matching heatmap columns.
3. Edit the medium once more without running. Verify the overlay clears immediately and the Medium
   tab says another check is required. Change taxonomy or exact/merge mode and verify the UI does
   not compare unlike contexts.

### 5. Minimal medium

1. Select one real model, set minimum growth and aerobic/anaerobic mode, and choose the namespace
   and medium application policies.
2. Click **Find Minimal Medium** and verify a non-blocking `minimal_medium` job appears.
3. Verify the result lists each CLI-emitted component and uptake, marks limiting nutrients as
   leave-one-out results, and shows achieved growth, status, warnings, and component count. A
   failed/infeasible summary must remain visibly failed and must not be labelled complete.

## Proposed CHANGELOG entries

- Added a complete advanced GUI Medium Editor with loader-validated preset selection, optional
  `row_role` display, visually distinct pool-closure rows, a safe exact-only nutrients view, and
  row-named CSV paste validation.
- Added non-blocking GUI hooks for taxonomy-based `cmig solve` growth checks and single-model
  `cmig minimal-medium`, including exact/merge and unknown-id policies, dropped-id/status display,
  limiting-nutrient results, and before/after external-profile overlays.
- Changed the Medium tab's former single-model `strain-growth` Check Growth action to the
  specification-required taxonomy-based community `cmig solve` workflow.

## Integration notes / risks

- `pyproject.toml` is frozen and currently packages only `cmig` in wheels; its explicit sdist list
  also omits `/medium_presets`. The source-worktree GUI finds the repository-level directory and
  all nine presets, but a built wheel/sdist will not contain those files. The coordinator should
  add `medium_presets` to distribution data (or establish another single canonical packaged
  location) in an authorized packaging change; duplicating the scientific CSVs under `cmig/gui`
  was deliberately avoided.
- The picker excludes `provenance_rows.csv` because it is a multi-preset provenance audit table
  with duplicate exchange ids, not a loadable medium. Every actual medium CSV in the directory is
  enumerated.
- A nutrients-only selection changes only the in-memory effective `MediumSpec`. It is blocked in
  merge mode because the documented safe stripping procedure requires exact mode. The canonical
  preset remains unchanged and no derived file is silently persisted.
- Profile comparison is limited to successful runs with the same taxonomy, namespace choice, and
  exact/merge mode. This intentionally sacrifices an overlay when contexts differ rather than
  attributing a taxonomy or medium-policy change to nutrient edits.
- GUI jobs continue to use registered OS temporary output directories, matching the existing App
  Shell convention. Project Explorer exposes them, but OS cleanup/persistent project storage is a
  broader product concern.
- No CLI, core, manifest/schema, golden, dependency, lockfile, preset, README, CHANGELOG, or docs
  file was changed. Existing solve `run_hash` components and all 17 envelopes remain unchanged.

## Proposals deliberately not implemented

- No GUI-side solve, medium translation, minimal-medium, limiting-nutrient, dropped-id inference,
  or profile-delta algorithm was added. The GUI invokes and displays existing CLI/core contracts.
- No preset save/overwrite action and no automatic export of a nutrients-only file was added; both
  would create a new provenance/staleness surface and are not required for the display-level view.
- No automatic `--allow-unknown-medium`, namespace assumption, exact-mode selection, or silent
  merge-to-exact conversion was added. Every answer-determining policy remains explicit.
- No solver/tradeoff control expansion was added to this focused medium-check surface; the existing
  `cmig solve` defaults remain authoritative and a broader solve-configuration UI is separate.
- No packaging-file change was made because `pyproject.toml`/`uv.lock` are frozen for this track.
- No QtWebEngine workaround or render-test weakening was added to the product. The `/tmp` QWidget
  substitute was verification-only; real WebEngine tests remain for the coordinator's host run.
