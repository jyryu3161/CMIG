# Independent GUI remediation review — 2026-09-25

Reviewer: GPT-6 Astra, dispatched task `task_915e97f233ff`. **Disposition: request changes.** The lane-B delivery fixes the principal layout, frozen-argument, failed-Search readback and SVG-preview defects, but does not yet satisfy the complete F3/F5/F6/F8/F10 acceptance contract. Five remaining issues are reproduced below; GR-1 is a material integration blocker.

Reviewed against `0167529fa9ba81649b138c476c524dc4495d4954`, still HEAD during this review. Read `AGENTS.md`, remediation design lane B, original UI audit F3–F10, GUI implementation report and the affected implementation/tests. Other lanes were editing the shared checkout; their uncommitted changes are not counted as GUI regressions. The reviewed GUI source hashes are recorded in `.run/remediation-20260925/gui-review/review-source-sha256.json`. Subsequent corrections require focused re-review. Only this new report and ignored reviewer evidence were written; no implementation, prior report, branch, index, commit or remote was changed.

## Disposition of F3–F10

| Finding | Independent verdict | Evidence and boundary |
| --- | --- | --- |
| F3 | **Partial: forwarding fixed; applicability still incomplete** | Independent blocked-queue recorder confirmed Gene KO executes the original medium plus `--exact-medium`, `min_uptake`, growth fraction `0.7`; Growth and Ratio execute original cooperative fraction `0.6`, exact medium, and no target-direction/growth flags. Growth pins `--single-medium community`. Applicable changes remain in the superseded note; inapplicable fields are excluded from request comparison. However, an inapplicable edit after completion clears a valid Ratio result: GR-3. |
| F4 | **Pass for required offscreen window fit and essential form navigation** | Twelve independent English/Korean empty Search, loaded Pareto and loaded Host captures all naturally fit exactly 1280×800 or 1500×950, with zero horizontal overflow. All probed form actions, details, table and figure centers were reachable through the real scroll area. New PNGs and implementation PNGs were visually opened. Remaining narrow table/header and Host graph-filter label clipping is described below; native/HiDPI usability is not certified. |
| F5 | **rc=3 fix passes; rc=2 cause preservation incomplete** | Fresh GUI→real CLI/Gurobi run with member growth floor 100 yielded failed Job, rc=3, failed summary, two `baseline_failed` candidates, zero ranked candidates, Explorer entry, selectable output path and both actual infeasibility reasons. Digest independently remains verified. Reopening retained diagnostics. Cancellation regressions pass. A real missing-medium rc=2 loses its specific cause and filename: GR-5. |
| F6 | **Partial** | The five direct routes use the existing CLI inspector and distinguish valid, changed/missing recorded artifacts and legacy no-digest runs in the successful-read cases. Manifest malformed/null/list cases are caught. The loader matrix identifies schema-invalid summaries that leave a verified badge, and failed-job completion can ignore failed preflight: GR-2. |
| F7 | **Pass for the audited Search figure selector** | Independent actual Qt probes load Ranking, remove Scatter before selecting it, and replace Ranking with unreadable SVG. Both cases clear the visible preview to a specific placeholder and disable export; no previous image remains. Choices come from supported existing files, and export selection uses the same artifact. This is not an acceptance claim about every historical Host static-figure mode. |
| F8 | **Partial** | All four historical Pareto warnings, units/normalizer, candidate counts, partial sampling map and 16/1/15 attempt counts are accessible in the selectable details panel. Missing legacy fields do not crash or acquire fabricated counts. Present scientific conditions/semantics are still omitted (GR-4), and the actual sparse Host uncertainty schema is not displayed (GR-1). |
| F9 | **GUI aspect fix passes** | Independent red-pixel measurements: wide viewBox 400×100 draws 740×184 (ratio 4.0217 versus 4); tall 100×400 draws 80×320 (0.25 versus 0.25). PNGs visibly letterbox correctly. Historical mixed/Pareto figures were inspected as preview-layout evidence only. Saved plot sign/clipping F2/F9 belongs to lane D and is not accepted by this report. |
| F10 | **Partial** | Original malformed-manifest escape is fixed, including null/list and malformed provenance probes. Several direct loaders clear or retain their prior views consistently on ordinary failures. Host objective conversion still escapes outside the guarded stage, and failed-Search publication bypasses failed preflight: GR-2. |

## Remaining issues

### GR-1 — P1: actual Host nullable/range output cannot be read back

**Paths:** `cmig/gui/app.py:1701`, `cmig/gui/host_view.py:381`, `cmig/gui/host_view.py:403`.

**Trigger and proof:** Execute the science lane's two-fuel toy `alternative_host()` through the real `solve_bigg_host`/FVA and production `_write_host_microbe_bigg_outputs` with controlled community metadata. The host objective is 5, and both ac and but uptake/transfer ranges are `[0,5]`. The scientific schema uses sparse point maps (`lumen_uptake={}`, `microbe_to_host={}`), ranges and `ambiguous_metabolites`, rather than fabricated point values. The production CSV writes `ac,,0,5,...` and `but,,0,5,...`.

