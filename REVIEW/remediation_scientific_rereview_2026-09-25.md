# Independent scientific correction re-review — 2026-09-25

Reviewer: GPT-6 Astra. Task `task_a0b7970bf156`, dispatch `ctx_3fb3d6b2f199`. **Disposition: changes requested for two bounded residuals; R1/R2 community physics, R3 standalone publication and the mandatory R4 KO arithmetic now pass.** Review execution is complete. This is not final integration or publication acceptance.

Read `AGENTS.md`, the remediation design, the final first scientific review, the implementation report's R1–R5 correction section, relevant root-specification contracts, current source/tests, `docs/USAGE.md`, `docs/USER_GUIDE.md` and `docs/HARNESS.md`. Owned writes are this report and ignored `.run/remediation-20260925/science-rereview/` evidence. No production, test, other documentation, Git, shared environment or credential changes were made. Source hashes before/after cover all `cmig` Python files, remediation tests, both current guides, dependency metadata and lockfile: **no changes during this review**. Root owns stable-tree global validation, acceptance and Git publication.

## Remaining findings

### RR1 — P2: frontier baseline exceptions still claim that no solve happened

`cmig/core/search_product.py:1444` calls the sampled-pass baseline without a local exception record. Its outer catch at `:1608` classifies an exception before the observer returns as `phase="setup"`, `solve_executed=false`, with empty policy fields.

Independent reproduction executes the real fourth COBRA/Gurobi optimization to `optimal`, then injects a failure while returning that result. Both direct and controlled searches record the first baseline and two capabilities correctly, but label the fourth, executed baseline as an unsolved setup error. The candidate remains failed and unranked, so this is residual **attempt provenance**, not a demonstrated false scientific optimum. Four completed real LP calls are observed; the final ledger row nevertheless asserts no solve occurred.

The returned exception is explicitly injected; this does not claim a naturally occurring Gurobi return-path failure. The general defect applies when baseline optimization raises before `on_solution`: source cannot distinguish setup from an attempted or completed solve, yet publishes `false`. Preserve a baseline-phase error at that boundary, its policy and an honest unknown execution/readout state when completion cannot be established; do not fabricate an optimal readout from this probe's external observer. Cancellation must continue to propagate.

Evidence: `probe_followup.py`, `followup.json` keys `frontier_baseline_exception_False/True`, `followup.log`. Escalated as `msg_b639910ad8c2`; coordinator accepted a bounded Sol correction in `msg_479c855ec340`. No corrective implementation is anticipated or certified here.

### RR2 — P2: the real host artifact/GUI path still calls an identified zero unknown

The required HostArm/KO correction works, but it has not reached all public readouts. A real host LP with acetate transport disabled and butyrate sustaining objective 5 produces acetate FVA **[0,0]**. `arm_from_coupling` now correctly reports acetate **identified**, target point **0**, while the same result passed through `_write_host_microbe_bigg_outputs` produces:

| Public field | Observed |
| --- | --- |
| `microbe_to_host.csv`, acetate `transfer_flux` | blank |
| CSV `minimum`, `maximum` | `0`, `0` |
| CSV `identifiable` | **False** |
| Saved JSON point map | acetate omitted; butyrate point 5 retained |
| Actual GUI reload, acetate transfer cell | **`unknown [0.0, 0.0]`** |
| GUI artifact integrity | **verified** |

The sparse positive-only map is legitimate as a transfer-edge representation, but its absence is still incorrectly used as the identifiability test in `cmig/cli/main.py:5203` and `cmig/gui/host_view.py:381`. Apply the finite collapsed-range rule consistently to the published point/identifiability and visible value, retaining null for noncollapsed or unavailable ranges. This does not require drawing zero-width network edges.

Minimal consistent correction contract: retain the producer's positive-only maps wherever they represent nonzero edges, but carry the solved finite range as independent measurement evidence. For an otherwise trustworthy, optimal readout, a finite ordered interval collapsed within the existing identification tolerance yields its identified point, including numeric zero; a noncollapsed interval takes precedence over any incidental solver point and yields an unknown point with its range, while unavailable/invalid readouts remain unavailable. The CSV writer must emit `transfer_flux=0` and `identifiable=True` for the real [0,0] case, and the GUI must show `0` with identified state through both live and saved-result paths without requiring an artificial zero entry in the sparse map. Preserve legacy explicit finite point assertions only when no contradictory ambiguous range is present, and do not create zero-valued network edges as a side effect. Regress the actual producer→writer→GUI [0,0] case alongside the existing real [0,5] null case and unavailable/FVA-failure case. Coordinator accepted this residual and requested this bounded cross-layer contract in `msg_55f233efca21`.

