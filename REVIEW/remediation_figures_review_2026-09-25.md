# Independent figure and bounded documentation review — 2026-09-25

Reviewer: GPT-6 Astra; task `task_5be31a34162a`, dispatch `ctx_7a2852d5aa86`. **Disposition: request changes for saved F9 (FR-1); accept F2 signed geometry and stored-score handling.** The TIFF layout passes the bounded cases, but the actual saved SVG still clips scientifically relevant caption text in the Qt consumer. This is an independent final-file rendering finding, not a repetition of the already assigned science or GUI follow-ups.

Read `AGENTS.md`, the root specification §9/§14, remediation design F2/F9/lane D and bounded documentation scope, the figure integration report, the original UI audit F2/F8/F9 and documentation section, the consolidated audit, relevant current writers/consumers, and the science/GUI lane reports. Only this report and ignored `.run/remediation-20260925/figure-review/` evidence were written. No implementation, tests, docs, Git state, dependency installation or environment configuration was changed.

## Verdicts

| Scope | Verdict | Independent evidence |
| --- | --- | --- |
| F2 signed contributions | **Pass** | Ten rendered cases; sign-specific cumulative bases/widths match the supplied contributions, the marker equals the stored total, annotations use the same six-significant-digit value, and input scores/order are unchanged. |
| Invalid ranked data | **Pass in the bounded matrix** | All 22 missing, nonnumeric, nonfinite, inconsistent-total, non-optimal-status and malformed-weight cases reject before writing SVG or TIFF; genuine zero and cancellation of positive/negative terms remain plotted as zero totals. |
| F9 TIFF | **Pass in the bounded matrix** | Actual final TIFFs are RGB, 600 dpi, LZW; all measured visible text fits at both 300 and 600 dpi, including the long-label case. Images were opened and inspected. |
| F9 saved SVG | **Not accepted: FR-1** | Actual final SVG rendered by Qt 6.11.1 clips Pareto/normalized captions and long target labels despite passing the implementation's Agg bounds check. |
| Artifact/consumer contract | **Pass for names and order** | Writer retains `search_plot.svg` and `search_plot.tiff`; Search chooses the same existing SVG for Ranking, with no invented multi-target Scatter artifact. Positive target/rank order is preserved. |
| Bounded documentation | **No independent new blocker beyond FR-1; pending assigned science/GUI gates remain** | Units, normalized weights, report order, workflow availability, unknown host values, partial attempts, installed presets, solver prerequisites, and integrity limits were checked against the source and assigned correction boundary. Parser probes pass for 20 USAGE and 33 USER_GUIDE examples. |

## FR-1 — P2: saved SVG text does not fit in its real Qt consumer

**Paths:** `cmig/cli/main.py:_write_multi_target_figure` (line 8076 at review), especially the measured wrapping and pre-export bounds guard; `cmig/render/figure_style.py:load_matplotlib_pyplot`; real consumer `cmig/gui/builder.py:refresh_figure_mode`.

**Reproduction:**

```sh
QT_QPA_PLATFORM=offscreen uv run --no-sync python .run/remediation-20260925/figure-review/probe.py
```

The probe reconstructs result objects from the unchanged historical `mixed/search_summary.json` and `pareto/search_summary.json`, invokes the production writer to create fresh final SVG/TIFF files, and independently renders those saved SVG bytes using `QSvgRenderer`. It measures every SVG `text_*` group with `boundsOnElement` plus its ancestor transform, then renders a 1560-pixel-wide PNG at the original viewBox ratio. TIFF previews are independently derived from the actual 600-dpi TIFFs. Neither preview replaces the final file.

| Actual final file | SVG canvas width | Right overflow in Qt | Agg text margin at 300 / 600 dpi |
| --- | ---: | ---: | ---: |
| `historical-pareto.svg` | 748.8 points | **58.402 points** (caption right edge 807.202) | +46.2 / +92.4 px |
| `weighted-normalized.svg` | 748.8 points | **34.93325 points** | +46.2 / +92.4 px |
| `bounded-long-labels.svg` | 748.8 points | **61.9645 points** caption; **5.24338 / 9.665255 points** target legend entries | +56.175 / +112.35 px |

The PNGs visibly corroborate the measurements: Pareto's first caption line loses its right end, including part of the score/front caveat; normalized output loses the recorded-weight explanation; long target labels extend beyond the right edge. The long member labels remain within the canvas but extend into the plot in Qt, unlike the TIFF. No row-label vertical overlap was measured in the five-row case. The extra deliberately nonmonotonic Pareto-order case also clips its SVG caption; this has the same cause, not a second finding.