`load_host_microbe_bigg_dir` returns false with `could not convert string to float: ''`. In a separate JSON-only copy, it returns true but shows **zero transfer rows**, despite both recorded ranges. `load_impact` only iterates point keys; `load_bigg_summary` can append ranges only to existing rows and expects a `metabolite_identifiability` map which this actual writer does not emit. The existing GUI regression's explicit `{"ac": null}` plus no uptake CSV does not exercise this contract.

**Expected correction/regression:** Parse blank uptake as unavailable, preserve its range, and populate transfer rows from the union of point/range/ambiguity keys. Display unknown `[0,5]`/ambiguous without creating a zero or point edge. Test actual writer output with CSV present, objective still shown, both uncertainty rows visible, plus identified/zero and legacy variants. Host Search's target-specific null/range adapter separately passes the existing focused regression; that does not cure the direct Host loader.

**Evidence:** `loader-results-v2.json` entries `real_host_writer` and `host_json_only`; `loaders-v2/host-writer-ambiguous/`; `host-ambiguous-json-only-1280x800.png`, all under the reviewer evidence directory.

### GR-2 — P2: guarded publication and schema state remain inconsistent

**Paths:** `cmig/gui/app.py:1733`, `:1603`, `:1765`, `:1811`, `:2933`; tidy unsupported-viewer dispatch at `:1540` is also implicated.

**Reproduced cases:**

- After a valid Host load, a replacement summary with `host.objective_value={}` passes the guarded validation and raises `TypeError` from the unguarded `float(...)` at line 1733. The prior Host data/export directory remains, but integrity detail has already advanced to the replacement run. This is a real exception escaping the Python loader boundary, not a claim that the native process always crashes.
- Search `top_ranked={"ac":"wrong"}` and dFBA/spatial `final_t={}` are rejected and their view cleared, but a matching recorded digest leaves **Integrity: verified** and no persistent invalid/unreadable readback state. Byte verification is correct; it is insufficient to label a rejected summary as a valid loaded run under the required GUI state contract.
- A failed Search with `manifest.json=null` still publishes summary, current run pointer and Explorer entry: `_poll_completed_jobs` ignores `_inspect_gui_run` returning `None` in its FAILED branch. The badge says invalid/unreadable while the view publishes the rejected run.
- A tidy run missing `nodes.parquet` is reported as an unsupported viewer instead of an essential-data failure; the shared inspector badge advances although the previous tidy view remains. The supported-kind decision must distinguish an incomplete tidy publication from a genuine unsupported workflow.

**Expected correction/regression:** Validate every consumed field and stage all view data before any publication. On failure either clear the whole view/provenance/export state or retain the complete old state with an explicit failed-load message; keep readback validity distinct from the unchanged shared digest verdict. Make failed-job completion honor preflight. Extend the good-A→bad-B matrix to malformed numeric/nested summary data, missing essential tidy files and a failed job with invalid manifest; assert no exception and consistent data, badge/detail, export pointer and Explorer state.

**Evidence:** `loader-results-v2.json` (`wrong-summary`, tidy `missing-recorded`) and `edge-results.json` (`failed_invalid_manifest`). The Host malformed-manifest cases that retain the complete prior view and prior integrity detail are an allowed retention policy, not additional bugs.

### GR-3 — P2: inapplicable controls invalidate a completed adjacent workflow

**Path:** `cmig/gui/builder.py:668` through the control signal connections and `invalidate_results` at `:781`.

**Trigger:** Complete Ratio Impact with the independently recorded frozen request. Change only Search direction. The run pointer becomes `None`, details disappear, and status says `Inputs changed — previous result cleared; re-run to update`, although direction is explicitly inapplicable to Ratio. The new cooperative fraction similarly connects unconditional invalidation despite being inapplicable to main Search. Workflow-specific `REQUEST_FIELDS` currently governs only superseded comparison.

**Expected correction/regression:** Retain the displayed workflow kind and its executed snapshot; invalidate only when an applicable answer-determining field changes. Test post-completion Ratio/Strain Growth under direction/target-growth edits, and main Search under cooperative-fraction edits, alongside genuine applicable edits. Preserve frozen execution and superseded annotations.

**Evidence:** `behavior-visual-results.json`, `requests.ratio_before_irrelevant_edit` and `ratio_after_irrelevant_edit`.

### GR-4 — P2: present scientific conditions and solution semantics remain inaccessible

**Path:** `cmig/gui/builder.py:882` and summary adapters.

**Trigger:** Load the actual historical Pareto summary with current partial-attempt fields added as an explicitly synthetic compatibility probe. All warnings/counts render, but `solution_semantics`, `metric`, `directions`, `weights`, `normalization_ranges` and `ga_metadata` present in that summary are omitted by the hard-coded detail-field list. No raw-summary view in this panel supplies them. A report-order warning alone does not replace the actual executed conditions.

