# P4 — claims made by the implementer, to be INDEPENDENTLY verified

Worktree: `/Users/jaeyongryu/orca/CMIG-wt-followup` (branch `feat/p4-manifest-drift`,
uncommitted). Verify each claim by running it yourself. Do **not** take the
implementer's word for any number below — every one of them is a claim under test.
Report each as CONFIRMED / REFUTED / PARTIAL with your own observed output.

## Claimed scope

New files: `cmig/core/workflow_envelope_golden.py`,
`cmig/core/workflow_envelope_golden.json`, `tests/test_workflow_envelope_golden.py`,
`tests/test_host_map_workflow_manifest.py`, `tests/test_publication_benchmark_manifest.py`.

Modified: `cmig/core/workflow_manifest.py`, `cmig/core/host_map.py`,
`cmig/core/namespace.py`, `cmig/cli/main.py`, `cmig/service/publication_benchmark.py`,
`tests/test_workflow_manifest.py`, `.github/workflows/ci.yml`, `README.md`.

Workflow kinds: 11 → 13 (`host_map`, `publication_benchmark` added).

## Claims

### C1 — host-map determinism
Identical inputs twice → run_hash
`21dc28d077c071295cdc0d51090a4ddd74ab1684771da75ac8caf9880e4611c0`, and the
manifest **bytes** are identical (nothing timestamped).

### C2 — host-map completeness
All 7 non-kind components, perturbed individually, move the hash. Verify the
converse too: is there any input that changes the produced interface map but does
**not** move the hash? That is the failure mode that matters — go looking for it.

### C3 — publication-benchmark determinism
Identical inputs → `58fadcbe54628f3d346e5701f01526ba28c8a52547ac51e72533e9ee9199facf`
twice; `--tradeoff-f 0.5→0.7` → `8649c6f7…`. All 13 non-kind components move the hash.

### C4 — bundle hash includes child hashes
Changing one child `run_hash` → `8b21cc39…`; dropping a certified child → `54757197…`;
reversing child order → unchanged (identity is the set, `bundle_component` sorts).
Also verify: a child whose manifest could not be written is retained with
`run_hash: null` rather than dropped.

### C5 — the community_solve child is carried, not recomputed
The `community_solve` child hash is read from the manifest that leg already wrote
([HASH-SINGLE]), not recomputed. Verify it is manifest-scope `solve`, not `workflow`.

### C6 — cross-surface equality
The `host_map` leg inside `publication-benchmark` and a standalone `cmig host-map`
on the same host + pool produce the **same** run_hash. This is the claim that
justifies `solver_setting = {"solver": None}` — check that justification holds.

### C7 — the drift gate actually fires
Three source perturbations of `cmig/core/workflow_manifest.py` each produced rc=2
with a precise diff:
1. canonical-JSON separators `(",",":")` → `(", ",": ")` → all 13 kinds drift
2. widening `dfba`'s tuple with `tradeoff_f` → `WorkflowManifestError: missing determining components`
3. reordering `host_map`'s tuple → **only** `host_map` drifts, other 12 stay OK

**Re-run all three yourself.** Perturbation 3's selectivity is the important one —
a gate that reports everything as drifted on any change is useless. Note the
implementer's own warning that a same-size same-second revert can leave a stale
`__pycache__/*.pyc`; clear pycache between attempts or you will mis-measure.

### C8 — new kind does not break the gate, removed kind does
`test_adding_a_new_kind_does_not_break_the_gate` vs
`test_removing_a_declared_kind_breaks_the_gate`, and
`test_every_currently_declared_kind_is_covered` fails until a new kind is blessed.

### C9 — re-bless is a no-op on a clean tree
`python -m cmig.core.workflow_envelope_golden` on an unmodified tree must not
change the committed golden file.

### C10 — frozen contract untouched
`golden verify` green; gurobi hash still
`29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`,
osqp `a422eb89d019f917f7fc334db8e9a2eff7d89ce49031ccbf215df7bd404d3d9d`.

### C11 — gates
`ruff check cmig tests` clean. `pytest` 823 collected (731 baseline + 92 new),
820 passed / 2 skipped / **1 failed**. mypy 2 errors, both claimed pre-existing.

### C12 — the packaging claim (NOT verified by the implementer — verify it)
`cmig/core/workflow_envelope_golden.json` is claimed to ship inside the wheel/sdist
(not gitignored, under the `cmig` root allowlist in `scripts/audit_distribution.py`).
The implementer verified this **by inspection only** because the brief forbade `uv`.
A gate whose golden file is missing from the distribution silently skips — i.e. it
is not a gate. **Actually build and check**, using the venv's own build tooling
rather than `uv` if necessary, or run `scripts/audit_distribution.py` directly.

## Known caveats the implementer self-declared — confirm or refute each

1. `tests/test_render.py::test_render_client_passes_project_rlib` fails in the
   worktree because it asserts the R lib path ends with `/CMIG/.Rlib`, which is
   false in any directory not named `CMIG`. Claimed pre-existing and unrelated.
   (Coordinator note: this test ALSO fails in isolation on main for a *different*
   reason — an over-broad `subprocess.run` monkeypatch. Track P3 owns the fix. Do
   not fix it here; just confirm P4 did not cause it.)
2. `publication_benchmark` hash inherits solver determinism via the embedded solve
   hash — certifies "these runs", not "these arguments".
3. The envelope fingerprints inputs, not output bytes.
4. A new workflow kind is unprotected until blessed.
5. `map_spec` records the policy; four fields (`match_order`, `annotation_sources`,
   `secretion_criterion`, `annotation_requires_unique_target`) are control-flow
   facts guarded only by a manually-bumped `HOST_MAP_MATCH_POLICY_VERSION`.
   **This is the weakest point of the implementation — probe it.** Construct a
   change to host-map matching behaviour that alters the produced interface map
   while leaving the hash unchanged. If you succeed, that is a P0 finding.