**Evidence:** [actual Pareto SVG preview](../.run/remediation-20260925/figure-review/historical-pareto-svg.png), [paired TIFF preview](../.run/remediation-20260925/figure-review/historical-pareto-tiff.png), [normalized SVG](../.run/remediation-20260925/figure-review/weighted-normalized-svg.png), [long-label SVG](../.run/remediation-20260925/figure-review/bounded-long-labels-svg.png), [paired long-label TIFF](../.run/remediation-20260925/figure-review/bounded-long-labels-tiff.png), and full per-text bounds in [measurements.json](../.run/remediation-20260925/figure-review/measurements.json).

**Consumer/font contract and cause evidence:** Agg resolves `/System/Library/Fonts/Supplemental/Arial.ttf`. The final editable SVG emits `font-family: 'Arial', 'Helvetica', 'DejaVu Sans', sans-serif`; Qt logs a missing combined family resembling `Arial', 'Helvetica', 'DejaVu Sans', Sans-seri` and uses different glyph metrics. An evidence-only diagnostic replaces that CSS family list with single `Arial` in copies of the three final SVGs. Qt's minimum text margins then become positive: **10.211531, 10.211531 and 12.947531 points**, respectively, without changing wrapping, coordinates or text. This strongly isolates font-list interpretation/metric divergence; no production correction was made. See `font_diagnostic.py`, `font-diagnostic.json` and `environment-fonts.json`.

**Minimal correction guidance:** Resolve a font the actual SVG consumer supports and keep wrapping/export metrics consistent with that font, retaining an appropriate fallback strategy. Preserve editable SVG text (`svg.fonttype='none'` and the existing publication regression); converting every label to paths or dropping units/caveats would evade the intended contract. Validate fresh final SVG through Qt, plus the actual TIFF, for the historical Pareto and mixed cases, normalized caption, and bounded long labels. Check both canvas containment and label intrusion/overlap. Keep the signed geometry, totals, target/rank order, filenames, full units, normalizer, and Pareto reporting caveat unchanged. A pre-export Agg check or TIFF-derived PNG alone is insufficient.

Escalated as `msg_bd651a13a7d6`; coordinator accepted this as a material saved-F9 defect (`msg_9cdf957a7923`) and assigned correction separately. This report finishes without waiting for that correction.

## Numerical and semantic evidence

- Historical mixed rows each retain `glc__D=-10`, `ac=13.358851988170386`, stored total **3.358851988170386**. The blue bar starts at zero and extends to −10; the orange bar starts independently at zero and extends right; both black diamonds equal the stored total. Annotation `3.35885` is the documented numeric formatting, not a recomputed positive subtotal.
- All-positive rows `[2,5,1]`, `[3,1,2]`, `[1,1,1]` retain totals **8,6,3**, target order A/B/C and original top-to-bottom member order. The earlier writer was source-compared: that same positive ordering is preserved.
- All-negative rows `[-2,-5,-1]` and `[-3,-1,-2]` use bases `[0,-2,-7]` and `[0,-3,-4]`, totals **−8/−6**. No absolute-value conversion or clamp is applied.
- Zero cases `[-5,5,0]`, `[0,0,0]`, `[-7,2,5]` each mark **0**. Multi-sign four-target rows prove later positive and negative segments accumulate on their own sides; totals are **4/−4**.
- `normalized_weighted` keeps stored pre-weight scores `[-2,4]` and weights `[3,2]`, draws **−6/+8**, and marks **2**. A second row `[0.5,0.25]` draws **1.5/+0.5**, also totaling **2**. No clipping to [0,1], renormalization, double application of non-normalized weights, or mutation of input values occurred. A carbon-equivalent fixture preserves its already weighted values and `mmol C gDW^-1 h^-1` caption.
- Historical Pareto rows retain their recorded **13.358851988170386** display score and explicit zero contribution. A separate synthetic Pareto input ordered **6,9,5** remains in that order, proving the writer does not sort by scalar score. The complete caption states the full weighted-flux unit, normalizer, sampled-front reporting order and absence of a scalar best-point claim; FR-1 prevents all of that text being visible in Qt.
- Historical Pareto summaries contain old `missing_targets=['but']` and explicitly stored zero. These were used as immutable historical visual fixtures, not accepted as newly established capability measurements or current scientific output. The writer does not invent missing values: deleting a required score rejects. Review of upstream missing-target scientific semantics remains outside this lane.
- The bounded long case has **five displayed records, two 46/47-character target identifiers, three named strains per consortium, and four warning strings**. Input warnings remain unchanged; full run warnings belong to summary/GUI details, not an undocumented promise that all warnings appear in this saved figure. The figure's full Pareto caveats were inspected; TIFF fits, Qt SVG does not. GUI F8/GR-4 warning visibility is separately assigned and was not re-reviewed here.

