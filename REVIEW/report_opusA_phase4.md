# CMIG Phase 4 (batch 1) — manifest + run_hash for every science command

Closes the #1 remaining reproducibility gap: R2-C **F6**, named by all five independent
evaluations and carried on my own phase-3 deferral list. Before this, only `solve`/`solve-fixture`
emitted a `manifest.json`; for every other science command `inspect-run` returned
`run_hash: null`, and the parameters that *determine* the answer were recorded nowhere.

**Every claim below was verified by running the command and reading its output.**

---

## 1. The frozen contract is untouched

| Check | Result |
|---|---|
| `RUN_HASH_COMPONENTS` | still exactly the same 11 names, same order ([HASH-11] assertion intact) |
| `DEFAULT_FLOAT_DECIMALS` | unchanged (6) |
| `cmig solve-fixture --solver gurobi` run_hash, before → after | `29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab` → **identical** |
| `uv run cmig golden verify` | `[OK] gurobi 0.39.0`, `[OK] osqp 0.39.0`, exit 0 |
| `[HASH-SINGLE]` | preserved — the workflow envelope **carries** a solve hash, never recomputes one |

The baseline hash was captured from the tree *before* any edit and re-checked after all wiring.
It also matches the value R2-C recorded independently in round 2, which makes it an outside check
rather than only a self-comparison.

