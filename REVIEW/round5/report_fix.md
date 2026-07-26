# Track P3 (I/O, exception handling & logging, security) — FIXER report

Worktree `/Users/jaeyongryu/orca/CMIG-wt-io` @ `eec5a55` (clean at start).
All work is uncommitted. No path outside this worktree was written.
`import cmig` → `/Users/jaeyongryu/orca/CMIG-wt-io/cmig/__init__.py` (verified).

**Headline: the frozen 11-component `community_solve` run_hash `29844e29…cef29ab` did NOT
move.** Verified end-to-end through the real CLI, not just by unit test:

```
$ cmig solve-fixture --solver gurobi --out /tmp/cc4check
run_hash: 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab
FROZEN MATCH: True
```

Counts: **14 ACCEPT · 3 ACCEPT-MODIFIED · 3 REJECT · 6 DEFER.**

---

## 1. Triage table

Every finding from both reports. "Repro" = I personally reproduced it before touching code.

| ID | Sev | Finding | Verdict | Evidence |
|---|---|---|---|---|
| **CC-2** / opus F1 / codex F6 | P0 | abundance-impact fabricates `community_growth: 0.0` on a failed solve; figure filters on `target_abundance`, never `status` | **ACCEPT** | Repro'd: `main.py:2462` zeros + `:4949` filter; regression test failed before / passes after |
| **CC-2** / opus F2 / codex F5 | P0 | gene-KO `except` returns `score_delta = -baseline.score` (finite, ranked) | **ACCEPT** | Repro'd via `_evaluate_ko_target` with an injected `RuntimeError`: returned `-12.148`, finite |
| **CC-4** / codex F1 | P0 | 6-decimal canonicalization collides distinct answer-determining inputs | **ACCEPT-MODIFIED** | Repro'd: bounds `1e-7` vs `4e-7` → identical hash. Fixed backward-compatibly, **not** by `DEFAULT_FLOAT_DECIMALS = 17` (see §3) |
| codex F3 | P0 | `_biomass_reactions` swallows every exception → false "no objective reaction detected" | **ACCEPT** | Repro'd; also measured that `linear_reaction_coefficients` returns `{}` (does not raise) for a model with no objective, so the catch never served its stated purpose |
| codex F4 | P0 | `medium._is_blocked` treats *any* lookup error as "nutrient unavailable" | **ACCEPT** | Repro'd; measured that cobra's `get_by_id` raises `KeyError` for an absent id, so narrowing is exact |
| **CC-3** / opus F3 | P1 | stale `search_unevaluated.csv` survives into the next run | **ACCEPT** | Repro'd against the real writer; fixed by extracting and reusing the solve-path helper, as the coordinator directed |
| opus F4 / codex F8 (manifest part) | P1 | `write_workflow_manifest` truncates before writing; a failure destroys the previous manifest | **ACCEPT** | Repro'd by injecting at `os.fsync` and `os.replace` |
| **CC-1** / opus F12c / codex §5 | P2 | `test_render_client_passes_project_rlib` order-dependent **and** worktree-dependent | **ACCEPT** | Repro'd both modes; fixed both; now passes isolated *and* in full-suite order |
| (found while fixing CC-1) | P2 | `test_review_regressions.py::test_profile_render_passes_rlib_to_rscript` has the identical blanket-monkeypatch defect | **ACCEPT** | Not in either report. Fails in isolation with `TypeError: fake_run() got an unexpected keyword argument 'stdout'`. Same fix |
| opus F12a | P2 | `gene_ko_summary.json` hardcodes `"status": "ok"` | **ACCEPT** | Read confirmed the literal is never reassigned |
| opus F10 / codex F2 | P2 (opus) / P0 (codex) | renderer CSVs use `.6f`, zeroing every \|flux\| < 5e-7 fed to R | **ACCEPT-MODIFIED** | Repro'd. Fixed with `.12g` (the codebase's existing `_finite_csv` format), not codex's `repr()` — see §3 |
| opus F12b | P2 | `graph.html` builds legend via `innerHTML` | **ACCEPT** | Not currently exploitable (confirmed: `legend` is the module constant `SIGN_LEGEND`). Landed as latent hardening |
| codex F13 | P2 | `FileSystemStore.record_run` accepts a path-traversing `run_hash` | **ACCEPT** | Repro'd: `../escaped` created a directory outside the store root |
| codex F11 | P2 | `inspect-run` reports a corrupt manifest as an unknown run, exit 0 | **ACCEPT** | Repro'd for `[]`, `{`, empty — all rc 0 |
| codex F10 | P2 | empty CSV / corrupt parquet dump raw tracebacks | **ACCEPT** | Repro'd both |
| opus F9 | P2 | CSV `.12g` is not bit-exact float64 | **REJECT** | The reviewer's own measurement: worst relative error **2.8e-12**, ~6 orders below any LP tolerance, and `run_hash` canonicalization is coarser still. Changing it would alter every published CSV for no scientific gain. Correct as designed |
| opus F11 | P2 | `taxonomy_model_checksum` folds unrelated taxonomy columns into the hash | **REJECT** | The reviewer explicitly records it as "not a defect… errs on the conservative side (over-sensitive, never colliding)". Over-sensitivity cannot produce a wrong number, only a false non-reproducibility claim; B2/B3/B4 all verified invariant |
| opus F7 / codex F9 (probe half) | P2/P1 | `capability()` reports Gurobi available from `find_spec` alone | **REJECT (as patched) → DEFER** | I measured the proposed fix: `gurobipy.Env()` **succeeds under a size-limited licence** (the limit bites at model size, not env creation). The patch does not detect the case opus described, while making `available` look authoritative. Landing it would be worse than the status quo. See §6 |
| codex F7 | P1 | `write_solve_output` is not transactional across its `os.replace` loop | **DEFER** | Real, and I reproduced the class. Fixing it properly means a generation-directory swap — too invasive for a fix pass. Current behaviour already leaves the directory *without* `manifest.json`, the documented incomplete-run signal. See §6 |
| codex F8 (remaining ~57 sites) | P1 | most artifact writers overwrite in place | **DEFER (partially fixed)** | The commit marker — the workflow manifest — is now atomic. A shared `atomic_write_text` across ~57 sites is a refactor. See §6 |
| opus F5 | P2 | `manifest.artifacts` is a hardcoded, unverified list | **DEFER** | Real (under-declaration reproduced). But raising on a declared-but-absent artifact would abort runs whose figure legitimately failed to render, and doing it right means threading the true list through ~12 call sites. See §6 |
| opus F6 / codex F12 | P2 | no logging subsystem; manifests carry no timestamp | **DEFER** | A new subsystem, not a fix. See §6 |
| codex F9 (service half) | P1 | `GurobiError` from community construction escapes as a raw traceback | **DEFER** | Real, but the clean fix is a structured `EngineUnavailableError` in the service layer — a facade contract change. See §6 |