`measurements.json` records the expected/actual bar positions and widths, totals, labels, captions, warning counts, final format properties and every measured text extent. No new solver or biological-validity claim is made from these rendering fixtures.

## Documentation and assigned correction boundary

The updated `docs/USER_GUIDE.md`, `docs/USAGE.md` and Unreleased changelog accurately distinguish signed score contributions from absolute bar lengths, pre-weight normalized values from plotted weighted contributions, and Pareto report order from a total ordering of alternatives. Their saved-text-fit claim remains contingent on FR-1. Multi-target artifacts match the writer and Search consumer: Ranking SVG/TIFF, no multi-target Scatter or member-matrix promise.

Source checks support the bounded corrections on package-backed medium presets; package versus COBRA/optlang solver capability and license prerequisites; OSQP approximate community provenance; MICOM 0.39 pin/non-unit rejection and explicitly documented internal topology coupling; per-file versus guarded Search publication; result-byte integrity versus scientific validity; and the implemented `dfba-community` CLI. The guide no longer claims universal GUI reopening parity or that community dFBA lacks a CLI. The root specification's richer Pareto scatter/per-target GUI and optimization plans are not silently declared implemented by these docs; absence of those planned features is already scoped, not a new figure blocker.

**Explicitly pending, not new findings:** SC-01 collapsed-zero classification; SC-03/04 community exchange signs and duplicate uptake limits; SC-05 truthful per-LP baseline/capability ledgers, counts and cancellation; standalone dFBA attribute correction; and GUI GR-1–GR-5 remain under separate active correction/re-review. The coordinator confirmed that per-LP counts will increase while summary count keys persist. The docs do not freeze an attempt count, and explicitly say componentwise capability optima are separate LP outcomes. Statements about zero, reverse-unit support, nullable Host readback, summary validity and workflow-specific invalidation require those already assigned corrections to pass. This report does not approve their present implementation or reclassify them as fresh documentation defects.

`tests/test_docs_commands.py` covers README/USAGE flags but omits USER_GUIDE and does not fully parse values/required arguments. The independent `docs_probe.py` parses **20 USAGE and 33 USER_GUIDE** invocations against `build_parser`: all pass after substituting explicitly documented biomass shell variables with parser-only placeholders. No example was executed as a scientific run or network fetch, and those placeholder numbers are not biological validation. The initial unexpanded-variable errors are retained as harness evidence, not reported as product defects.

## Commands, source identity and limits

```sh
uv run --no-sync pytest -o addopts='' -q tests/test_remediation_figures.py tests/test_figure_publication_export.py tests/test_docs_commands.py
QT_QPA_PLATFORM=offscreen uv run --no-sync python .run/remediation-20260925/figure-review/probe.py
uv run --no-sync python .run/remediation-20260925/figure-review/docs_probe.py
QT_QPA_PLATFORM=offscreen uv run --no-sync python .run/remediation-20260925/figure-review/font_diagnostic.py
```

Focused tests: **43 passed, zero failed/skipped, exit 0**. Rendering probe: ten final SVG/TIFF pairs, all numerical assertions pass, 22/22 malformed records rejected; exit 0 records measurements rather than falsely asserting SVG containment. Docs probe and diagnostic font probe exit 0. The first rendering-harness run stopped on Pillow `IFDRational` JSON serialization; the evidence script was corrected to serialize DPI as floats, then completed. Its initial log is retained and is not an application failure. No full suite, broad quality gates, solver suite, native window/HiDPI acceptance, browser portability, R renderer or publication-validity certification was duplicated.

Fresh SVG/actual-TIFF previews were visually opened for historical Pareto and long labels; historical mixed SVG, normalized SVG/TIFF, and positive/negative/zero/four-target/carbon TIFF previews were also opened. Measurements cover all ten outputs. Environment: Python 3.12.11, Matplotlib 3.10.9, PySide6/Qt 6.11.1; exact environment/font evidence is stored alongside the renders.

HEAD was `0167529fa9ba81649b138c476c524dc4495d4954` on `main`, with other lanes' pre-existing uncommitted edits. `source-identity.json` stores full file hashes and per-function hashes; `source-check-final.json` confirms figure dependencies remained unchanged at the review check; only `search_product.py` changed under the active separate science correction during this interval, and those new scientific edits were not re-reviewed here. The reviewed `_write_multi_target_figure` SHA-256 is **`b3d513b62f174276a8624c5c13c1694bd0c4b4cdd2d553739738c73dff82d144`**. Use this function plus `figure_style.py`/atomic exporter identities when deciding whether unrelated later scientific CLI edits invalidate the figure evidence. A plot/font/export change requires focused FR-1 re-review; unchanged F2 evidence can be cited by final acceptance without duplicating this whole review.