Two regression tests pin this going forward: `test_a_known_solve_run_hash_is_bit_identical`
(fixed 11-component input → pinned digest) and `test_shipped_golden_fixture_run_hash_is_unchanged`
(the gurobi golden fixture's stored hash, which `golden verify` gates on).

## 2. Design: an envelope, not an extension

New `cmig/core/workflow_manifest.py`. Rather than touching the 11, each workflow **kind** declares
its own ordered component tuple:

- `WORKFLOW_HASH_COMPONENTS` — 11 kinds, each an explicit ordered tuple;
- `_EXPECTED_ARITY` — a per-kind size assertion, so changing a component set without changing its
  number fails at import. Editing a contract is necessarily a deliberate act, mirroring [HASH-11];
- `WORKFLOW_COMPONENT_VOCABULARY` — a typo in a kind tuple fails at import instead of silently
  dropping a determining parameter out of the hash;
- components serialize as an **ordered `[name, value]` pair list**, not a dict, so the declared
  order is itself part of the hash;
- float normalization is shared with the solve hash via `manifest.canonicalize_floats` (a public
  alias of the existing private `_round_floats`) rather than a second implementation that could
  drift;
- a missing determining component raises `WorkflowManifestError`; so does an extra one, because
  silently ignoring it would let a caller believe it was hashed.

Where a community solve happens inside a workflow, its 11-component hash is embedded as the single
`solve_run_hash` component, computed through the one canonical path
(`build_run_components` → `compute_run_hash`). Verified: the `strain_growth` manifest carries
`solve_run_hash: bf95e9698eda1db8…`.

## 3. Commands now emitting manifest + non-null run_hash

Every one of these was run for real; the hash shown is from the produced `manifest.json`.

| Command | `inspect-run` kind | run_hash |
|---|---|---|
| `search` (single target) | `model_pool_search` | `f895587806f8f557…` |
| `search --target-preset scfa --multi-metric carbon_equivalent` | `multi_target_model_pool_search` | `cb4806405393cbdc…` |
| `search-fixture` | `model_pool_search` | `e7eed5cee92ddc83…` |
| `strain-growth` | `strain_growth` | `f9570a9d35faa17d…` |
| `abundance-impact` | `abundance_impact` | `c80303a4f999573b…` |
| `gene-ko-search` | `gene_ko_search` | `33f2e8c295100f3b…` |
| `host-microbe-bigg` | `host_microbe_bigg` | `b42ee1a2eec8e426…` |
| `host-search-bigg` | `host_search_bigg` | `f2e4514df65959f4…` |
| `host-ko-impact` | `host_ko_impact` | `b31c0f1be61d6b37…` |
| `sweep` | `sweep` | `c13597660f0ab02a…` |
| `dfba` | `dfba` | `90664e4b41657a35…` |
| `model-quality` | `model_quality` | `498e2b921ba9bc86…` |
| `solve-fixture` (unchanged path) | `community_solve` | `29844e2910360332…` |

### What is recorded

Every kind records cmig version, the full dependency-version map (micom/cobra/optlang/gurobipy/
osqp/pandas/pyarrow), solver setting, model checksum and medium. On top of that, per kind:

- **searches** — target/preset/direction/multi-metric/effective *and* user weights/carbon numbers
  and their source metabolites, min/max size, strategy (requested and resolved), seed, top_k,
  n_samples, robustness_fva, growth_fraction;
- **strain-growth** — abundances, tradeoff_f, the **namespace-bridge decisions** (which metabolites
  the community offered, which each member had no exchange for, and the `--single-medium` mode),
  the flux normalization actually used, and the embedded solve hash;
- **abundance-impact** — the swept member and its fraction grid, and the per-point flux
  normalization actually used (phase 3 found the pFBA fallback can fire on some points and not
  others, changing the flux-selection rule mid-curve);
- **KO kinds** — ko level, member, the explicit gene/reaction list, selection mode, seed,
  max_genes, and the ids actually screened (a truncated screen is a different experiment);
- **host kinds** — host model checksum, interface-map checksum, host objective, host/microbe medium
  checksums, exchange suffix, exclusions, keep-host-uptake, and the full biomass basis
  (kind + source + both gDW values);
- **sweep** — the axis grid, metric, FVA settings, and the per-condition 11-component solve hashes;
- **dfba** — dt, min_dt, t_end, km, vmax, initial biomass/concentrations, growth floor;
- **model-quality** — per-file checksums and which checks were run.

Spot-check from the brief's own SCFA command:
`target_spec.carbon_numbers = {ac:2, but:4, lac__D:3, lac__L:3, ppa:3, succ:4}`,
`growth_fraction = 0.5`, `search_spec = {min_size:2, max_size:2, seed:0, top_k:10,
strategy_resolved: exhaustive, exhaustive_max:100}`.

## 4. Both hash directions, verified on real runs

| | Command pair | Result |
|---|---|---|
| identical inputs → identical hash | `search` run twice | `f895587806f8f557…` both times |
| | `dfba --dt 0.5` run twice | `90664e4b41657a35…` both times |
| changed parameter → changed hash | `search --growth-fraction 0.5` vs `0.7` | `f895587806f8f557…` vs `11c1c5d304f8f2a9…` |
| | `dfba --dt 0.5` vs `--dt 0.25` | `90664e4b41657a35…` vs `1a2ca0499df839e7…` |
| | `model-quality` vs `--check-blocked-reactions` | `498e2b921ba9bc86…` vs `adfd7bcc79169ac7…` |

Also covered by parametrized unit tests over every recorded field, plus: two kinds cannot collide
(every tuple leads with `workflow_kind`), float noise below the rounding floor does not move a
hash, and non-finite floats serialize deterministically.

## 5. `inspect-run` now reports every kind uniformly

Two things had to change:

1. **Kind confusion.** `RUN_SUMMARY_FILES` maps `manifest.json → community_solve` and is scanned
   first, so giving workflows a manifest would have relabelled every search/host/KO run a
   community solve. `_inspect_run_dir` now reads the manifest first and honours
   `manifest_scope == "workflow"` → `workflow_kind`.
2. **Status vocabulary.** R2-C **F11** found `inspect-run` emitting `optimal` and `completed`
   alongside the `ok`/`degraded`/`failed` tiers that `_STATUS_SEVERITY` and every automated gate
   are written against. A workflow manifest's status (the derived run-level tier) now wins over a
   summary's raw solve status, and legacy raw statuses are normalized. All 13 run kinds above now
   report a status inside the vocabulary.

`_compact_manifest` also surfaces `workflow_kind`, `hash_components` and `components`, so a reader
can see what the answer depended on — and in what order it was hashed — straight from
`inspect-run`.

## 6. Gates

- `uv run pytest -q` → **EXIT=0**, 688 collected, **686 passed / 2 skipped / 0 failed**
  (both skips pre-existing: `Recon3D.xml` fixture absent). See §8 for the one test whose
  contract I changed.
- `uv run ruff check cmig tests` → **All checks passed**.
- `uv run cmig golden verify` → both solvers OK, exit 0.
- New tests: `tests/test_workflow_manifest.py` (46) + `tests/test_inspect_run_workflow_manifest.py`
  (28) = **74**, none requiring a solver.

## 7. Two judgement calls worth flagging

**A provenance failure must not destroy a finished analysis.** `_emit_workflow_manifest` catches
broadly and reports `analysis completed but its reproducibility manifest could not be written
(...); this run has no run_hash`. It never fabricates a hash. I widened this after a `TypeError`
in my own sweep component builder aborted an otherwise-successful sweep — the narrow exception
tuple turned a provenance bug into data loss.

**`solve_run_hash` is `None` when the solve was not optimal.** A failed solve must not be
fingerprinted as though it had succeeded.

## 8. One pre-existing test contract changed

`tests/test_cli_workflows.py::test_inspect_run_reports_manifest_metadata` asserted
`payload["status"] == "completed"` — it pinned the inconsistent vocabulary F11 reported. It now
asserts `"ok"`, with a comment explaining why. This is a deliberate behaviour change, not a test
repair, and reviewers should look at it.

## 9. Not done in this batch

- **`dfba-fixture`, `dfba-sensitivity`, `spatial-preview`, `stats-*`, `sandbox-fixture`,
  `host-fixture`, `host-generic`, `host-benchmark`, `namespace-suggest`, `model-review`,
  `host-map`, `publication-benchmark`** emit no workflow manifest. The brief scoped this batch to
  the eleven commands named in F6 plus `search-fixture`; these are the remainder.
- **The workflow hash does not cover output bytes.** It fingerprints the *inputs* that determine
  the answer, which is what re-derivation needs; it is not a checksum of the result files.
- **No `golden verify` equivalent for workflow hashes.** There is no stored expected-value gate
  that would catch a future drift in the envelope's serialization the way SC-5 does for the 11.
  The per-kind arity assertions catch component-set edits, not serialization changes.