Both reports' `except Exception` censuses (34 vs 33 sites) agree on classification for every site
I checked; the count differs only because opus counted `cli/main.py:1301` separately. Not a defect
either way.

---

## 2. What I changed

### P0 — a failed computation must never be published as a real number

**`cmig/cli/main.py:2462`** — the abundance-impact failure row now carries `None` for
`community_growth`, `target_member_exchange`, `community_target_exchange`,
`target_influence_share`, `target_secretion_share`, `target_member_contribution` instead of `0.0`.
`None` propagates as a blank CSV cell and a JSON `null`.

**`cmig/cli/main.py:4941` — new `_abundance_impact_plot_series`** — the figure selects points on
`status == "optimal"`, not merely on `target_abundance` being present, and each series is read
through `_optional_float` **without** the `or 0.0` idiom (which would have resurrected the
fabricated zero from a legitimate `None`). Per FIXER rule 2 the omission is *visible*: when points
are dropped the panel title reads `… — N of M points not evaluable (omitted)`.

**`cmig/cli/main.py:1847`** — the gene-KO generic `except` returns `NaN` for all six numeric
fields, matching the sibling "no evaluable consortium" branch 25 lines above. `_finite_csv` already
renders `NaN` as an empty cell, so `gene_ko_rankings.csv` degrades correctly.

