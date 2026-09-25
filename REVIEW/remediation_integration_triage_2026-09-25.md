# Integration failure triage — 2026-09-25

Reviewer: GPT-6 Astra. Task `task_06435567d33f`, dispatch `ctx_bdf91c1137c4`. **All 10 reported failures are stale or scientifically incomplete fixtures/private-call adaptations; none of these 10 demonstrates a production regression requiring constraint relaxation.** This is bounded integration triage, not approval of the entire product. The separately accepted production residuals **RR1/RR2** and guide corrections remain with the concurrent Sol worker.

Read `AGENTS.md`, `REVIEW/remediation_design_2026-09-25.md` (especially A1/A2), `REVIEW/remediation_scientific_rereview_2026-09-25.md`, the root specification's MICOM/sign/namespace contracts, all 10 failures in `.run/remediation-20260925/integration/full-summary.json` and `full-tests.log`, their original tests/helpers, and the affected current engine, exchange, medium, host-impact, HostArm and CLI output paths. The root suite remains **1,764 collected / 1,736 passed / 10 failed / 18 skipped**. This review did not rerun or amend that suite.

Owned writes: this report and ignored `.run/remediation-20260925/integration-triage/` only. No production source, test source, shared environment, source GEM, Git commit or push was changed by this worker. Other workers have concurrent edits; this is not a claim that the shared working tree stayed unchanged globally.

## Executed evidence

`uv run --no-sync python .run/remediation-20260925/integration-triage/probe.py` exited **0**, with **10/10 scenario checks passing** against the current production code. The probe imports the original test modules and changes fixture objects only in that process. Eight checks invoke the original test functions and assertions; the private readout and stereochemical checks directly execute the same purpose/assertions with explicit missing inputs. This is a fixture-correction proof, **not 10 newly passing committed pytest tests** or real scientific solver validation.

Evidence: `probe.py`, `probe.log`, `probe-results.json`, an identified-zero status bundle and two actual host-search CLI artifact bundles under that ignored directory. The host coupling and MICOM tradeoff are intentionally stubbed, as in the original tests; host-search still reads actual generated SBML and exercises the real ranking/writer/figure path. The probe also verifies that removing the explicit butyrate zero interval leaves its unused amount and transfer range unavailable.

Findings were sent promptly to root in `msg_f2a918e4d646` and the successful bounded probe in `msg_b9360fffdd88`. No correction is requested in the concurrently owned RR1/RR2 production paths by this report.

## Per-failure correction contract

Paths in the table are under `tests/`. Preserve each original assertion and purpose unless an assertion is explicitly about the invalid old absence-as-zero inference; provide the missing evidence instead of weakening the expected behavior.

