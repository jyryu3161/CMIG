# Round-8 U5 report — `feat/gui-sweep-overlays`

## What changed and why

- Rebuilt the advanced Sweep tab around the real `cmig sweep` product workflow. The tab now
  accepts either a taxonomy CSV or a model folder, all six condition axes (`--mediums`,
  `--abundance-variants`, `--member-sets`, `--bounds-variants`, `--tradeoff-fs`, and
  `--solvers`), the required namespace decision, and the existing exact-medium/FVA options.
  Model-folder input is converted to a taxonomy inside the background job before invoking the
  CLI. The Run button defaults to this real path; `cmig sweep-fixture` remains available through
  an explicit **Use built-in fixture smoke sweep** checkbox and through the existing
  `run_sweep_fixture()` method.
- Kept the GUI as a shell over the CLI. Both sweep modes snapshot the visible request, submit the
  same in-process `argv` + `cmig.cli.main.main()` job pattern as the other tabs, remain observable
  through `JobRunner`, and reload `sweep.parquet` into a read-only result matrix. The matrix now
  retains the six axis values and per-condition diagnostic alongside value/status/cache state.
  A CLI scientific failure remains a failed Job; if it wrote diagnostic-bearing sweep artifacts,
  those failed rows are still displayed instead of being discarded.
- Added a dependency-free, Qt-native flux heatmap under External Profile. A nested **Heatmap**
  surface shows metabolites×members for complete tidy bundles and metabolites×scenario for a
  plain/current profile or comparison. Positive values use the established green secretion
  convention, negative values use purple uptake, and a measured zero gets a neutral fill.
  Missing/non-finite values remain blank with an explicit note; they are never zero-filled.
- Added a baseline/variant overlay to the profile charts using `DeltaResult` values without
  recomputation. The net-flux chart uses paired light (baseline) and solid (variant) signed bars
  with an explicit legend, while the heatmap switches to baseline/variant scenario columns.
  Scenario Compare results and completed sandbox preview/commit results both activate the
  overlay. Because `DeltaResult` carries external flux but not per-member exchange, member bars
  are deliberately blank while an overlay is active, with that limitation stated in the UI.
  **Clear comparison overlay** restores the last loaded profile and member matrix.
- Added all new visible copy and dialog strings to the existing en/ko `I18N` catalogue with real
  Korean translations. The contribution display basis remains unchanged as requested and its
  English wording is centralized in `CONTRIBUTION_BASIS_NOTE` for the U2 merge reconciliation.
- Added `tests/test_round8_gui_sweep_overlays.py` with coverage for real-button dispatch and all
  CLI axes, model-folder taxonomy generation, failed-sweep artifact visibility, fixture opt-in,
  sparse/missing heatmap values, offscreen painting, overlay restoration, Compare and Sandbox
  wiring, and Korean strings.

## Verification log

The first `uv run --no-sync` invocation encountered the managed sandbox's unreadable default UV
cache (`~/.cache/uv/sdists-v9/.git`, `Operation not permitted`). All commands below retained
`--no-sync` and used `UV_CACHE_DIR=/tmp/cmig-round8-u5-uv-cache`; no sync or dependency change was
performed.

- `UV_CACHE_DIR=/tmp/cmig-round8-u5-uv-cache uv run --no-sync ruff check .`
  - **PASS** — `All checks passed!`
- `UV_CACHE_DIR=/tmp/cmig-round8-u5-uv-cache uv run --no-sync mypy cmig`
  - **PASS** — `Success: no issues found in 77 source files`
- `UV_CACHE_DIR=/tmp/cmig-round8-u5-uv-cache uv run --no-sync cmig golden verify-envelope`
  - **PASS** — all 13 workflow kinds and the float-normalization probe OK; serialization
    unchanged.
- `git diff --check`
  - **PASS** — no whitespace errors.
- Renderer-independent owned/adjacent tests, run per file because this PySide/macOS environment
  can terminate a multi-file pytest process when the application object crosses module teardown:
  - `... pytest -q tests/test_gui_editors_builder.py` — **10 passed**
  - `... pytest -q tests/test_gui_views.py` — **8 passed**
  - `... pytest -q tests/test_graph_data.py` — **8 passed**
  - `... pytest -q tests/test_round7_gui_graph_profile.py` — **5 passed**
  - `... pytest -q tests/test_round8_gui_sweep_overlays.py` — **10 passed**
- Eight adjacent App Shell / round-5 sandbox/read-only contracts were also run with a
  verification-only `/tmp` QWidget graph stub (no workspace file) so controller behavior could
  be exercised without constructing Chromium:
  - advanced-tab placement, fixture sweep, real scenario comparison, sandbox preview, all result
    tables read-only at view and item level, sandbox request provenance, and no-result button
    release — **8 passed**.