**`cmig/cli/main.py:2523` — new `_gene_ko_summary_status`** — `gene_ko_summary.json` derives its
status from the rows (all ok → `ok`, some → `degraded`, none → `failed`) instead of the literal.

**`cmig/io/model_import.py:90`** — `_biomass_reactions` no longer swallows exceptions. I measured
that `linear_reaction_coefficients` returns `{}` for a model with no objective, so the catch was
never needed for its stated case and only converted introspection failures into the scientific
claim "no objective reaction detected". `import_model` wraps it in an actionable `ModelImportError`
at the boundary.

**`cmig/core/medium.py:65`** — `_is_blocked` catches `KeyError` only. Measured: cobra's
`get_by_id` raises exactly `KeyError` for an absent id, so a genuine absence is still treated as
unavailable while a backend error no longer silently removes water from a minimal medium.

### P0 — CC-4, reproducibility identity (full procedure in §3)

**`cmig/core/manifest.py:60`** — `_round_floats` emits `round(x, 6)` when that is lossless
(`round(x,6) == x`) and the exact shortest round-trip `repr` under an `f64:` marker otherwise.

**`cmig/core/workflow_manifest.py:35`** — schema version `1.0` → **`1.1`**, so an envelope hash
computed under the old rule is never silently compared against one computed under the new rule.

**`cmig/cli/main.py:920, :4274`** — the two envelope components that carry *solve-derived* floats
(`strain_growth` abundances from `community_result.abundances`; `host_microbe_bigg`
`coupling_scale`) are now rounded to 6 decimals **where the noise enters**, exactly as
`io.solve_output.build_run_components` already did for the solve hash. This keeps noise absorption
working after the canonicalizer stopped blurring inputs. I audited all 16 envelope component
builders; these two were the only solve-derived sites (`host_ko_impact` abundances come from the
taxonomy file, `abundance_impact` from `--fractions`, `biomass_basis` entirely from argv).

### P1

**`cmig/io/solve_output.py:37` — new `prune_stale_artifacts(out_dir, known, written)`**, extracted
from the inline loop in `write_solve_output` (which now calls it) so the search paths reuse the
helper rather than duplicating it, per the coordinator's CC-3 direction.

**`cmig/cli/main.py:4485` — `KNOWN_SEARCH_ARTIFACTS` / `KNOWN_HOST_SEARCH_ARTIFACTS` +
`_prune_stale_workflow_artifacts`** — called at the end of `_write_search_outputs`,
`_write_multi_target_outputs`, and `_write_host_search_bigg_outputs`. A removal is printed, not
silent.

**`cmig/core/workflow_manifest.py:277`** — `write_workflow_manifest` stages into a same-directory
temp file, `fsync`s, and `os.replace`s; on any exception it unlinks the temp and re-raises.

### P2

- **`cmig/render/client.py:194`, `cmig/render/composer.py:75`** — `.6f` → `.12g`.
- **`cmig/service/store.py:56`** — `record_run` rejects any `run_hash` that is not 64 lowercase hex.
- **`cmig/cli/main.py:518`** — `_load_json_object` raises `CorruptRunArtifactError` when a file
  exists but is not a JSON object; absence still returns `None`. `_cmd_inspect_run` catches → rc 2.
- **`cmig/cli/main.py` — new `_read_taxonomy_csv`** used by `_load_pool_taxonomy` and `_cmd_solve`;
  `render-figure` catches `ValueError` (covers `pyarrow.ArrowInvalid` and `TidyContractError`).
- **`cmig/gui/assets/graph.html:55`** — legend built with `textContent`/`createElement`.

---

## 3. CC-4 — the coordinator's 4-step procedure, and its outcome

**Step 1 — split by contract.** Done, but the investigation changed the shape of the fix. The
envelope and the solve hash share one canonicalizer (`canonicalize_floats` →
`manifest._round_floats`) *by deliberate design* — `test_canonicalize_floats_is_the_same_
normalization_the_solve_hash_uses` exists precisely to stop them drifting apart. Forking it would
have broken that invariant to fix a symptom. So I fixed the shared rule and versioned the envelope.

