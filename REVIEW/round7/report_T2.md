# Round-7 T2 report — `feat/gui-graph-profile`

## What changed and why

- Mounted `InteractionGraphView` as a first-class **Graph** tab in `CmigMainWindow`.
  The existing Open Run path now sends every successfully read community tidy bundle to
  both the Graph and Profile tabs. A failed load clears both surfaces so a prior run cannot
  remain visible under a new failure message.
- Added a namespace `GateBadge` above the first-class graph. It reports either the
  successfully recorded namespace policy (`assume_bigg` or `require_reviewed`) or an
  explicit `NOT RECORDED`/unavailable state; it never invents a gate verdict from tidy data.
- Augmented `ExternalProfileView` with two dependency-free, Qt-native charts while retaining
  the complete read-only table:
  - a signed horizontal net-exchange chart using the existing green secretion / purple
    uptake convention, with FVA whiskers only when both finite bounds exist;
  - a signed stacked member-contribution chart. Direct `edges.parquet` fluxes are per-taxon,
    so each segment is `edge.weight × nodes.abundance`; allocated `cross_feeding` rows are
    excluded. Missing/non-finite basis data is omitted with a visible note, never replaced
    by zero. Both charts label that the display is limited to the 12 largest magnitudes while
    the table retains every row.
- Replaced the no-op ko/en catalogue with actual Korean strings for the explorer, job
  headers, primary and progressive-disclosure tab titles, toolbar actions, namespace badge,
  and application status-bar messages. English is now the single factory/constructor/CLI
  default; Korean remains explicit opt-in through `cmig gui --lang ko` or
  `cmig-gui --lang ko`.
- Corrected `_NoEditorDelegate.createEditor` to match PySide6's override signature, including
  `QModelIndex | QPersistentModelIndex` and the stub's non-optional `QWidget` return. The
  runtime still returns Qt's null widget pointer through a documented cast, preserving the
  read-only-table invariant.
- Added round-7 tests for Graph-tab/Open Run wiring, GateBadge provenance, FVA state,
  abundance-weighted member contributions, cross-feeding exclusion, missing-value honesty,
  Qt-native offscreen painting, real Korean strings, and the English default.

## Verification log

The worktree-local sync could not complete because the sandbox has no DNS access for the
locked `gurobipy==12.0.3` wheel. Verification therefore used the already-synced primary
checkout environment via `UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv`,
`UV_CACHE_DIR=/tmp/cmig-round7-t2-uv-cache`, `PYTHONPATH=<this worktree>`, and
`uv run --no-sync`. That environment contains pytest 9.0.3, PySide6 6.11.1, pyarrow 24.0.0,
and gurobipy 12.0.3.

- `uv run --no-sync ruff check .`
  - **PASS** — `All checks passed!`
- `uv run --no-sync mypy cmig/gui/builder.py cmig/gui/views.py cmig/gui/graph_view.py cmig/gui/app.py`
  - **PASS** — `Success: no issues found in 4 source files`
- `uv run --no-sync pytest -q tests/test_graph_data.py tests/test_gui_editors_builder.py tests/test_gui_views.py tests/test_round7_gui_graph_profile.py`
  - **PASS** — 31 passed.
- `uv run --no-sync cmig golden verify-envelope`
  - **PASS** — 13/13 workflow kinds OK; float-normalization probe OK; serialization unchanged.
- `git diff --check`
  - **PASS** — no whitespace errors.
- Whole owned GUI command:
  `uv run --no-sync pytest -q tests/test_gui_*.py tests/test_app_shell.py tests/test_host_view.py tests/test_graph_data.py tests/test_round7_gui_*.py`
  - **ENVIRONMENT BLOCKED** — process exits 133 (`SIGTRAP`) after ten tests when
    `QWebEngineView.load()` initializes Chromium under this managed macOS sandbox. The same
    exit 133 reproduces on the pre-existing renderer-only test
    `tests/test_gui_render.py::test_widget_constructs_and_renders_without_error`; macOS writes
    a Python crash report whose faulting stack is inside QtWebEngine 6.11.1/Chromium. Adding
    `QT_ACCESSIBILITY=0`, disabling GPU/software rasterization, disabling Chromium sandbox,
    and disabling LiveCaption/MacAccessibilityAPIMigration did not change the result. The
    renderer-independent GUI and new shell-wiring tests above are green; actual Cytoscape
    rendering still requires the coordinator's normal desktop/Linux offscreen environment.