Evidence: real solver → real writer → real GUI reload in `probe_gui_zero.py`, `gui-real-zero.json/log`, and `gui-real-zero/`. The four selected GUI regression tests pass, but their identified-zero fixture manually inserts `{"ac": 0.0}` into the saved point map (`tests/test_gui_audit_regressions.py:502`); it therefore misses this actual producer path. The ambiguous sparse-range test is genuinely produced by the real writer and remains valid. Escalated immediately as `msg_c8c77f052761`.

### Documentation discrepancy

`docs/USAGE.md:193` and `docs/USER_GUIDE.md:539` still describe summary attempted/resolved/failed **slice** counts. They now include both baselines, each independent capability, and any minimization auxiliary, as well as slices: the ordinary two-target example is **20 total attempts, of which 16 are sampling slices**. Also, the guide's checkpoint warning describes histories *without* a ledger, whereas the actual incompatibility intentionally includes **v2 histories that already have a ledger**. Update that description to the affected evaluation-policy change. No documentation was edited by this reviewer.

The guide correctly distinguishes independent capability optima from a jointly achieved vector and explains conservative marginal host intervals. Its statement that a measured zero stays `0` agrees with the corrected KO path but is contradicted by RR2's public writer/GUI path.

## Revalidated corrections and preserved contracts

| Contract | Fresh result |
| --- | --- |
| **R1 / SC-03: reverse-unit member at zero cap** | Original real MICOM/Gurobi forward/reverse pair now leaves M0 biomass **0.1**, uptake **0** in both orientations; M1 remains supplied. No source GEM is modified. |
| **R2 / SC-04: shared duplicate-channel budget** | Original one-versus-two channel reproduction now gives the same M0 uptake **1.98019802** at Vmax 2. Focused real LP regressions cover mixed orientations, blocked primary with usable alternative, unequal initial biomasses and two steps, checking per-member budget and environment balance. Inspection verifies the nonnegative per-channel auxiliaries enforce gross uptake sum, rather than independent caps or a fixed split, after each abundance update. |
| **R3: standalone dFBA publication** | Both previously failing real CLI tests pass. An additional actual standalone CLI hidden-sink run publishes normally, with nonempty untracked uptake and **`model_biomass`** basis. `DfbaResult` now owns the relevant property; the writer no longer depends on a Community-only field. |
| **R4 / SC-01: identified zero and ambiguity** | Real host LP/FVA **[0,0] → [5,5]** identifies acetate in both arms and yields target and per-metabolite **+5**, with **[5,5]** marginal delta; reverse is −5. Structural zero and real JSON/CSV numeric zero/+5 pass. Real **[0,5]** remains null/blank, reverse bounds are [−5,0], two ambiguous arms give conservative [−5,5], and FVA failure stays unavailable. Real MICOM→host CLI objective-only ranking remains usable; transfer/weighted candidates remain unevaluable. RR2 limits public-field consistency. |
| **R5 / SC-05: normal attempt provenance** | Observer compares every actual `cobra.Model.optimize` result with its ledger row, including physical flux/sign readouts: default direct and controlled paths each have **20 calls / 20 rows**, **15 optimal / 5 actual infeasible**. Sequence includes 2 baselines, 2 independent capabilities and 16 slices. Mixed minimization has **21 calls / 21 rows**, **19 optimal / 2 infeasible**, including its relaxation solve. Both independent capability rows have scalar measured readouts and `achieved_vector=null`; measured capabilities are 15 and 40, whose combination violates `2a+b≤20`, while every achieved archive vector satisfies the bound. RR1 limits the exceptional baseline boundary. |
| **SC-05: partial/failure partitions** | Both paths retain a real feasible point through **15 injected timeout statuses**. Injected later exceptions, all timeouts, duplicates, minimization-auxiliary timeout and failed capability/resume regressions pass. Failed capabilities stay `failed`, are not double-counted in resumed ledgers and never produce a ranked point. Actual zero-growth nonviability retains its distinct outcome and marks skipped target solves `solve_executed=false`. A genuinely infeasible sampled-pass baseline is recorded as baseline/infeasible, not an ordinary setup error. |
| **SC-02: same-solution hidden uptake** | Independent nonunit internal sink/demand cases each observe exactly **one** integrated MICOM solve; recorded supply equals that solution's boundary readout (**10** in both fixtures), keyed by member with **`member_biomass`** basis. Closure prevents growth and leaves no hidden uptake. Forced supplier, explicit formula-X exemption and missing-formula controls pass in the focused tests. |
| **Other SC-03/04 contracts** | Real standalone/host coefficients −3, −0.5, +0.5, +3 preserve uptake, FVA and depletion; reverse/cross-zero conversion and bound restoration pass. Renamed glucose exchanges, 0.2/0.8 member weighting, tidy identity, medium translation, duplicate aggregation and explicit unsupported nonunit community-input rejection remain intact. Golden/sign/namespace regressions pass unchanged. |
| **SC-06/07/08** | Independent valid/tiny/zero/negative/nonfinite abundance and duplicate-member probes retain rejection semantics. Undefined effects stay null with diagnostics; volcano/FDR reject unavailable inputs; positive pooled-variance controls remain finite. Actual Gurobi/OSQP standalone LPs reach objective 10, actual QPs x≈1 and actual advertised Gurobi MILP x=1 under integer x≤1.5. Native HiGHS rejects because the adapter is absent despite package availability. These are actual local solves, not license conclusions inferred from a capability list. |

