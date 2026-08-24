# Round-7 Track T2 — `feat/gui-graph-profile`

Read `REVIEW/round7/COMMON_BRIEF.md` first. You own the GUI layer only. Do NOT
touch `cmig/cli/main.py` or any `cmig/core/*` file.

## Goal

Close the three biggest GUI gaps against spec §11 (`CMIG_명세서_v3.0.md`):

1. **Mount the Interaction Graph as a first-class tab.**
   `cmig/gui/graph_view.py::InteractionGraphView` and `GateBadge` are fully
   implemented and tested but only instantiated inside
   `cmig/gui/host_view.py` (host sub-panel). Add a `Graph` tab to
   `CmigMainWindow` fed by community-solve tidy bundles (see
   `cmig/gui/graph_data.py` for the data bridge; runs are loaded via the
   existing Open Run path). Include the namespace `GateBadge` in that surface.
2. **Charts for the External Profile view.** Replace/augment the 4-column table
   in `cmig/gui/views.py::ExternalProfileView` with: a diverging horizontal bar
   chart (net exchange flux, uptake vs secretion colored by the existing sign
   convention), a per-member stacked contribution bar, and FVA error bars when
   FVA columns are present. Qt-native painting or QtCharts-free custom widgets
   preferred — do NOT add a dependency (matplotlib is an optional extra; the GUI
   must not hard-require it; if you use it, degrade gracefully when absent).
3. **Real ko/en i18n.** `cmig/gui/app.py` `I18N` currently has identical English
   strings under both "ko" and "en" (a no-op). Provide actual Korean
   translations, extend coverage to tab titles, toolbar actions, and status
   messages, and fix the default-language mismatch (`build_main_window(lang="ko")`
   vs `cmig-gui` default "en") — pick "en" as the single default and make
   `cmig gui --lang ko` the opt-in (record the decision in your report).
4. **Small fix:** `cmig/gui/builder.py` `createEditor` return-type mypy error
   (PySide6 override signature).

## Ownership

- `cmig/gui/**` (all files)
- tests: `tests/test_gui_*.py`, `tests/test_app_shell.py`,
  `tests/test_host_view.py`, `tests/test_graph_data.py`, new
  `tests/test_round7_gui_*.py`

## Constraints

- All tests must pass offscreen (`QT_QPA_PLATFORM=offscreen` is forced by
  `tests/conftest.py`).
- The GUI is a shell over the CLI: do not re-implement analysis logic; only
  read existing run artifacts / call existing service-layer entry points.
- Keep the Advanced Tools progressive-disclosure behavior intact.

## Verification to include in your report

- Offscreen test run for the whole GUI test set.
- Screenshot-free acceptance description: exact manual steps to see the Graph
  tab and charts with a fixture run (the coordinator will perform them).