## Screenshot-free manual acceptance

1. From a fully synced checkout with a Gurobi licence, create a tidy fixture run with FVA:
   `uv run cmig solve-fixture --solver gurobi --fva --out runs/round7_gui_fixture`.
2. Launch the English-default GUI: `uv run cmig gui`.
3. Click **Open Run** (or press the standard Open shortcut) and select
   `runs/round7_gui_fixture`. The GUI opens **Profile** and registers the directory under
   Project Explorer → Runs.
4. In **Profile**, verify the left chart diverges around zero (green/right secretion,
   purple/left uptake), recorded FVA rows have whisker/cap lines, and the right chart has
   member-colored signed stacks. Confirm the note states that direct member↔pool edge flux is
   multiplied by recorded abundance and that allocated cross-feeding is excluded. The full
   four-column
   table remains below both charts.
5. Click **Graph**. Verify the Cytoscape interaction graph, edge-family controls, top-edge
   table, and namespace GateBadge are visible. A fixture without reconstructable namespace
   provenance must say the gate status is not recorded, rather than showing a fabricated OK.
6. Relaunch with `uv run cmig gui --lang ko`. Verify the explorer, primary/advanced tabs,
   workflow toolbar, Ready/loaded-run status messages, and namespace badge use Korean. Relaunch
   without `--lang` and verify those surfaces default to English.

## Integration notes / risks

- `CHANGELOG.md` is outside T2 ownership, although this intentional GUI behavior change needs
  an Unreleased entry under the common brief. Coordinator proposal: “Added first-class Graph
  and charted External Profile tabs; implemented real Korean GUI localization and made English
  the single default.”
- The stacked contribution chart intentionally reconstructs community-basis contributions from
  tidy presentation artifacts because `edges.weight` remains the known-open per-taxon value.
  It does not alter artifacts, schemas, hashes, solver behavior, or core analysis logic.
- Graph gate provenance currently recognizes the two policies emitted by solve manifests. An
  older or otherwise incomplete manifest stays visibly `NOT RECORDED`; this conservative state
  is deliberate.
- The chart canvases show at most 12 measured metabolites by magnitude for legibility. The table
  remains authoritative for the complete profile and all exact displayed values.
- Startup Git operations are blocked by the managed filesystem: the literal requested command
  `git checkout -B feat/gui-graph-profile .` first failed because `.` is not a commit; the
  intended `git checkout -B feat/gui-graph-profile` then failed creating
  `/Users/jaeyongryu/Projects/CMIG/.git/worktrees/round7-T2-gui-graph-profile/index.lock`
  (`Operation not permitted`). Orca's runtime is also unavailable (`runtime_unavailable`), so
  no supported out-of-sandbox terminal exists. The same Git-admin restriction prevents T2's
  implementation/report commits from being created in this session.

## Deliberately not implemented

- No `CHANGELOG.md`, CLI, core, manifest, schema, dependency, or lockfile change (outside T2
  ownership).
- No heatmap, scenario-diff overlay, sandbox delta overlay, or chart export redesign; those are
  separate spec items beyond this track's three requested chart surfaces.
- No attempt to “fix” `edges.parquet.weight` in the GUI. The chart applies the documented
  abundance basis for presentation and leaves the known-open artifact value/schema untouched.
- No matplotlib/QtCharts dependency or fallback path; the charts are entirely Qt-native.
- No silent GateBadge OK fallback when namespace provenance is absent.
