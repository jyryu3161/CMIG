# Round-9 Track V4 — `feat/gui-medium-tools`

Read `REVIEW/round9/COMMON_BRIEF.md` first. You own the GUI layer only.
Spec §11 (`CMIG_명세서_v3.0.md`) requires a real medium-editing surface:
"medium 편집(CSV paste·preset·Check Growth·minimal medium·before/after
profile)" — none of which the Medium editor currently has.

## Goal

Extend `cmig/gui/editors.py::MediumEditor` (behind Show Advanced Tools; keep
its existing table contract intact) with:

1. **Preset picker.** Enumerate `medium_presets/*.csv`, load the chosen file
   through the real loader (`cmig.core.medium_spec.load_medium`), and display
   it. Surface the round-8 `row_role` column when present: show
   `pool_closure` rows visually distinct with the documented warning that
   stripping them is only safe for exact-medium/other-pool use, and offer a
   "nutrients only" view that mirrors the documented stripping semantics
   (display-level; never rewrite the preset files).
2. **CSV paste.** Paste `exchange_id,uptake_limit[,row_role]` text into the
   table with the same validation the loader applies; invalid rows are named,
   never silently dropped.
3. **Check Growth.** A button that runs a real growth check for the current
   medium against a user-selected taxonomy through the existing in-process CLI
   job pattern (`cmig solve` with the medium written to a temp file; merge vs
   exact mode is an explicit toggle mirroring `--exact-medium`). Non-blocking
   via `JobRunner`, results (growth, status, dropped ids) shown with the same
   honesty rules as the CLI. Do not re-implement any solve logic.
4. **Before/after profile.** After a Check Growth on a modified medium, show
   the external-profile delta vs the previous check (reuse the round-8 overlay
   machinery in `views.py` where possible) — clearly labelled, cleared when the
   medium changes again.
5. **`cmig minimal-medium` hook.** A button that launches the round-8
   `minimal-medium` CLI for a selected single model + current medium and shows
   the components/limiting nutrients. CLI exists; this is pure wiring.

All new strings get real Korean translations in the `I18N` catalogue. All
tests offscreen-green; extend into `tests/test_round9_gui_medium_tools.py`.
GUI stays a shell over the CLI — zero analysis logic in `cmig/gui/**`.

## Ownership

- `cmig/gui/**`
- tests: `tests/test_gui_*.py`, `tests/test_app_shell.py` (additive),
  new `tests/test_round9_gui_medium_tools.py`

## Verification to include in your report

- Offscreen test run; manual acceptance steps for each of the five features
  (the coordinator re-runs the full GUI set on the host).
- Proof the preset files on disk are untouched by the nutrients-only view.
