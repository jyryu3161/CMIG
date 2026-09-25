# Independent GUI and SVG correction acceptance — 2026-09-25

Reviewer: GPT-6 Astra; task `task_2f658ebcf123`, dispatch `ctx_3feaf629e808`. **Disposition: accept the assigned GUI and saved-SVG corrections within the tested boundaries.** GR-2a, GR-2b and FR-1 are closed by fresh independent reproduction. GR-1–GR-5 and the reviewed F2–F10 behavior remain functional; no material residual GUI interface incompatibility was reproduced. Separate scientific correction/acceptance and final integrated gates remain with their assigned owners.

Read `AGENTS.md`, the original remediation design's F2 and F3–F10 contracts, both independent re-review reports, the latest sections of `remediation_gui_2026-09-25.md` and `remediation_figures_integration_2026-09-25.md`, and the corrected source and relevant tests. Inspected `validate_search_summary`, direct Search loading, completed/failed job publication, Host loading and the current Host output writer, the multi-target writer, figure style/export helpers and GUI figure export. Only this report and ignored evidence under [gui-figures-acceptance](../.run/remediation-20260925/gui-figures-acceptance/) were authored. No production, repository test, documentation, Git, dependency/environment or credential changes were made; no commit or push.

**Remaining-findings disposition**

| Finding | Independent result |
| --- | --- |
| **GR-2a — prior verification inherited by rc=2 Search** | **Pass.** After loading digest-verified A, both real GUI → JobRunner → CLI failures publish B with `Integrity: not_recorded`, detail `State: not_recorded (no_manifest)`, B's exact directory and no A path in the integrity detail. Both Search pointers and selectable details refer to B; Explorer contains A and B, the job/scientific status stays failed with rc=2, zero ranking rows and disabled figure export. |
| **GR-2b — silently accepted malformed ranking** | **Pass.** The original `[5]`, `score: {}` and `target_flux: {}` summaries now reject despite valid production digests. A further ten consumed numeric-field variants reject on direct load, and all three original shapes reject through both emulated successful and failed CLI completion. Rejection clears the ranking and both Search pointers, disables export, adds no B Explorer entry, and shows `Readback: invalid/unreadable` while independently retaining `Artifact digest: verified` and B's path. No exception escaped. |
| **FR-1 — saved Qt SVG caption/legend overflow** | **Pass.** Fresh historical mixed/Pareto and bounded normalized/long-label final SVGs were rendered with actual `QSvgRenderer`; all text groups remain inside the canvas. Their eight SVG/TIFF PNG previews were opened and inspected. Captions, normalizer, weighted-score explanation, Pareto reporting caveat and long legends are visible without clipping or label intrusion. Editable text, signed geometry, stored totals and TIFF policy remain intact. |

The rc=2 missing-medium run used the real audit model pool and a nonexistent medium; the invalid-pool run used an actual empty directory. Their output directories are `boundaries/cmig-search-rpjvw9jk` and `boundaries/cmig-search-autx983_`. A is an independently written valid summary with a production artifact digest. The failures are real CLI executions, not mocked return codes. Detailed before/after state, error, executed request and paths are in [boundary-results.json](../.run/remediation-20260925/gui-figures-acceptance/boundary-results.json).

The validator runs before `SearchView.load_summary` mutates state and is applied by direct and completed-job paths. The additional direct cases cover malformed weighted score, growth, both FVA bounds, a nested target-flux value, a nonobject flux map, boolean score, NaN flux, infinite score and invalid numeric text; two also exercise grouped rankings. Null numeric fields, absent fields, genuine zero, finite legacy scalar numeric strings and FVA ranges remain accepted in both flat and grouped schemas. Four distinct valid rows per schema retain unknown/zero/range distinctions. See [search-schema-results.json](../.run/remediation-20260925/gui-figures-acceptance/search-schema-results.json). The six completed-job cases use a controlled CLI writer/return value but the real GUI submission, JobRunner, digest and publication path.

**Prior GUI corrections and original contracts**