- Mandated whole-GUI offscreen attempt:
  `... pytest -vv -s --randomly-dont-reorganize tests/test_gui_*.py tests/test_app_shell.py
  tests/test_host_view.py tests/test_graph_data.py tests/test_round7_gui_*.py
  tests/test_round8_gui_*.py`
  - **ENVIRONMENT ABORTED** — pytest collected 127 tests and passed the first 10, then
    `tests/test_gui_launcher.py::test_launcher_builds_and_runs` constructed QtWebEngine. Chromium
    aborted in `mach_port_rendezvous_mac.cc` because
    `bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer...` returned
    `Permission denied (1100)`. This is the same managed-macOS QtWebEngine failure recorded by
    round-7 T2; the coordinator should rerun the whole set on the normal host/Linux offscreen
    environment. It was not silently skipped.

## Screenshot-free manual acceptance steps

### Real Sweep tab

1. Launch `UV_CACHE_DIR=/tmp/cmig-u5 uv run --no-sync cmig gui`, enable **Show Advanced
   Tools**, and open **Sweep**.
2. Select exactly one source: a real taxonomy CSV or a folder of prepared microbial GEMs. Select
   a reviewed namespace-decisions JSON file or explicitly confirm BiGG namespace.
3. Populate at least two axes, for example tradeoff `0.3,0.5`, two medium files, member sets
   `A+B;A+C`, one abundance file, one bounds file, and `gurobi`; then click **Run Sweep**.
4. Verify Runtime & Jobs shows kind `sweep`, the window remains responsive, and completion
   populates condition, value, status, cache, all six axis columns, and diagnostic. The completion
   status names the registered temporary output directory. For the preserved smoke path, tick
   **Use built-in fixture smoke sweep** and verify its command completes through the same job UI.

### Profile heatmap

1. Open a completed community tidy run and select **Profile → Heatmap**.
2. Verify rows are metabolites and columns are members, positive cells are green, negative cells
   are purple, and measured zero cells have a neutral gray fill.
3. Verify unavailable member/metabolite cells are blank and the note explicitly says they were
   not zero-filled. Cross-check a few cells against the member contribution chart/table basis.

### Fixture delta overlay

1. Create two fixture-derived runs, for example a baseline with
   `uv run --no-sync cmig solve-fixture --out runs/u5_base` and a committed variant with a valid
   fixture bound via `cmig sandbox-fixture ... --commit --out runs/u5_variant` (the CLI help lists
   the fixture reaction syntax).
2. Enable advanced tools, open **Compare**, select `runs/u5_base` as Run A and
   `runs/u5_variant` as Run B, then click **Compare**. Alternatively, run a bound **Preview** in
   **Sandbox** to exercise the direct sandbox overlay path.
3. Switch to **Profile**. Verify the signed net chart identifies baseline as light and variant as
   solid, includes both names in its legend, and the Heatmap has baseline/variant columns. Confirm
   the UI states why member contributions are blank for `DeltaResult`.
4. Click **Clear comparison overlay** and verify the previously opened profile/member charts are
   restored.

## Proposed CHANGELOG entries

- Added a real GUI parameter-sweep workflow covering taxonomy/model source and all six `cmig
  sweep` axes, while retaining the fixture sweep as an explicit smoke option.
- Added Qt-native external-profile flux heatmaps and baseline/variant overlays for Scenario
  Compare and Sandbox deltas, with explicit missing-value and provenance notes.

## Integration notes / risks

- Track U2 is changing edge-weight semantics. Per the U5 constraint, this track did **not** change
  the contribution chart's `edge.weight × abundance` display basis. The coordinator should
  reconcile `cmig.gui.views.CONTRIBUTION_BASIS_NOTE` and `member_contribution_rows()` after merging
  U2 if the artifact basis changes.
- `DeltaResult` exposes external profile values only. U5 therefore does not invent per-member
  baseline/variant fluxes; the member contribution chart is blank and explicitly labelled during
  an overlay. A future core contract carrying per-member deltas could extend this honestly.
- The heatmap and charts display up to 12 metabolites for legibility. The authoritative profile
  table remains complete. Member matrices are sparse by design: absence remains blank, not a
  measured zero.
- The real sweep follows existing GUI behavior and writes into a registered OS temporary
  directory. The explorer exposes that directory, but long-term run-directory selection remains
  a broader GUI product decision outside this track.
- No CLI, core, manifest/schema, golden, solve fixture, dependency, lockfile, README, or CHANGELOG
  file was changed.

## Proposals deliberately not implemented

- No GUI-side sweep enumeration, model analysis, delta computation, or missing-value imputation;
  those remain in CLI/core contracts.
- No attempt to add per-member values to `DeltaResult` or reinterpret missing scenario values.
- No re-blessing of workflow envelopes or solve goldens.
- No chart export redesign, new plotting dependency, or QWebEngine workaround.
- No automatic namespace assumption and no silent selection between taxonomy and model-folder
  inputs.
