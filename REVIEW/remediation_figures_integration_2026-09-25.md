# Signed figure and documentation integration — 2026-09-25

Owner: GPT-6 Sol, lane D and bounded documentation integration. Scientific CLI
ownership was released before this edit. The GUI correction and its independent
re-review are separate coordinator gates; this report does not accept that lane.

## Disposition

| Finding | Result | Evidence |
| --- | --- | --- |
| F2 signed multi-target score figure | Fixed. Each positive contribution accumulates right of zero; each negative one accumulates left. The black diamond and annotation use the stored `weighted_score`, checked against the signed contribution sum. Missing, nonnumeric, nonfinite, non-optimal or inconsistent ranked values raise a diagnostic instead of becoming zero or a misleading plot. | `tests/test_remediation_figures.py`; actual audit mixed result in `.run/remediation-20260925/figures/mixed.svg`, `.tiff`, `.png` and `measurements.json`. The audit rows contain −10 and +13.3588519882, and both marked totals are 3.358851988170386. |
| F9 saved SVG/TIFF text | The initial Agg/TIFF bounds check missed QtSvg clipping in the saved SVG; the independent review recorded FR-1. The correction and final-file Qt evidence are below. | `.run/remediation-20260925/figure-correction/final-file-check.json` and paired SVG/TIFF previews. |

The preserved all-positive fixture keeps target and rank order and the full
unit in the caption. `normalized_weighted` bars multiply the recorded
pre-weight `target_scores` by the recorded target weights without changing the
stored values, so the bar sum agrees with `weighted_score`. Regression geometry
covers mixed, all-positive, all-negative and zero-total rows. The historical
Pareto score is a display
quantity only: rank remains report order on a sampled front, and the figure
caption states that the score does not identify a best point. No archive
scatter workflow was introduced. The existing `search_plot.svg` and
`search_plot.tiff` artifact names and GUI selection contract are unchanged.

## Documentation

- `docs/USAGE.md` now scopes GUI readback and workflow controls, names only
  available figures, explains integrity versus scientific outcome, nullable
  host point readouts, Pareto partial attempts, physical medium units, installed
  presets and actual solver prerequisites.
- `docs/USER_GUIDE.md` adds the attempt ledger and partial sampling policy,
  signed plot meaning, host target intervals/nulls, MICOM 0.39 non-unit input
  rejection and adapter coupling, packaged preset discovery, and byte-integrity
  limits. It corrects the older community dFBA “no CLI surface,” universal GUI
  reopening parity, unconditional native HiGHS and broad atomic/digest claims.
- `CHANGELOG.md` records these audited corrections under Unreleased without a
  version or golden change.

## Verification

`uv run --no-sync pytest -o addopts='' -q tests/test_remediation_figures.py
tests/test_figure_publication_export.py tests/test_docs_commands.py`:
**43 passed, 0 failed, 0 skipped**. Scoped Ruff on `cmig/cli/main.py` and the
two figure test files passed. `uv run --no-sync mypy cmig/cli/main.py` passed
for one source file. `git diff --check` passed on the owned tracked files.
There was no full-suite duplicate, environment sync, Git staging, commit,
push, source GEM edit, golden change or solver semantics edit.

The evidence figures were regenerated from the actual historical summaries
at `.run/audit-20260925/mixed/search_summary.json` and
`.run/audit-20260925/pareto/search_summary.json`. Their TIFFs are 600 dpi RGB
with LZW compression through the existing export policy. The PNGs are scaled
TIFF previews for visual review; they do not replace the full resolution
exports. Geometry, marked totals, source paths, dimensions and text margins
are in `.run/remediation-20260925/figures/measurements.json`.

## Limits

This verifies saved multi-target Search figures and bounded documentation. It
does not certify every other CMIG figure writer or biological validity of the
audit E. coli toy outputs. The GUI aspect-ratio preview was handled by lane B;
its independent review requested follow-up changes and root must re-review the
settled GUI tree. Astra scientific review also requested SC-01/SC-05 and
single-model dFBA serialization follow-up after the initial lane-A report. The
guide therefore describes per-target capability optima as separate LP outcomes,
without assuming a fixed Pareto attempt count; root owns science re-review.
The coordinator owns stable-tree full quality, release and
envelope gates, final builds, independent acceptance and Git publication.

## Saved SVG consumer correction after independent review

The final Astra review found that QtSvg interpreted Matplotlib's emitted
`font-family: 'Arial', 'Helvetica', 'DejaVu Sans', sans-serif` as a missing
combined family. Agg and 600 dpi TIFF text fitted, but the saved Pareto and
normalized captions and the five-row target legend extended past the SVG
canvas. The multi-target writer now resolves one installed font from the
existing Arial/Helvetica/DejaVu Sans stack and applies that family only while
creating and exporting this figure. Agg wrapping, editable SVG text and TIFF
therefore use the same font; the shared font stack and unrelated figure
writers retain their existing policy. Scientific scores, signed bar geometry,
rank order, units, normalizer, Pareto caveat and artifact names did not change.

Fresh outputs from the two immutable historical summaries and bounded
normalized/long-label fixtures are in
`.run/remediation-20260925/figure-correction/`. Each case has the saved SVG,
actual 600 dpi TIFF, Qt-rendered SVG PNG and TIFF-derived PNG; all eight PNGs
were opened and inspected. Independent `QSvgRenderer` measurements of final
SVG text groups show minimum canvas margins of **10.212 pt** for historical
mixed, historical Pareto and normalized-weighted, and **12.948 pt** for the
five-row long-label case. The latter has a **7.105 pt** member-to-plot gap,
**5.685 pt** minimum member-row gap, **37.119 pt** legend-to-plot gap and
**2.684 pt** legend-row gap. The SVG retains native `<text>` elements; all
four TIFFs are RGB, 600 dpi and LZW. Source-bar and stored-score geometry,
caption content, full text bounds and file properties are recorded in
`final-file-check.json` and `measurements.json`. The evidence scripts are
`probe.py` and `verify_final_files.py` in the same directory.

A new optional-PySide6 regression renders the *saved* SVG through QtSvg and
checks text containment, long member/legend spacing, editable text and the
TIFF policy. Focused figure/publication/docs tests: **46 passed, zero
failed/skipped**. Scoped Ruff and `mypy cmig/cli/main.py` pass. This is
final-file consumer evidence for the bounded figures, not a universal font
availability or publication-validity certificate; a separate independent
FR-1 re-review is still the acceptance gate.
