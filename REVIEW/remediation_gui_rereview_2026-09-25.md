# Independent GUI correction re-review — 2026-09-25

Reviewer: GPT-6 Astra; task `task_738e9aeeaef7`, dispatch `ctx_6ecfb73b2377`. **Disposition: request changes for two remaining GR-2/F6/F10 boundary gaps.** GR-1, GR-3, GR-4 and the actionable-error part of GR-5 pass independent reproduction. The original GR-2 examples are corrected, but the complete guarded-readback contract is not yet met. No new escaping exception was observed.

Read `AGENTS.md`, `remediation_design_2026-09-25.md` (especially B1–B3), the complete first independent GUI review, the implementation/correction report, and affected GUI, JobRunner and scientific-writer code/tests. Only this report and ignored evidence under `.run/remediation-20260925/gui-rereview/` were authored. No production/test/documentation, Git, environment or credential edits were made; no global suite was run. Source start/end SHA-256 records show no change during these probes to the seven recorded GUI/service/CLI/test files. Concurrent scientific correction announced by the coordinator remains separately assigned and is not counted as a new GUI blocker.

## Remaining material findings

### GR-2a — P2: an input-failed Search inherits the previous run's verified integrity

**Source:** `cmig/gui/app.py:3031–3056`, failed Search completion. When no manifest exists and `cli_exit_code == 2`, this branch publishes the new summary, run/export pointer and Explorer entry without inspecting that directory or replacing the integrity state.

**Independent actual boundary:** Load a valid, digest-verified Search A, then use GUI controls and the real CLI to run B with either the audit model pool plus a missing medium, or an empty model pool. Both jobs fail with rc=2 and zero ranked rows. The newly corrected exact input cause is present in selectable details and `Job.error`, but both runs retain **`Integrity: verified`** and integrity detail `Run: …/boundaries/rc2-prior\nState: verified`, while the displayed Search directory advances to B:

- Missing medium: `boundaries/cmig-search-dota4mjj`.
- Empty pool: `boundaries/cmig-search-sl_dtqfm`.

The prior A summary is a reviewer-created valid fixture with a real production digest; both B invocations are real GUI → JobRunner → CLI failures, not mocked failures. Their output directories have no published manifest. This is mixed provenance between two runs, independently of the correctly displayed failed scientific status.