## Cancellation, archives and checkpoints

`probe_followup.py` injects `SearchCancelled` at capability baseline, capability target, sampled baseline, weighted solve and a later frontier solve in **both direct and controlled** paths; all propagate. Minimization-relaxation cancellation also propagates in both. These are deterministic cancellation-boundary injections, not a demonstrated mid-optimization solver interrupt.

Five further scenarios use **real spawned ProcessPoolExecutor workers and the actual service worker function**, with a reviewer initializer selecting the tiny COBRA engine and deterministic cancellation on the second candidate at each of those five phases. Each propagates `SearchCancelled` to the parent, retains the previously completed candidate's **7 feasible points and 20 attempts** in the checkpoint, omits a false completed record for the cancelled candidate, and resumes to the same ledger/states as uninterrupted execution. The focused suite separately verifies actual MICOM workers=1/2 equivalence. These cover completed candidate archives; no claim is made that unfinished in-candidate slices are checkpointed incrementally.

Checkpoint incompatibility was independently tested with the **full public service context**, including `solver_threads=1` and `solve_timeout=null`, so those settings cannot accidentally cause the expected rejection. With everything else identical: absent policy and `attempt_ledger_v2` both reject explicitly and preserve checkpoint bytes; `attempt_ledger_v3` accepts and completes 20 attempts. The marker is confined to Pareto configuration in `search_identity`, preserving unrelated single-target identity semantics. The envelope gate remains unchanged.

## Published summaries and digest evidence

The existing real CLI publication regressions were also invoked with retained output directories for inspection (these are repetitions of two tests, **not additional unique test counts**):

| Run | Science status | Attempts / resolved / failed | Unique candidates evaluated / ranked | Candidate state | Integrity |
| --- | --- | --- | --- | --- | --- |
| Real first slice + 15 injected timeouts | degraded | **20 / 5 / 15** | **1 / 1** | partial | verified |
| One injected capability timeout, other capability real optimal | failed | **3 / 2 / 1** | **1 / 0** | failed | verified |

The second run uses explicit `--allow-failed-run`: exit 0 permits artifact publication and does **not** mean scientific success. Its declared artifacts omit nonexistent plots, and digest verification reports no missing artifact. Modifying the retained first run's evaluation-ledger bytes makes inspection report **mismatch**, then restoring the original bytes restores the evidence. Attempt counts include recorded skipped/setup outcomes when present; resolved counts specifically count optimal/infeasible, and failed counts specifically count timeout/error, not a reclassification of nonviable as solver error. These counters should not be described as a universal binary partition of all outcome categories.

Evidence: `publication.json/log`, `publication-partial/`, `publication-failed_capability/`, `identity-controls/`, `standalone-cli/`.

## Commands and counts

All project execution used the already synchronized environment and `uv run --no-sync`. Exact probe sources, outputs and full invocation list are under the evidence directory (`commands.txt`). The bounded fresh pytest commands were:

```sh
uv run --no-sync pytest -o addopts='' -q -rs --junitxml=.run/remediation-20260925/science-rereview/focused.xml tests/test_remediation_scientific.py tests/test_remediation_host_cli.py tests/test_remediation_pareto.py tests/test_remediation_stats_solver.py tests/test_dfba.py tests/test_round8_community_dfba.py tests/test_round9_dfba_community_cli.py tests/test_host_ko_impact.py tests/test_host_medium_strictness.py tests/test_search_execution.py tests/test_search_service.py tests/test_search_policy_v2.py tests/test_engine_golden.py tests/test_sign.py tests/test_namespace_gate.py
uv run --no-sync pytest -o addopts='' -q -rs --junitxml=.run/remediation-20260925/science-rereview/gui-fields.xml tests/test_gui_audit_regressions.py::test_host_search_null_transfer_keeps_range_and_identifiability tests/test_gui_audit_regressions.py::test_real_host_writer_sparse_fva_ranges_round_trip tests/test_gui_audit_regressions.py::test_full_window_fits_with_long_warnings_and_hidden_host tests/test_gui_audit_regressions.py::test_search_nullable_numeric_readouts_remain_unknown
```

- Scientific focused run: **exit 0, 212 passed, 0 failed, 0 skipped**, 100.06 seconds; `focused.log/xml`.
- GUI public-field run: **exit 0, 4 passed, 0 failed, 0 skipped**, 6.98 seconds; `gui-fields.log/xml`. Total **216 distinct tests**, not a whole-suite pass.
- `uv run --no-sync python .run/remediation-20260925/science-rereview/probe_independent.py`: **8/8** scientific scenario groups pass; no IO rerun. `independent.json/log`.
- Same command form for `probe_gaps.py`, `probe_community_limits.py`, `probe_solve_count.py`: exit 0 and observed corrected original reproductions. `probe_solve_count.py` also executes relocated `probe_pareto.py`, covering both partial paths, resume and minimization auxiliary failure. Observer-script exit 0 alone is not product acceptance.
- Same command form for `probe_followup.py`: exit 0; **25 scenarios**, comprising 23 successful contract checks and two observations of RR1. `followup.json/log`.
- Same command form for `probe_gui_zero.py`: exit 0; real saved evidence reproduces **RR2**, not acceptance.
- Same command form for `probe_publication.py`: exit 0; artifact/digest, full-context checkpoint controls and standalone CLI basis checks pass.
- `uv run --no-sync ruff check cmig/core/dfba.py cmig/core/dfba_community.py cmig/core/host_ko_impact.py cmig/core/search.py cmig/core/search_product.py cmig/core/search_multi.py cmig/service/search_service.py`: exit 0, all checks pass.
- `uv run --no-sync python scripts/check_release_versions.py`: exit 0, six surfaces agree at **0.3.0**.
- `uv run --no-sync cmig golden verify-envelope`: exit 0, **18 workflow kinds** and float normalization unchanged.

Probe construction correction: the first spawned-worker preservation probe named the cancelled candidate lexicographically first, so it correctly cancelled before any completed checkpoint existed and the reviewer then tried to read a nonexistent checkpoint. Renaming the fixture candidates to `a_complete`/`z_cancel` tests the intended completed-first sequence. `followup-first-run.log` preserves the error; it was a reviewer fixture-order mistake, not a product failure. The final five worker scenarios pass. Original probes were relocated to this review's directory, with v3 expectation and IO invocation adjusted; prior review evidence was not overwritten.

## Bounded prior acceptance and limitations

The previously accepted absent-`os.fchmod` IO correction is unchanged: `cmig/io/atomic.py` SHA-256 remains **f3149a3755ea6ce42c71c30f4c1bf11b65ccae12843742687bd7f67e38215d8f**, matching `science-review/reviewed-source-sha256.json`. Reuse the first review's **84 passing IO tests and API-absence emulation acceptance**, rather than rebuild or claim new native-Windows validation. Those counts are prior evidence and are not added to the 216 fresh tests.

MICOM construction/tradeoff delegation and `micom==0.39.0` remain intact. The already flagged version/shape adapter dependency on MICOM pool/member metadata remains a bounded accepted contract tension with the root specification's public-API-only wording; the current guide acknowledges it. No golden tolerance, solver stack or source GEM was changed. Host objective, biomass denominators, growth-floor semantics, fixed normalization and budget units remain as scoped by the accepted design.

This review establishes tiny LP/MICOM software behavior and offscreen public-field readback, not biological efficacy or publication validity for full host/community GEMs. No full-suite rerun, global `mypy cmig` rerun, native Windows, remote CI, live AGORA publisher, human-GEM or GUI visual certification is claimed. Root's running global validation remains separate. The two residuals and documentation discrepancy require their owning corrections and bounded acceptance; do not interpret the passing focused tests as approval of the currently reproduced public-field/provenance errors.