| # | Failed node | Classification and cause | Precise Sol edit and validation |
| --- | --- | --- | --- |
| 1 | `test_round5_domain_accuracy.py::test_apply_search_medium_helper_applies_what_it_can` | Invalid topology fixture. `_model` constructs metabolite `ac_m` with compartment **e**. `exchange_identity` correctly refuses to strip a compartment the metabolite does not have. | Repair the fixture builder to declare **m** for these pool metabolites, retaining **e** for member metabolites. Prefer an explicit fixture compartment argument or an intentionally limited e/m fixture suffix mapping. Keep uptake `7`, absent `EX_notreal_m`, note contents, exact notes set, and lower bound `−7` assertions unchanged. |
| 2 | `test_round5_domain_accuracy.py::test_search_is_silent_when_the_whole_medium_was_applied` | Same invalid `ac_m`/e fixture; no evidence of a warning suppression regression. | Use the repaired pool topology. Keep strict application, return `None`, and empty notes assertions; additionally retaining/asserting the applied bound `−7` makes the silent-success control concrete. |
| 3 | `test_round5_domain_accuracy.py::test_search_surfaces_medium_exchanges_it_could_not_apply` | Same invalid topology in `_StubEngine.build_community`. It fails before medium translation finishes, so there is no dropped-medium warning to forward. | Reuse the repaired builder. Keep the **real `search_model_pool` entry point**, both the run warning containing `EX_notreal_m` and the candidate diagnostic assertion. Do not replace this with a helper-only test: its documented mutation target is the run-level warning propagation. Its minimal community may later be unevaluable for another reason; the test deliberately accepts ranks plus unevaluated rows and must still retain the applied-medium diagnostic. |
| 4 | `test_round5_domain_accuracy.py::test_pfba_fallback_is_not_reported_as_pfba` | Stale private API call: `_solve_result_from_solution` now requires keyword-only `community` to derive identity from topology. | Pass a consistent empty community (`exchanges=[]`, `reactions=[]`, `boundary=[]`) alongside the existing empty solution, or a shared valid nonempty topology fixture. Keep full pFBA versus `fba_non_parsimonious` and `NON-parsimonious` label assertions. Do **not** make `community` optional or restore reaction-name parsing. |
| 5 | `test_engine_solver_guard.py::test_pfba_success_keeps_pfba_provenance_and_no_warning` | Incomplete readout double. Tradeoff returns its fake solution successfully, but `_StubCommunity` has no `.exchanges`, `.reactions` or `.boundary`; conversion correctly returns structured `solver_failed`. | Add the minimal topology/metadata described below, matched to the fake flux frame. Keep calls `[True]`, optimal, `pfba`, no warnings and no diagnostic. Add/retain a numerical flux check so a topology omission cannot be hidden by an empty result. |
| 6 | `test_engine_solver_guard.py::test_pfba_failure_retries_without_pfba_and_warns` | Same incomplete double; the expected retry `[True, False]` already occurs. The failure is in converting its returned solution, not retry selection. | Same shared fixture correction. Preserve optimal objective `0.6`, `fba`, `PFBA_FALLBACK_WARNING`, structured solver-error cause and the text identifying the failed pFBA stage. Keep the both-stages-fail and readout-failure negative controls unchanged and passing. |
| 7 | `test_run_status_reporting.py::test_all_ok_stays_ok_and_writes_no_unevaluated_file` | Stale output-row schema: `_row` claims a numeric target transfer but omits its identifiability/range. The writer conservatively treats the missing state as unavailable and degrades the run. This is not proof of actual ambiguity. | In the **identified success fixture**, supply `target_identifiability="identified"` and `target_transfer_range=(0.0,0.0)` to substantiate the existing `target_transfer=0.0`. Keep `status="ok"`, zero failures, empty unevaluated list and no undeclared/created unevaluated file. Failed rows should remain failed with unavailable target evidence; do not blanket-tag all rows identified. Add/retain an objective-only ambiguous/unavailable row control that remains ranked for a finite objective but has null transfer and degraded summary. |
| 8 | `test_round10_review_fixes.py::test_host_impact_joins_stereo_metabolites_across_spellings` | Scientifically invalid zero inference in a secondary assertion. The `lac__D`↔`lac__d` join already works, but the fixture contains no butyrate uptake point or range, so it cannot prove that all `but=1` secretion is unused. | Add **`"but": (0.0,0.0)`** to `lumen_uptake_ranges`; keep the sparse point map containing only lactate. Preserve all original expected lactate transfer/range and `unused_secretion={"but":1.0}` assertions. Keep a separate missing-butyrate-evidence control: absent point and absent range must not fabricate a zero transfer or a numeric unused amount. Do not change the production sparse-absence branch to zero. |
| 9 | `test_round5_final_fixes.py::test_an_optimal_host_lp_is_still_ranked_ok` | Stale coupling double. `_bigg_result` uses `SimpleNamespace(microbe_to_host=...)`, missing the `HostImpact.microbe_to_host_ranges` readout now required by `arm_from_coupling`. Its old empty secretion/match maps also contradict the asserted positive acetate transfer. | Replace the impact with actual **`HostImpact`**. For the optimal case, use acetate point `1.2` and collapsed range `(1.2,1.2)`, with consistent microbial availability and a matched exchange; preserve the legitimate optimal objective `0.0` control. For the failed case, keep no measured point/range and the actual failure statuses. Keep ranked row `ok`, summary/manifest `ok`, exit `0`; validate adjacent failed-LP tests still publish no ranked number and exit `3`. |
| 10 | `test_round5_final_fixes.py::test_the_host_search_figure_makes_no_such_claim_when_everything_evaluated` | Consequence of the same invalid coupling double: missing range raises, the real CLI excludes the candidate, and the figure correctly says it is not evaluable. No figure regression is demonstrated. | Reuse #9's typed coherent result fixture. Keep the assertion that the all-evaluated SVG has no `not evaluable` claim. Keep the opposite failed-case figure assertions (failure count and absence of evaluated-ok blue), plus artifact/manifest agreement tests. Do not hide the figure's failure caption or relabel unevaluable candidates. |