**Step 2 — try the backward-compatible scheme. It worked.** Measured before committing to it:

```
== BEFORE ==                       == AFTER (backward-compatible) ==
KNOWN_SOLVE_RUN_HASH: cf3c73d9…    KNOWN_SOLVE_RUN_HASH: cf3c73d9…   (identical)
golden fixture:       29844e29…    golden fixture:       29844e29…   (identical)
bounds 1e-7 vs 4e-7 distinct? False    →  True
```

The coordinator's stated risk was that the 3-member fixture might pass `1/3` at runtime. It does —
`result.abundances` is `0.3333333333333333` — but `golden_fixture._run_hash_components` and
`io.solve_output.build_run_components` **both round abundance to 6 decimals before constructing
the components**. So every float reaching the frozen hash is already exactly six-decimal,
`round(x,6) == x` holds, and the serialization is byte-identical. That pre-rounding is also why the
fix is architecturally right rather than lucky: noise absorption already lived at the boundary; the
canonicalizer was doing it a second time and destroying inputs as a side effect.

**Step 3 — not triggered.** The frozen hash did not move, so no deferral was needed. Confirmed
twice: by unit test, and end-to-end through `cmig solve-fixture --solver gurobi` (output above).

**Step 4 — behaviour pinned by test.** `tests/test_round5_p3_io_exception.py` pins both directions:
`test_frozen_solve_hash_does_not_move` / `test_frozen_golden_fixture_config_hash_does_not_move`
(guard rails, passed before and after) and `test_solve_hash_separates_inputs_below_the_rounding_
floor` / `test_workflow_envelope_separates_sub_micro_growth_fraction_and_weights` (failed before,
pass after), plus `test_six_decimal_exact_values_keep_their_current_serialization` which pins the
backward-compatibility property itself.

**Why not codex's patch.** `DEFAULT_FLOAT_DECIMALS = 17` moves *every* hash including the frozen
one — the contract break the coordinator ruled out. The marker-prefixed exact form achieves the
same separation with zero movement.