**Expected correction/regression:** Expose the available effective request/conditions and scientific semantics in selectable details, or supply an accessible complete structured summary. Preserve absent legacy values as absent/unknown. Test distinctive values for each supported field and confirm they survive both direct loading and workflow adaptation, with all warnings and partial counts.

**Evidence:** `loader-results-v2.json`, `pareto_details.omitted_present_fields`; source summary `.run/audit-20260925/pareto/search_summary.json` was read without modification.

### GR-5 — P2: rc=2 readback discards an actionable specific input error

**Paths:** `cmig/gui/app.py:703` (`_failed_search_artifacts`) and `run_search_fixture` job boundary.

**Trigger:** A real Search with the valid audit pool and nonexistent `NONEXISTENT_review_medium.csv` returns rc=2. CLI reports `medium file not found` with the exact path, but GUI details and retained job diagnostic contain only the generic checklist/exit code/output directory; the missing filename is absent. The output directory is empty, so opening it cannot recover that cause. Job diagnostic additionally uses generic `solver_error` for this input failure.

**Expected correction/regression:** Preserve structured input diagnostics or perform bounded GUI/job-boundary validation for malformed/missing inputs and retain the specific path/cause. Do not add unsafe process-wide stderr redirection. Regress real missing-medium and invalid-pool cases through GUI completion, asserting the specific input cause is accessible and no scientific success/ranking is claimed.

**Evidence:** `edge-results.json`, `real_rc2`; the CLI's exact emitted cause remains in `probe_edges.log`.

## Independent execution and visual evidence

All reviewer evidence is in `.run/remediation-20260925/gui-review/`. Commands used `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox'`, `uv run --no-sync`; standalone probes additionally set `PYTHONPATH=.`.

- Focused suite: `pytest -q tests/test_gui_audit_regressions.py tests/test_app_shell.py tests/test_gui_round5_p2.py tests/test_gui_views.py tests/test_host_view.py tests/test_jobrunner.py` — **108 passed, zero failed/skipped, exit 0**. Includes real parser/context exact-medium boundary, nullable target-transfer adapter, cancellation, completion-after-artifact policy and large-inspection Qt timer responsiveness. Log: `focused-tests.log`.
- Independent request, real failed Search, window and SVG probes: `probe_behavior_visual.py`, exit 0; `behavior-visual-results.json` and log. Output `cmig-search-95mjk6da/` is the new rc=3 run, not the implementation author's failed fixture. Its two infeasibility diagnostics were visually inspected after scrolling in `review-failed-diagnostics-scrolled-1500x950.png`.
- Independent five-route integrity/readback matrix and real host FVA→writer→GUI integration: `probe_loaders.py`, clean exit 0; decisive `loader-results-v2.json` and `probe_loaders-v2.log`. The initial unguarded review script allowed multiprocessing re-entry; its first log/`loader-results.json` are **superseded review-harness evidence**, not application findings. The corrected script has a main guard, uses one FVA process, and fresh `loaders-v2/` fixtures. No audit fixture was overwritten.
- Edge probes: `probe_edges.py`, exit 0; `edge-results.json`. Actual Tab from cooperative-fraction input reached the visible details editor; its scrollbar reached the final diagnostics. This is a narrow offscreen focus/scroll check, not complete keyboard/accessibility certification.
- The implementation author's defined-medium control manifest was independently inspected: `exact_boundary_isolation`, seven named uptake metabolites, `tradeoff_f=0.65`, `single_medium_mode=community`, matching single/community medium and status ok. This solver control was **not independently rerun**; independent argument/parser tests establish forwarding, and the new actual solves in this review were rc=3 Search and host FVA.

Opened new PNGs directly with the image tool, including implementation-author English/Korean empty Search and Host at both sizes; both-language long-warning Pareto at both sizes; real failed Search; mixed and Pareto figure-scroll states. Also opened reviewer-produced English loaded Host at 1280, Korean loaded Host at 1500, English/Korean partial-Pareto states, both red SVG aspect probes and the scrolled actual failure diagnostics. Geometry assertions alone were not used as visual acceptance.

At 1280, Search's figure/table requires vertical scrolling but essential run/cancel/adjacent workflow controls remain accessible. Narrow table cells and Host graph-filter labels can still elide/truncate; at 1500 the main Host form and result table are usable. The WebEngine canvas is blank in some offscreen captures while payload/table data are available; no native rendering defect is inferred from that environment limitation. Search/Host content remains partially English in Korean mode, as already scoped; this review does not require a full translation.

The historical mixed saved plot still omits the negative contribution and Pareto's saved caption still clips. These are explicitly lane-D F2/saved-F9 evidence, not regressions caused by GUI aspect preservation, and are not accepted here. No native macOS, Windows, HiDPI, full-suite, global formatting, release/envelope or publication-validity claim is made by this bounded review.

Material findings were escalated to the coordinator as they were established. Completion of this review does not approve the GUI for integrated release; GR-1–GR-5 need Sol corrections and focused Astra re-review.