## Exact engine fixture topology

The solver-guard tests can remain delegation/readout unit tests without running MICOM or a licensed solver. Their fake flux matrix has member abundances `A=B=0.5`, `EX_ac_e` member fluxes `A=8`, `B=−5`, and a medium row. Supply real-shaped metadata:

- Shared pool metabolite `ac_m`, compartment `m`.
- Environmental reaction `EX_ac_m`, coefficient `−1` on `ac_m`, `global_id="EX_ac_m"`, `community_id="medium"`.
- Member reactions with unique IDs such as `EX_ac_e__A` and `EX_ac_e__B`, each `global_id="EX_ac_e"` and its correct `community_id`. Each has one member metabolite with coefficient `−1` and `ac_m` with coefficient **`+0.5`**, matching that member's abundance.
- `.exchanges=[environment]`, `.boundary=[environment]`, `.reactions=[environment, member A, member B]`. There are no hidden single-metabolite member suppliers in this stub; member↔pool transfers are not boundary suppliers.
- Correct the stub's medium flux from **3.0 to 1.5**: `0.5×8 + 0.5×(−5)=1.5`. This is a physically consistent fixture correction, not a golden expected-value update. Preserve member fluxes `8/−5`, abundances and objective `0.6`; ideally assert the weighted balance explicitly.

Minimal hashable metabolite/reaction doubles suffice; constructing a live community or solving a model is unnecessary. If preserving the file's stated no-MICOM dependency, scope a test-only pinned-version provider (`MicomEngine._load` returning an object with `__version__="0.39.0"`, for example) to these pure stub tests. Do not remove the production version check. The existing actual-MICOM golden tests validate the real dependency and adapter; a fake version is not evidence that an arbitrary MICOM version works. The executed probe used the installed pinned MICOM version and solver-free COBRA reaction objects.

The label-only private test can legitimately use empty topology because its solution contains no members or fluxes. The nonempty solver-guard tests **must not** use empty topology just to avoid conversion checks; that would silently discard the very flux result whose provenance they test.

## Validation and ownership for Sol/root

Sol's correction scope is the five test files named above. The corrections may share existing test helpers, but no production change is justified by these failures. Preserve all original tests rather than deleting, skipping, xfail-ing or weakening them. Preserve the new invalid-topology, ambiguous/unavailable host and exact-zero scientific regressions. The accepted A1 design explicitly instructs legacy fixtures to supply zero/range evidence rather than retain default-zero inference; A2 explicitly rejects unresolved compartment identity.

After the fixture edits, run the complete five files so their negative controls and neighboring callers are included:

```sh
uv run --no-sync pytest -o addopts='' -q -rs tests/test_round5_domain_accuracy.py tests/test_engine_solver_guard.py tests/test_run_status_reporting.py tests/test_round10_review_fixes.py tests/test_round5_final_fixes.py
```

Then validate the intersecting scientific contracts on the integrated tree, reusing a concurrently completed stable-tree run when it covers these same paths:

```sh
uv run --no-sync pytest -o addopts='' -q -rs tests/test_remediation_scientific.py tests/test_remediation_host_cli.py tests/test_host_ko_impact.py tests/test_engine_golden.py tests/test_sign.py tests/test_namespace_gate.py
uv run --no-sync ruff check .
uv run --no-sync mypy cmig
uv run --no-sync python scripts/check_release_versions.py
uv run --no-sync cmig golden verify-envelope
```

Root owns one stable-tree full-suite rerun and integration acceptance after fixture and RR1/RR2 corrections land. Preserve the 18 missing-human-GEM skips as limitations, not passes; preserve golden tolerances and pinned dependencies. The original scientific re-review remains the evidence for the broader real-LP/host/MICOM contracts, with its explicit publication and platform limitations. This report adds no publication-validity claim and does not certify RR1/RR2 as fixed.