| Scope | Fresh verification and limits |
| --- | --- |
| **GR-1 / Host null and range interface** | The current two-fuel Host solve/objective-fixed FVA and `_write_host_microbe_bigg_outputs` produce objective 5, blank uptake points in CSV and sparse JSON point maps, with ac/but ranges `[0,5]`. Both actual CSV and JSON-only readback show `unknown [0.0, 5.0]`; no uptake/transfer edge is invented. Explicit-null, identified-zero and ambiguity-only variants also load correctly. Four current range screenshots retain the rows and ambiguity tooltips. This is actual current writer output, not a copied old summary. |
| **GR-2 / F6/F10 guarded readback** | All 20 original nested cases now reject, versus three false acceptances in the preceding review. Host failures retain the complete old Host payload, tables, pointers, viability and integrity detail with an explicit failed-load message; Search/dynamics failures use coherent clearing. The 48-case prior integrity/loader matrix reruns with zero escaped exceptions and retains verified/mismatch/not-recorded distinctions. Malformed/null/list manifests and missing essential data do not become verified scientific views. Failed Search with a null manifest publishes no pointer or Explorer entry. |
| **GR-3 / F3 applicable frozen requests** | All 12 completed-view applicability cases pass. Independent blocked-queue runs still execute the original exact medium in Gene KO, Growth and Ratio; KO retains `min_uptake` and growth fraction `0.7`, Growth/Ratio retain cooperative fraction `0.6`, and Growth retains `--single-medium community`. Applicable edits invalidate; irrelevant edits preserve a superseded Ratio result. This queue probe records argv; the focused suite separately exercises the actual exact-medium parser/context boundary. The earlier defined-medium scientific control is not newly rerun or recertified here. |
| **GR-4 / F8 scientific context** | All five direct/adapted routes preserve distinctive semantics, metric, directions, weights, normalization ranges and GA metadata, two warnings and partial-attempt fields. The complete selectable recorded JSON equals the supplied source. Historical Pareto details omit none of the present checked fields. Synthetic attempt totals test preservation only; SC-05 owns scientific ledger/count acceptance. |
| **GR-5 / F5 actionable failed Search** | The real rc=2 causes remain in both job error and selectable details. A fresh real GUI/CLI Search with minimum member growth 100 returns rc=3: failed job/summary, two baseline-failed candidates, no ranking, one Explorer entry and independently verified artifacts. Reopening preserves accessible diagnostics; detail scrolling reaches its end. Cancellation and completion-after-artifacts behavior pass the focused regressions. |
| **F4 layout/navigation** | All 12 EN/KO × empty Search/loaded Pareto/loaded Host × 1280×800/1500×950 captures match requested dimensions, have zero horizontal overflow, and expose all measured essential widget centers through scrolling. Four actual-writer range captures also match requested sizes. The selectable detail editor is reachable by Tab. |
| **F7 figure identity** | All four missing/unreadable checks clear the previous Search preview, show a specific placeholder and disable export. Fresh multi-target export offers only the existing Ranking artifact; no Scatter is invented. |
| **F9 GUI aspect** | Wide 400×100 SVG content renders at 740×184 pixels (ratio 4.021739; raster rounding), and tall 100×400 at 80×320 (ratio 0.25). Both PNGs were opened. |

The original prior-reviewed GUI scopes are accepted with these boundaries, and the new checks close the former F6/F10 incompleteness. Source inspection confirms the failed dictionary-result branch now inspects B unconditionally, including rc=2 without a manifest. Digest verification remains distinct from schema acceptance and scientific success.

**Actual final-file figure evidence**

The independent rendering probe was copied from the preceding independent review and restricted to the four assigned cases. It invokes the current production writer, checks signed Matplotlib geometry against stored input values, then independently renders the saved SVG bytes through Qt. Paired TIFF PNGs come from the actual final TIFF files. A separate final-file script associates SVG text with Qt bounds and checks caption, member-label and legend separation.

| Fresh pair | Minimum Qt text/canvas margin | Editable SVG text elements | Stored marker totals |
| --- | ---: | ---: | --- |
| Historical mixed | 10.211531 pt | 18 | 3.358851988170386, twice |
| Historical Pareto | 10.211531 pt | 19 | 13.358851988170386, twice |
| Weighted normalized | 10.211531 pt | 19 | 2, 2 |
| Five-row bounded long labels | 12.947531 pt | 44 | 11, 10, 9, 8, 7 |