**Residual limitation, recorded honestly.** Solve-level `abundance` is still pre-rounded to 6
decimals by its builders, so two runs whose abundances differ below 1e-6 still share a solve
run_hash. That rounding is deliberate (it absorbs micom's abundance noise) and removing it *would*
move the frozen hash. Documented in the code comment at `manifest.py:42`; not silently left.

### ⚠️ Downstream handoff to P4

**Workflow-envelope hashes change** (that is the fix). Per the coordinator's note, P4's drift gate
firing on this is the gate working correctly. P4 must regenerate its golden envelope values, and
this change should be sequenced **before** P4's re-bless. The solve-level hash and `golden verify`
are unaffected.

---

## 4. Regression tests

New file **`tests/test_round5_p3_io_exception.py`** — 19 tests. Evidence: on the unmodified tree
**15 of 19 failed** (the other 4 are the frozen-hash guard rails, which must pass both before and
after); after the fixes **19/19 pass**.

```
BEFORE (clean tree):
FAILED ...test_gene_ko_exception_branch_reports_no_effect_size
FAILED ...test_abundance_impact_figure_drops_points_that_were_never_solved
FAILED ...test_abundance_impact_failed_point_is_blank_not_zero
FAILED ...test_gene_ko_summary_status_is_derived_not_a_literal
FAILED ...test_solve_hash_separates_inputs_below_the_rounding_floor
FAILED ...test_six_decimal_exact_values_keep_their_current_serialization
FAILED ...test_workflow_envelope_separates_sub_micro_growth_fraction_and_weights
FAILED ...test_workflow_envelope_schema_version_records_the_canonicalization_change
FAILED ...test_rerun_removes_the_previous_runs_optional_search_artifact
FAILED ...test_search_rerun_into_the_same_directory_leaves_no_orphan
FAILED ...test_workflow_manifest_write_failure_keeps_the_previous_manifest
FAILED ...test_objective_inspection_failure_is_not_reported_as_a_zero_objective
FAILED ...test_absent_exchange_is_blocked_but_a_backend_error_is_not_swallowed
FAILED ...test_store_rejects_a_run_hash_that_is_not_a_sha256
FAILED ...test_inspect_run_reports_a_corrupt_manifest_instead_of_calling_it_unknown
(+ the renderer-precision and malformed-input tests, added after the first run and
 each verified failing against the pre-fix code path)

AFTER: 19 passed
```

CC-1 verified in **both** orderings:

```
$ pytest -q tests/test_render.py -k project_rlib     → 1 passed   (was: ValueError '--out' is not in list)
$ pytest -q tests/test_render.py                     → 11 passed
$ pytest -q tests/test_review_regressions.py -k rlib → 1 passed   (was: TypeError ... 'stdout')
```

---

## 5. Contract changes (existing tests I deliberately updated)

Six, all stated explicitly in the test docstrings themselves. **No test was weakened to pass.**

1. **`test_workflow_manifest.py::test_float_noise_below_the_rounding_floor_does_not_move_the_hash`**
   → renamed `test_a_determining_input_below_the_rounding_floor_still_moves_the_hash`, assertion
   inverted. `dfba_spec.dt` is a user-supplied determining parameter, not a solve output. The old
   contract is exactly the collision CC-4 removes.
2. **`test_run_hash.py::test_float_rounding_absorbs_noise`** → same change for `tradeoff_f`, plus a
   **new** `test_solve_derived_values_are_rounded_by_their_builder_not_by_the_hash` proving noise
   absorption *moved* rather than disappeared.
3. **`test_run_hash.py::test_round_floats_normalizes_negative_zero`** → narrowed from `-1e-9` to
   `-0.0`. The guarantee is about signed zero (one value, two serializations); `-1e-9` is a
   genuinely different value and collapsing it was the bug. The `-0.0 == +0.0` guarantee is
   unchanged and still asserted; a new line asserts `-1e-9` is now distinguishable.
4. **`test_workflow_manifest.py::test_canonicalize_floats_is_the_same_normalization_…`** → the
   *intent* (envelope and solve hash share one rule) is preserved and now checked by comparing the
   two code paths on the same input, instead of pinning the old rule's output.
5. **`test_review_regressions.py::test_tc7_csv_nonfinite_becomes_na`** → the `-2.000000` literal
   encoded `.6f`. The TC-7 guarantee (no `nan`/`inf` tokens, deterministic bytes) is unchanged and
   still asserted; I added a byte-for-byte determinism check and a probe that 3.7e-7 no longer
   becomes zero.
6. **`test_filesystem_store.py`** (4 tests) → placeholder run hashes `"abc123"`/`"h"`/`"nanrun"`/
   `"commit1"` replaced with valid 64-hex digests. These were readability placeholders; I verified
   every production caller passes `compute_run_hash` output
   (`service/engine_service.py:303` builds it, `core/sandbox.py:122` forwards it).

---

## 6. Deferred, with owners

| Item | Why deferred | Suggested owner |
|---|---|---|
| codex F7 — `write_solve_output` generation swap | Needs a sibling-generation directory + pointer switch. Invasive for a fix pass; current failure mode (no `manifest.json`) is the documented incomplete-run signal | I/O follow-up |
| codex F8 — remaining ~57 non-atomic writers | Commit marker is fixed; the rest wants a shared `cmig/io/atomic.py::atomic_write_text` applied uniformly. A refactor, not a fix | I/O follow-up |
| opus F5 — unverified `manifest.artifacts` | Raising on a declared-but-absent artifact would abort runs whose figure legitimately failed to render; doing it right means threading the real list through ~12 commands | manifest owner |
| opus F6 / codex F12 — logging + manifest timestamp | A new subsystem. The timestamp alone is cheap but belongs with the logging decision so both land under one schema bump | schema-versioning owner |
| opus F7 / codex F9 (probe) — Gurobi licence probe | **Measured**: `gurobipy.Env()` (0.002 s) succeeds under a size-limited licence, so the proposed patch does not detect the case it was written for. A correct probe must optimise a small model. Landing the half-fix would make `available` *look* authoritative while still being wrong — worse than today | solver owner |
| codex F9 (service) — `GurobiError` → traceback | Correct fix is a structured `EngineUnavailableError` at the facade boundary; a service-contract change | `engine_service` owner |

---

## 7. Final gates

```
$ python -c "import cmig; print(cmig.__file__)"
/Users/jaeyongryu/orca/CMIG-wt-io/cmig/__init__.py          worktree OK

$ python -m ruff check cmig tests
All checks passed!                                          OK

$ python -m pytest -q tests/
749 passed, 2 skipped, 0 failed  (751 collected)             exit 0  OK
baseline on this worktree: 728 passed, 2 skipped, 1 failed (731 collected)
  — the 1 failure was the CC-1 render test; +20 tests are mine

$ python -m cmig.cli.main golden verify
[OK ] gurobi   golden=0.39.0 installed=0.39.0
[OK ] osqp     golden=0.39.0 installed=0.39.0
→ 모든 golden 이 설치 MICOM 버전과 일치 (승격 가능)          exit 0  OK

$ cmig solve-fixture --solver gurobi   run_hash 29844e29…cef29ab   FROZEN, unmoved
```

Working tree: 10 source files + 5 existing test files modified, 1 test file added
(~480 insertions, ~112 deletions). Nothing committed, pushed or merged.

---
---

# FOLLOW-UP PASS — response to two verifier audits

Triggered by the coordinator after an Opus verifier found a blocking regression in my first pass,
and a codex verifier returned "NOT fully verified" with four further items. Everything below is in
addition to the pass above; the same constraints applied (worktree only, nothing committed).

## A. The regression I caused, and why my own tests missed it

**OSQP golden run_hash moved: `a422eb89…404d3d9d` → `6a30a02a…3fae5c06`.** Reproduced before
fixing:

```
solver | stored              | recomputed          | MATCH
gurobi | 29844e2910360332…   | 29844e2910360332…   | True
osqp   | a422eb89d019f917…   | 6a30a02ac1a36dd5…   | False
         decimals=4  round(0.333333, 4) == 0.333333 -> False
```

**Root cause — my invariant was stated at the wrong precision.** I reasoned "the frozen inputs are
six-decimal-exact, so `round(x, 6) == x` and nothing moves". The invariant that actually matters is
`round(x, D) == x` where **D is the decimals the hash uses**. `golden_fixture.VARIANT_DECIMALS`
hashes osqp at 4 while `_run_hash_components` pre-rounded at `golden.DEFAULT_DECIMALS` (6), so
`0.333333` was not a fixed point at 4, took the new lossless branch, and moved the published hash.
Under the *old* canonicalizer this was invisible because double rounding is idempotent downward
(`round(round(x,6),4) == round(x,4)`).

**Why my tests did not catch it: they only ever exercised gurobi.** Both my hash pins and my
end-to-end `solve-fixture` verification hardcoded one solver. A two-variant fixture needed a
two-variant pin. That is the actual lesson, and it is now structural — every golden pin is
`@pytest.mark.parametrize("solver", …)` over `SOLVER_VARIANTS`.

**Fix.** `decimals` is now an explicit parameter of both component builders, and the caller passes
the same value it will hash at:

- `cmig/golden_fixture.py:65` — `_run_hash_components(result, decimals=DEFAULT_DECIMALS)`;
  `capture()` passes `dec`.
- `cmig/io/solve_output.py:114` — `build_run_components(..., decimals=DEFAULT_DECIMALS)`.

Both docstrings now state the coupling explicitly ("must equal the precision these components will
be hashed at"), and `test_golden_builder_rounds_at_the_decimals_its_hash_uses[gurobi|osqp]` asserts
the fixed-point property per variant rather than trusting it.

**One shipped fixture was internally inconsistent and is corrected.** `expected/osqp/config.json`
stored `components.abundance = 0.333333` (pre-rounded at 6) while its `run_hash` was computed at 4.
Under the old rule that still recomputed correctly; under the new rule the file no longer
reproduced its own published hash. The three abundance values are now stored at 4 decimals —
exactly what the fixed `capture()` writes. **The published `run_hash` is unchanged**
(`a422eb89…404d3d9d`), verified before writing; only the components block changed:

```
-      "Escherichia_coli_1": 0.333333,      +      "Escherichia_coli_1": 0.3333,
```

## B. `golden verify` now gates hashes (it did not, and the verifier was right)

Confirmed: `verify_golden_versions` compared **only** `micom_version`. A gate that stays green while
a published golden hash moves is not a gate — it is precisely why this regression reached the
coordinator instead of my terminal.

It now also recomputes each golden's `run_hash` from its own recorded components at its own
recorded decimals and compares against the published value. This needs **no solver and no
re-solve**, so the gate stays instant while actually protecting the artifact:

```
MICOM-version + run_hash golden regression (SC-5):
  [OK ] gurobi   golden=0.39.0 installed=0.39.0
      [OK ] run_hash 29844e2910360332…
  [OK ] osqp     golden=0.39.0 installed=0.39.0
      [OK ] run_hash a422eb89d019f917…
```

`test_golden_verify_fails_when_a_published_run_hash_moves` proves the gate **fires** (perturbs a
copy and asserts `GoldenVersionMismatch`), not merely that it is green today.

## C. V1–V4

| ID | Status | What was done |
|---|---|---|
| **V1** `medium_checksum` collision | **FIXED** | `cmig/core/medium_spec.py:254` rounded uptake to 6 decimals; a medium is a *user-supplied determining input*, so it is now hashed exactly. Same defect class as CC-4 hiding in a checksum builder rather than the canonicalizer. |
| **V1b** `build_run_components` abundance | **CONFIRMED, kept, now pinned as a documented limit** | This pre-rounding is load-bearing — it is what makes the frozen hashes survivable — so it stays. My earlier claim was too strong and is corrected below. `test_solve_level_abundance_collision_is_a_known_documented_limit` encodes the exact boundary. |
| **V2** sweep cache replay | **FIXED** | Reproduced: `_sweep_condition_content_key` rounded `tradeoff_f` to 6 and `abundance` to 9, so `--tradeoff-fs 0.5000001,0.5000004` produced one key → the second point's solve was **skipped** and the first point's value *and run_hash* republished under the second's `condition_id`. Both roundings removed. `cmig/core/sweep.py:_axis_tradeoff_f` also rounded the recorded axis value, so the artifact could not even reveal the substitution — also removed. |
| **V3** atomicity | **FINISHED for text artifacts, rest deferred** | New `cmig/io/atomic.py::atomic_write_text` (stage in destination dir → fsync → `os.replace`, temp removed on any failure). Applied to render provenance, the generic CLI JSON writer, and all **9** `*_summary.json` run artifacts. Deferred: parquet/figure writers (library-owned binary writes) and `write_solve_output`'s multi-file generation swap — see the deferral table above. |
| **V4** gene-KO rank | **FIXED** | `_ko_ranks` / `_n_ko_evaluated`: a knockout with no effect size gets no ordinal (blank in CSV, `null` in JSON); ok rows stay consecutively numbered; `n_genes_evaluated` now means "produced a result" with `n_genes_attempted` published alongside so nothing is lost; the `rank 1 (largest effect)` headline is suppressed when nothing was evaluable and replaced with an explicit "no knockout could be evaluated (N attempted)". |

### Correction to a claim in the pass above

The statement that sub-1e-6 inputs "now separate" was **too strong as written**. Corrected scope:

- **Separate now:** solve `bounds`, `tradeoff_f`, workflow `growth_fraction`, target weights,
  solver tolerance, `medium` uptake, sweep cache key, recorded sweep axis.
- **Still collide, deliberately:** solve-level `abundance`, because `build_run_components` and
  `_run_hash_components` round it to absorb micom's noise. Removing that rounding moves the frozen
  hashes, so it stays and is now pinned by test rather than remembered.

## D. Other verifier P2s

| Item | Verdict |
|---|---|
| `coupling_scale` is argv-derived, not solve-derived | **CONFIRMED — my change reverted.** `core/host._coupling_scale` builds it from `--microbial-biomass-gdw`/`--host-biomass-gdw` before any solve; `microbe_to_host_ratio` is a pure function of those. My comment was wrong and the rounding was a CC-4 collision, not a fix. Now hashed exactly. |
| builder-decimals vs hash-decimals is unlinked | **FIXED** — the coupling is a parameter, documented in both docstrings, and asserted per variant. |
| `InMemoryRunStore` does not enforce the run_hash contract | **FIXED** — `validate_run_hash` now lives in `core/run_store.py` next to the Protocol and is used by **both** implementations. A double that accepts what production rejects is how an untested contract violation ships. |
| `f64:` sentinel could collide with a literal string | **CONFIRMED reachable in principle, and closed.** Measured: `canonicalize_floats(1/3)` and the string `"f64:0.3333333333333333"` did serialize identically. Strings that could impersonate a float token are now escaped (`str:` prefix, itself escaped so the mapping stays injective). No component in the current vocabulary starts with either prefix, so **no existing hash moves** — verified against both frozen hashes. Note the pre-existing `"NaN"`/`"Infinity"` sentinels have the same property; that predates this work and is left alone deliberately (fixing it would move hashes). |

## E. Test re-audit — "would this fail if the behaviour it names were deleted?"

I re-audited **all 32 tests I added** across this pass. **Four failed the audit** (one of which the
coordinator had already found). All four are fixed:

| Test | Why it was insufficient | Fix |
|---|---|---|
| `test_solve_derived_values_are_rounded_by_their_builder_not_by_the_hash` | Tautological — rounded both inputs itself and never called a builder. Would pass with every builder's rounding deleted. (Found by the coordinator.) | Now calls `build_run_components` on noisy vs clean results, asserts the builder produced the six-decimal value, **and** asserts the un-rounded pair *does* separate — so it fails if the rounding is removed. |
| `test_abundance_impact_failed_point_is_blank_not_zero` (CSV half) | Asserted `"0.0" not in cells`. `_finite_csv` renders `0.0` as `"0"`, so it passed *with the bug present* — measured. | Parses with `csv.DictReader` and asserts the six scientific cells are exactly `""`. |
| `test_failed_gene_ko_row_is_not_given_a_rank_or_counted_as_evaluated` | Exercised the helpers only; would still pass if the writer reverted to `enumerate(rows, start=1)`. | Added `test_gene_ko_artifacts_do_not_rank_a_knockout_that_failed`, which drives the real writer and reads the real CSV/JSON. |
| `test_objective_inspection_failure_is_not_reported_as_a_zero_objective` | `pytest.raises(Exception)` — satisfied by *any* failure, including an unrelated import error. | Asserts the specific injected exception type and message propagate, plus that the success path still returns `[]` / `["BIOMASS"]`. |

The remaining 27 were checked individually and do fail on deletion of the behaviour they name.

## F. Contract changes in this pass (additional to the six above)

7. **`test_review_regressions.py::test_tc3_sweep_tradeoff_f_canonical_rounding`** → renamed
   `…_records_the_value_it_was_given`, assertion inverted. It pinned the rounding that V2 shows
   causes a cache replay. The determinism guarantee TC-3 actually protects (no NaN token, stable
   serialization) is unchanged and still asserted, plus a new assertion that two distinct points
   are not recorded as one value.
8. **`test_sandbox.py`** — placeholder `run_hash="rh-123"` → a valid 64-hex digest, for the same
   reason as the `test_filesystem_store.py` change above (the double now enforces the contract).

## G. Final gates (follow-up pass)

```
$ python -m ruff check cmig tests
All checks passed!

$ python -m pytest -q -p no:randomly tests/
767 collected · 765 passed · 2 skipped · 0 failed · exit 0

$ python -m cmig.cli.main golden verify
gurobi run_hash 29844e2910360332… [OK]   osqp run_hash a422eb89d019f917… [OK]   exit 0

$ real runs, both solvers (cmig.golden_fixture.solve + compute_run_hash at each variant's decimals)
gurobi 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab   MATCH
osqp   a422eb89d019f917f7fc334db8e9a2eff7d89ce49031ccbf215df7bd404d3d9d   MATCH
```