**Required correction:** Set the persistent integrity label/detail to the inspected state of B (including the shared inspector's no-digest reason), or an explicit diagnostic-only/no-published-run state tied to B, before publishing it. Do not certify B using A's digest. Regress good-A → real missing-medium/empty-pool B and assert the badge, detail path, displayed request, pointers, Explorer and scientific failure all refer consistently to B.

**Evidence:** `probe_boundaries.py`, `boundary-results.json` → `real_rc2_after_verified`, and `probe_boundaries.log`. Escalated immediately in `msg_0af2177f1586`.

### GR-2b — P2: malformed nested Search ranking data is still published as an ok, verified run

**Source:** `cmig/gui/app.py:1659–1669` validates the outer collection only; `cmig/gui/builder.py:942–947` silently drops nonobject items, and `_optional_float` at `:1011–1019` turns wrong-typed values into missing readouts.

**Independent direct-loader boundary:** Starting from valid A for each case, create B with a matching production artifact digest and call `load_search_dir(B)`. All three invalid summaries return `True`, advance both Search pointers, register B in Explorer, and display `ok Search run … integrity verified`:

| Invalid nested data | Published result |
| --- | --- |
| `top_ranked: [5]` | Empty ranking, no readback failure |
| One otherwise valid optimal row with `score: {}` | Optimal row with score `—`, flux `3`, growth `1` |
| One otherwise valid optimal row with `target_flux: {}` | Optimal row with score `3`, flux `—`, growth `1` |

This is not a request to reject legitimate absent or null values in legacy/nullable scientific schemas. An object where a numeric value belongs, or a nonobject ranking item, is malformed consumed data. Its checksum can verify its bytes but cannot validate its schema. The design explicitly requires rejection of wrong-typed consumed nested fields and an invalid/unreadable readback state without a scientific claim.

**Required correction:** Validate ranking row shapes and present consumed numeric fields before publishing any state, distinguishing nullable/absent values from wrong types. Apply the same publication policy to direct and completed-job Search results. Regress these three good-A → bad-B cases with valid digests, asserting either complete old-state retention with a failed-load message or complete clear/rejection with the independent digest verdict retained in detail.

**Evidence:** `boundary-results.json` → `nested_matrix`, cases `ranking-nonobject-item`, `ranking-dict-score`, `ranking-dict-flux`; matching directories under `boundaries/`. Included in the same immediate escalation. No exception escaped in these cases; the defect is false acceptance.

## Disposition of all first-review findings

| Finding | Independent disposition and proof |
| --- | --- |
| **GR-1** | **Pass.** Independently reran the current real two-fuel Host solve/FVA and `_write_host_microbe_bigg_outputs`. Objective remains 5; CSV contains `ac,,0,5,…` and `but,,0,5,…`; JSON point maps are sparse. The actual CSV route and a JSON-only copy both show ac and but as `unknown [0.0, 5.0]`, with objective visible and no invented uptake/transfer edge. Explicit JSON-null, identified-zero and ambiguity-only compatibility variants also pass. The zero variant displays `0`; ambiguous rows have the ambiguity tooltip. Current screenshots visibly show both range-only rows. |
| **GR-2** | **Original cases pass; overall incomplete.** Host `objective_value={}` and seven additional malformed Host point/range/ambiguity cases return false and retain the complete prior view, both Host pointers, payload, label and integrity detail with a failed-load path. Original Search outer-ranking, dFBA/spatial numeric-object failures clear the view and show `Readback: invalid/unreadable` while detail separately says `Artifact digest: verified`. A missing essential tidy `nodes.parquet` is a readback failure. Failed Search with `manifest.json=null` publishes neither pointer nor Explorer entry. The two remaining gaps above prevent closure. |
| **GR-3** | **Pass.** All **12/12** independent completed-view signal cases behaved correctly: Ratio and Growth retain results for Search direction/target-growth edits; main Search retains results for cooperative-fraction edits; medium changes and applicable fraction/direction changes clear results. Independent blocked-queue execution of Gene KO, Growth and Ratio still uses the original exact medium, Gene KO direction `min_uptake`/growth fraction `0.7`, and Growth/Ratio cooperative fraction `0.6` with Growth `--single-medium community`. After queued controls change, superseded/effective conditions remain visible; a subsequent irrelevant Ratio direction edit retains its result. CLI in this queue probe is an argv recorder; the real parser/exact-medium boundary is independently exercised by the focused suite. |
| **GR-4** | **Pass.** The historical Pareto summary's present semantics, metric, directions, weights, normalization ranges and GA metadata are now accessible. Distinctive non-null values survive **5/5** direct/adapted detail routes: direct, Host Search, Gene KO, Strain Growth and Ratio. In each route the selectable recorded JSON exactly equals the supplied complete source, including both warnings and partial-attempt counts. Adapter probes use controlled summaries, not newly solved GA/Pareto runs. Historical partial counts are explicitly synthetic compatibility/layout overlays. |
| **GR-5** | **Pass for the requested actionable-error correction.** Independently reran real missing-medium and empty-pool CLI failures through GUI completion. Both retain the specific path/cause in job error and selectable details, with failed status and zero ranking rows. The missing-medium probe uses the real audit pool. The existing generic JobRunner envelope code remains `solver_error` around `ArtifactJobFailure`, but now contains the exact input failure; this is a remaining diagnostic-classification limitation, not evidence of solver execution or scientific success. Integrity after a prior run is the separate GR-2a blocker above. |

## F3–F10 regression disposition

| Original finding | Current GUI disposition |
| --- | --- |
| F3, applicable frozen requests | **Pass for reviewed behavior.** Queue recorder, 12 edit cases and focused parser/context tests pass. The prior author's defined-medium scientific control was not rerun in this correction re-review; no new solver-level claim is inferred from the argv recorder. |
| F4, window fit/navigation | **Pass within offscreen scope.** All **12/12** fresh EN/KO empty Search, loaded Pareto and loaded Host matrix captures fit exactly 1280×800 or 1500×950, have zero horizontal overflow, and all recorded essential widget centers are reachable through their scroll area. Four additional actual-writer range captures and two real-failed-Search captures also match requested pixel dimensions. |
| F5, failed Search diagnostics | **Pass for rc=3/rc=2 diagnostic retention and scientific failure.** A fresh real GUI/CLI/Gurobi Search with minimum member growth 100 creates `cmig-search-9s826425`: failed job/summary, two baseline-failed candidates, zero rankings, one Explorer entry and separately verified artifacts. Reopening preserves diagnostics; the detail scroll reaches its end. Cancellation/completion-after-artifact regressions pass. GR-2a concerns the distinct integrity state on artifact-less rc=2. |
| F6, integrity | **Incomplete: GR-2a/GR-2b.** Original valid/changed/missing-recorded/legacy states still distinguish verified, mismatch and not_recorded through direct routes. Malformed-manifest and original malformed-summary handling pass. New boundaries demonstrate that digest and readback state can still disagree with the displayed run. |
| F7, stale Search preview | **Pass.** Independently remove Scatter after choosing a valid Ranking and replace Ranking with unreadable SVG; both wide and tall probes clear to a specific placeholder and disable export. Existing supported-artifact selection behavior remains covered. This is the audited Search selector scope, not certification of every Host static-figure mode. |
| F8, warnings and scientific context | **Pass for reviewed valid summaries.** Every historical Pareto warning, unit/normalizer, candidate/attempt/sampling field and recorded semantics remains selectable. Complete source JSON supplies adapted details. Actual Host range-only rows remain visible. |
| F9, GUI SVG aspect | **Pass.** Wide 400×100 SVG draws **740×184** red pixels, ratio **4.021739** versus 4; tall 100×400 draws **80×320**, ratio **0.25** versus 0.25. Both were visually opened. Saved output F9 and F2 remain exclusively with the figure/final reviewer. |
| F10, guarded publication | **Incomplete: GR-2a/GR-2b.** The former Host numeric exception and failed-Search null-manifest publication are fixed. No escaping exception occurs across the independent original and extended direct-loader probes, but silent malformed-Search acceptance still violates the contract. |

No regression was found in the previously accepted F3–F10 behaviors tested here. That statement does not close the newly demonstrated remaining F6/F10 gaps or accept F2/saved-output F9.

## Fresh execution and evidence limits

All command logs, fixtures, scripts, source hashes and PNGs are under `.run/remediation-20260925/gui-rereview/`. Commands used `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox'`, `uv run --no-sync`; standalone probes additionally used `PYTHONPATH=.`.

| Execution | Exact outcome |
| --- | --- |
| `pytest -q tests/test_gui_audit_regressions.py tests/test_app_shell.py tests/test_gui_round5_p2.py tests/test_gui_views.py tests/test_host_view.py tests/test_jobrunner.py` | **122 passed, 0 failed, 0 skipped, exit 0.** Repository quiet options suppress the footer; the log has 122 passing progress dots. Includes the author's 14 added correction cases, nullable Host Search adapter, cancellation and large-digest Qt timer responsiveness. |
| `probe_loaders.py` | Exit 0; **48** original matrix variants across four workflow loaders and tidy, **zero escaped exceptions**, plus the fresh real Host FVA/writer and historical Pareto-detail readback. Matrix entries retain actual verdicts; this is not a claim of 48 universally valid loads. |
| `probe_behavior_visual.py` | Exit 0; three frozen queued adjacent workflows, fresh real rc=3 Search, 12 geometry matrix captures and two measured SVG aspects, with four absent/unreadable-selection checks. |
| `probe_edges.py` | Exit 0; real rc=2 missing medium, emulated invalid-manifest failed completion, actual detail-scroll and Tab-focus checks. Failed invalid-manifest completion has **0** Explorer entries and no run pointer. |
| `probe_boundaries.py` | Exit 0; **20** deliberately malformed nested summaries, **17 rejected / 3 falsely accepted / 0 escaped exceptions**; five Host schema variants; **12/12** applicability cases; **5/5** complete-source condition routes; two real rc=2 failures following a verified run. Probe exit success means the evidence was collected, not that every application behavior passed. |
| `capture_ranges.py` | Exit 0; four actual-writer range captures at both sizes/languages, recorded row text and ambiguity tooltips. |

The three original independent scripts were copied unchanged into this review's directory and rerun against current source; original evidence was not overwritten. New probes extend their boundaries. Source fingerprints and process exits are recorded in `source-{start,end}-sha256.json` and `execution-outcomes.json`.

Visually opened all eight current loaded Pareto/Host EN/KO matrix images at both sizes, actual-writer EN 1280/KO 1500 range images, reopened real failed-Search detail image, and both SVG pixel probes. Narrow Host graph-filter labels and table headers still elide at 1280, as in the first review; scrolling exposes required result content. The offscreen WebEngine canvas is blank in some images while graph payload/table data are present, so no native-canvas rendering conclusion follows. Tab reaches the visible selectable details editor; this is a narrow focus check, not full accessibility certification. No native macOS/Windows/HiDPI, whole-suite, release/envelope, or publication-validity claim is made.

The coordinator's pending science correction may change truthful attempt totals; the synthetic 16/1/15 examples here test preservation/display only and do not certify those totals as the final scientific policy. Two GR-2 corrections and focused independent verification remain before GUI acceptance. This bounded review is complete and does not wait for fixes.
