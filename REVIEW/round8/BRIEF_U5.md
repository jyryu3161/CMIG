# Round-8 Track U5 — `feat/gui-sweep-overlays`

Read `REVIEW/round8/COMMON_BRIEF.md` first. You own the GUI layer only,
continuing round-7 T2's work (see `REVIEW/round7/report_T2.md` for what it
deliberately did not implement).

## Goal

1. **Real Sweep tab.** `cmig/gui/views.py::SweepView` currently exposes only
   tradeoff-f × solvers and drives `sweep-fixture`. Rebuild it to drive the
   real user `cmig sweep` workflow with its actual axes (taxonomy/model
   source, `--mediums`, `--abundance-variants`, `--member-sets`,
   `--bounds-variants`, `--tradeoff-fs`, `--solvers`) through the existing
   in-process CLI job pattern (`gui/app.py`'s `run_*` methods + `JobRunner`).
   Axis inputs may be file pickers/tables — no new dependencies, keep the
   progressive-disclosure placement. Preserve the fixture path as a smoke
   option, don't delete it.
2. **Profile heatmap.** Add the §11 heatmap surface to the External Profile
   area: metabolites × members (or scenarios) colored by flux with the
   established sign convention, Qt-native like round-7's charts, honest with
   missing values (blank + note, never zero-filled).
3. **Scenario-diff / delta overlay.** Round-7 T2 skipped "scenario-diff
   overlay, sandbox delta overlay". Implement the delta overlay: when a
   comparison (Compare tab result or sandbox preview delta) is active, the
   profile charts can show baseline vs variant (e.g. paired/overlaid bars with
   an explicit legend), reusing `cmig/core/delta.py` results already flowing
   into `ScenarioCompareView` — read-only consumption, do not change core.
4. Keep ALL GUI tests offscreen-green, extend `tests/test_round7_gui_*`
   conventions into `tests/test_round8_gui_sweep_overlays.py`.

## Constraints

- GUI is a shell over the CLI: reuse existing CLI/service entry points; no
  analysis logic in the GUI; no dependency changes.
- **Do not change the contribution chart's `edge.weight x abundance` display
  basis** even though track U2 is changing the weight semantics — the
  coordinator reconciles the basis after both tracks merge. Just make sure the
  basis note string is easy to find/update (one place).
- ko/en: every new user-facing string goes into the round-7 `I18N` catalogue
  with a real Korean translation.

## Ownership

- `cmig/gui/**`
- tests: `tests/test_gui_*.py`, `tests/test_app_shell.py`,
  `tests/test_round7_gui_graph_profile.py` (only if an assertion must learn the
  new layout), new `tests/test_round8_gui_sweep_overlays.py`
- Do NOT touch: `cmig/cli/main.py` (U1), `cmig/core/**` (U1/U2/U6), CHANGELOG.

## Verification to include in your report

- Offscreen run of the whole GUI test set (the coordinator will re-run it on
  the host if your sandbox SIGTRAPs QtWebEngine like round 7 — say so rather
  than skipping silently).
- Manual acceptance steps (like T2's) for: a real sweep launched from the tab,
  the heatmap, and a delta overlay on a fixture comparison.