The long-label case has a 7.104687 pt member/plot gap, 5.684646 pt minimum member-row gap, 37.118880 pt legend/plot gap and 2.683906 pt legend-row gap. Caption/axis gaps are at least 19.247547 pt across the four cases. Each TIFF is **RGB, 600×600 dpi, LZW (compression tag 5)**. All four SVGs emit a single resolved `Arial` family and native `<text>` elements. The source selects one installed family from the existing fallback stack inside the multi-target figure's local rc context; it retains the shared editable-text and deterministic export policy.

Fresh signed geometry still draws the historical mixed `−10/+13.358851988170386` terms from independent zero-side bases and marks their stored sum. The normalized example retains pre-weight values `−2/+4`, applies recorded weights `3/2` once, draws `−6/+8` and marks 2; the second row draws `1.5/+0.5`. Inputs, target/member order and six-significant-digit annotations remain unchanged. The focused figure regressions also pass positive, negative, zero and malformed-data checks. This follow-up does not claim to have regenerated all ten older figure-review cases or rerun its 22-case rejection matrix.

The historical Pareto file includes an explicitly stored zero and old missing-target diagnostics. It remains an immutable visual compatibility fixture, not evidence approving current missing-target science. Four long warnings remain in the fixture source; the saved figure's contracted caption/units/caveats are verified, without a claim that all summary warnings are printed inside the figure.

Visual evidence: [Pareto SVG](../.run/remediation-20260925/gui-figures-acceptance/historical-pareto-svg.png), [paired TIFF](../.run/remediation-20260925/gui-figures-acceptance/historical-pareto-tiff.png), [normalized SVG](../.run/remediation-20260925/gui-figures-acceptance/weighted-normalized-svg.png), [long-label SVG](../.run/remediation-20260925/gui-figures-acceptance/bounded-long-labels-svg.png), [long-label TIFF](../.run/remediation-20260925/gui-figures-acceptance/bounded-long-labels-tiff.png), [mixed SVG](../.run/remediation-20260925/gui-figures-acceptance/historical-mixed-svg.png). Full numerical/file measurements are in `measurements.json` and `final-file-check.json` alongside these files.

A fresh verified reviewer bundle places the corrected Pareto pair under the real `search_plot.svg`/`search_plot.tiff` names. Actual `load_search_dir` and `_export_search_figure` select Ranking, render the corrected preview and export **byte-identical editable SVG**. Only the save-dialog answer is emulated. [Export evidence](../.run/remediation-20260925/gui-figures-acceptance/export-results.json) and [visible preview](../.run/remediation-20260925/gui-figures-acceptance/export-pareto-preview-1500x950.png) preserve this contract.

**Exact executions**

All following commands exited **0**. GUI processes used `QT_QPA_PLATFORM=offscreen` and `QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox'`; standalone probes used `PYTHONPATH=.`. No environment sync/install was performed.

```sh
QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' uv run --no-sync pytest -o addopts='' -q tests/test_gui_audit_regressions.py tests/test_app_shell.py tests/test_gui_round5_p2.py tests/test_gui_views.py tests/test_host_view.py tests/test_jobrunner.py tests/test_gui_editors_builder.py tests/test_remediation_figures.py tests/test_figure_publication_export.py --junitxml=.run/remediation-20260925/gui-figures-acceptance/focused-tests.xml
```

**187 passed, 0 failed, 0 skipped, 16.89 s.** Counts by file, from JUnit: GUI audit 43; app shell 38; GUI round5 P2 32; views 8; Host view 6; JobRunner 9; builder/editors 10; remediation figures 15; publication export 26. The GUI six-file group contributes 136, builder 10 and figure/export 41. See `focused-tests.log` and `focused-tests.xml`.

Each script below was executed as `uv run --no-sync python .run/remediation-20260925/gui-figures-acceptance/<script>`, with the stated Qt/PYTHONPATH settings and a same-name log (the final-file verifier uses `final-file-check.log`).

| Script | Exact outcome |
| --- | --- |
| `probe_loaders.py` | 48 loader/integrity variants, no escaped exceptions; actual current Host solve/FVA/writer plus JSON-only readback and historical Pareto details. |
| `probe_boundaries.py` | 20/20 malformed cases rejected; 5/5 Host variants loaded; 12/12 applicability checks; 5/5 complete-source routes; 2/2 real rc=2 failures following verified A. |
| `probe_search_schema.py` | 10/10 additional malformed direct cases and 6/6 malformed completion cases coherently rejected; 2/2 valid flat/grouped schemas accepted. All assertions pass. |
| `probe_behavior_visual.py` | Three frozen queued workflows; real rc=3 Search; 12 geometry captures; 2 pixel-aspect checks; 4 missing/unreadable preview checks. |
| `probe_edges.py` | Additional real missing-medium failure; emulated failed/null-manifest completion rejected; actual diagnostic scrolling and Tab focus. |
| `capture_ranges.py` | Four EN/KO actual-writer range screenshots and exact geometry/tooltips. |
| `probe_figures.py` | Four fresh SVG/TIFF pairs with signed geometry, stored totals, unchanged inputs, real Qt-rendered SVG PNGs and actual TIFF previews. |
| `verify_final_files.py` | 4/4 final-file containment/spacing/editability/TIFF assertions pass. |
| `probe_export.py` | Actual GUI load/export; Ranking-only choice and byte-identical editable SVG. |

`acceptance-checks.json` also records independent assertions over the raw probe results, and `execution-outcomes.json` records exits. Matrix counts describe cases with their recorded expected outcomes; legacy and mismatch loads are not falsely counted as universally valid scientific results. No global pytest, Ruff/mypy/release/envelope rerun, unrelated docs audit or broader scientific audit was duplicated.

**Source identity and practical limits**

HEAD is `0167529fa9ba81649b138c476c524dc4495d4954`, branch `main`, with pre-existing remediation edits. `source-start.json` and `source-end.json` record **16 files and selected function hashes, unchanged across this review**. `source-identity.json` additionally records figure helper hashes; `artifact-sha256.json` identifies produced image artifacts. Key SHA-256 values:

| Source | SHA-256 |
| --- | --- |
| `cmig/gui/app.py` | `245fc8fc1c27af32389351c88c6121250a3448ad04550e7873e67e2df6cfe365` |
| `cmig/gui/builder.py` | `5a2d3b7eedc51bfdcda10060014bffaf626d2ccfef715a22c51eb12e7afd6aab` |
| `cmig/gui/host_view.py` | `28049f69d2fca836496cfe92a291ed25013a6a23b2ea97f64cc45735028dffab` |
| `cmig/cli/main.py` | `69a8997eee99f11b61de91370352a57f819d78e6e3b243866e8cf5c8f6e49635` |
| `_write_multi_target_figure` (`inspect.getsource`) | `b5203c28d98a549f53b3da7423805575afd6dbb4bcc39158df6eb2c573ba220a` |
| `cmig/render/figure_style.py` | `20a692d47a0cd12552e094c0b5b1621b1b573d0ea31c6ff85a3f755031305c90` |
| `cmig/io/atomic.py` | `f3149a3755ea6ce42c71c30f4c1bf11b65ccae12843742687bd7f67e38215d8f` |

Execution was on **macOS 15.6 arm64, Python 3.12.11, Matplotlib 3.10.9, Qt/PySide6 6.11.1, Pillow 12.2.0**, resolving `/System/Library/Fonts/Supplemental/Arial.ttf`. Actual Qt SVG rendering and actual solver/CLI/writer calls ran locally, but windows used the **offscreen** platform; this is not native macOS window-manager, Windows/Linux, HiDPI, browser, or full accessibility acceptance. No new biological/publication-validity conclusion follows from these probes.

Opened all eight final figure PNGs, the fresh exported-Pareto GUI preview, EN 1280/KO 1500 empty Search/Pareto/Host captures, EN 1280/KO 1500 actual-writer range captures, real failed-Search and reopened scrolled-detail captures, and both pixel-aspect PNGs. Narrow Host graph-filter labels/table headers still elide at 1280 as previously documented; required content remains reachable. Some offscreen WebEngine Host canvases are blank, so table/payload checks do not certify native graph rendering. The generic JobRunner envelope still labels `ArtifactJobFailure` as `solver_error`, while preserving the exact rc=2 input cause; this pre-existing diagnostic-classification limitation is not a new scientific success or solver-execution claim.

SC-01/03/04/05 scientific decisions, including collapsed-zero classification, boundary signs/duplicate uptake policy and truthful per-LP attempt/cancellation ledgers, remain in the separate scientific acceptance scope. The current Host nullable/range interface is compatible in the cases actually reproduced here. Final overall acceptance may cite this report while the relevant source remains unchanged; later changes to GUI publication/schema handling, the figure writer, fonts or export helpers require the affected focused boundary to be rechecked.
