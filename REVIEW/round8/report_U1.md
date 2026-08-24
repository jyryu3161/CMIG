# Round 8 U1 report — pair/delta/single CLI and medium unification

## What changed and why

### One medium contract for the previously mismatched APIs

Before this track:

- `growth_feasible(model, threshold, solver)` had no medium argument. It always optimized the
  model's inherited SBML medium, even when the calling product workflow was about a user-supplied
  medium.
- `analyze_pair` solved the MICOM community on the community's inherited medium, then loaded each
  member afresh and solved it on that model's independent native medium. Its `co - mono` deltas
  therefore mixed media. No caller could supply `--exact-medium`, strict unmatched handling, or
  namespace-translated media.
- Missing co-culture member growth was coerced through `or 0.0`, which could fabricate a zero.

After this track:

- `solve_single_model`, reaction/gene KO, FVA, exchange summary, and `growth_feasible` accept the
  same optional `medium`, `strict_medium`, and `exact_medium` contract. Every supplied medium goes
  through `apply_medium_translated`; application occurs in a model context so bounds are restored.
- `minimal_medium_cardinality` accepts the same contract. Its candidate medium is established by
  `apply_medium_translated` before the MILP, so strict unmatched and exact boundary-isolation
  semantics are no longer bypassed by caller-side mutation.
- `analyze_pair` applies the requested medium to the community through
  `apply_medium_translated`, measures the community's effective metabolite-level offer, translates
  that offer into each monoculture's exchange namespace, and applies it exactly to each mono leg.
  Metabolites for which a member has no exchange are explicitly recorded and exempted from the
  equality check; every other mismatch fails the analysis. Thus every reported interaction delta
  is controlled for medium.
- `--exact-medium` determines whether a custom community/model medium replaces all mass sources
  or merges onto the default. Pair monoculture projection is exact after that choice in either
  mode, because a mono-vs-co comparison must hold the effective offer fixed.
- The new model-bearing CLIs enforce the namespace gate: callers must supply reviewed
  `--namespace-decisions` or explicitly assert `--assume-bigg-namespace`. The policy and decision
  keys are hashed.
- Missing co-culture member growth is now NaN/failure, never a fabricated zero.

### New CLI workflows

- `cmig pair`: exactly two taxonomy/model-dir members; mono/co growth and deltas, interaction
  typing, MRO/MIP, and a cross-feeding summary explicitly labelled as potential shared-pool
  co-occurrence (not identifiable pairwise transfer). `--per-medium` accepts comma-separated paths
  directly or through `--media/--mediums`; it writes the long-format `matrix.parquet` through
  `cmig.core.matrix`.
- `cmig delta`: compares `nodes.parquet` and `profile.parquet` from ordered baseline and variant
  completed run directories through `compute_delta`. It verifies any recorded input result digest
  before comparison and refuses a mismatch.
- `cmig single`: FBA, pFBA, or both; exchange summary; optional whole-model FVA; optional reaction
  KO list with deltas only when baseline and KO are both comparable.
- `cmig minimal-medium`: cardinality-minimal candidate medium, achieved-growth validation,
  leave-one-out verified limiting nutrients, forced-supply disclosure, and failed-MILP exit 3.
- All four commands use run directories, workflow manifests, result digests, `inspect-run`, and
  the 0/2/3 exit contract. All admit `--allow-failed-run` where failed scientific artifacts can be
  written.
- `GUI_CLI_WORKFLOWS` and `RUN_SUMMARY_FILES` include all four commands. Medium-bearing map entries
  advertise `--medium`, `--exact-medium`, and `--allow-unknown-medium`.

### Workflow envelopes

Added additive kinds `pair`, `delta`, `single`, and `minimal_medium`, with explicit component
tuples and arity assertions. New component vocabulary covers namespace, pair-condition, ordered
delta-run, single-analysis, and minimal-medium inputs. No existing tuple or schema version changed.
The documented generator added only the four new JSON entries; the diff for every previous kind
is byte-empty.

## Numerical medium-mismatch demonstration

Basis: bundled synthetic acetate-producer/butyrate-consumer pair, Gurobi 12.0.3,
`tradeoff_f=0.5`, exact medium `EX_glc__D=0`, `EX_ac=10`.

| Quantity | Old mismatched contract | Redesigned controlled contract |
|---|---:|---:|
| co growth, producer | 0.0 | 0.0 |
| co growth, consumer | 5.0 | 5.0 |
| mono growth, producer | 10.0 (native glucose remained open) | 0.0 |
| mono growth, consumer | 5.0 | 5.0 |
| producer growth delta | -10.0 | 0.0 |
| consumer growth delta | 0.0 | 0.0 |
| interaction | amensalism | neutralism |
| producer `growth_feasible` | `True` on native medium | `False` on exact acetate medium |

The old numbers were reproduced by applying the exact medium only to the community and calling
the old-equivalent no-medium single-model solve for each member. The new numbers came from
`analyze_pair(..., medium=spec, exact_medium=True)` and
`growth_feasible(..., medium=spec, exact_medium=True)`. The changed answer is therefore caused by
closing the medium mismatch, not by a solver or model change.

## Verification log

All Python/project commands used `uv run --no-sync`. The sandbox denied uv's default global cache
(`~/.cache/uv/sdists-v9/.git`), including with the brief's shared-venv fallback alone, so successful
runs used:

```text
UV_CACHE_DIR=/tmp/cmig-u1-uv-cache \
UV_PROJECT_ENVIRONMENT=/Users/jaeyongryu/Projects/CMIG/.venv \
PYTHONPATH=. uv run --no-sync ...
```

### Static and owned/adjacent tests

- `ruff check .` — pass, no findings.
- `mypy cmig` — pass, 0 errors in 77 source files.
- `pytest -q tests/test_pair.py tests/test_workflow_map_coverage.py tests/test_round8_pair_delta_single_cli.py`
  — pass (13 tests).
- The broader selected suite covering single-model, minimal-medium, delta, manifests, envelope
  golden, result digest, inspect-run, exact-medium, strain-growth medium basis, and solve-medium
  behavior passes when the one stale round-7 closed-set assertion described under Integration
  notes is deselected.
- A full randomized suite attempt collected 1,299 tests and exited 133 (SIGTRAP) as the first
  desktop GUI test began:
  `tests/test_gui_round5_p2.py::test_community_solve_blocks_until_namespace_is_confirmed`.
  The preceding tests passed/skipped normally. This is a headless Qt/native process abort, not a
  pytest assertion, and GUI files/tests are U5/outside U1 ownership.

### Hash and envelope gates

- Pre-change `cmig golden verify-envelope`: all 13 existing kinds OK.
- After declaring kinds, before golden update: all 13 existing kinds still OK; only `delta`,
  `minimal_medium`, `pair`, and `single` reported `[NEW]`.
- `python -m cmig.core.workflow_envelope_golden`: additive capture completed.
- Final `cmig golden verify-envelope`: all 17 kinds plus float-normalization probe OK.
- `cmig golden verify`: pass; frozen solve run hashes unchanged:
  - Gurobi `29844e2910360332...`
  - OSQP `a422eb89d019f917...`

### Real CLI demonstrations and `inspect-run`

All used the bundled synthetic pair models generated through `cmig.synthetic_pair`; delta compared
two real `cmig solve` run directories.

1. Pair matrix:

   ```text
   cmig pair --taxonomy .../pair.csv \
     --per-medium .../glucose.csv,.../acetate.csv --exact-medium \
     --assume-bigg-namespace --out .../pair_final
   ```

   Result: 2/2 conditions; glucose interaction `mutualism`, acetate interaction `neutralism`.
   `inspect-run`: kind `pair`, status `ok`, run hash
   `64c8bd13519cd2f6f0fb8e67093e18fd496631a40bfd0eb4c12b4906200ad547`, result digest
   `sha256:1d789907154d4a2bd78991d6b0aec90a581bee2c7d99fb427c0e6efdc08d534d`, verified.

2. Single model:

   ```text
   cmig single --model .../producer.xml --method both --fva \
     --reaction-ko GLC2AC --medium .../glucose.csv --exact-medium \
     --assume-bigg-namespace --out .../single_run
   ```

   FBA objective 10.0; pFBA objective 10.0; `GLC2AC` KO objective 0.0, delta -10.0.
   `inspect-run`: kind `single`, run hash
   `53a77c4dc2f23cc4149268259ad3f7edceb6b082746065f348ef2f28ff6247ba`, result digest
   `sha256:4507e6ffc84daa82e2330ba35b03609be29334a9335ba12c7da20f3526b943b7`, verified.

3. Minimal medium:

   ```text
   cmig minimal-medium --model .../producer.xml --min-growth 1 \
     --medium .../glucose.csv --exact-medium --assume-bigg-namespace \
     --out .../minimal_run
   ```

   One component, `EX_glc__D_e`; achieved growth 1.0; glucose leave-one-out limiting.
   `inspect-run`: kind `minimal_medium`, run hash
   `f84bc58a02e08e8976a01188cdc33ca9c2b0ed235d41363242174fc6af3e0f6a`, result digest
   `sha256:4f92846b96743807d8f099655d09e0bb6b265521203abfe6e7156325fe3c65e6`, verified.

4. Delta:

   ```text
   cmig delta --baseline .../solve_base --variant .../solve_variant \
     --out .../delta_run
   ```

   Baseline growth 12.5, variant growth 10.0, delta -2.5; three significant profile deltas.
   `inspect-run`: kind `delta`, run hash
   `d3492905b6c493606336118e30fc01b83445b14083bfc544531e8d877ca668a9`, result digest
   `sha256:6efc685fafa6918997e020deacff15d8c7576c5e0e33b07ac810e093a5c49af0`, verified.

## Proposed CHANGELOG entries

- Added `cmig pair`, including controlled mono-vs-co growth deltas, interaction/MRO/MIP,
  potential cross-feeding output, and per-medium matrix mode.
- Added `cmig delta` as the CLI counterpart to GUI baseline-vs-variant Compare over completed run
  directories.
- Added `cmig single` for FBA/pFBA, FVA, reaction knockout, growth feasibility, and exchange
  summaries.
- Added `cmig minimal-medium` for cardinality-minimal candidate media and leave-one-out verified
  limiting nutrients.
- Fixed `growth_feasible` and `analyze_pair` to apply media through the shared translated
  merge/exact pipeline; pair interaction deltas now hold the effective medium fixed across mono
  and co legs.
- Added workflow-manifest kinds `pair`, `delta`, `single`, and `minimal_medium` without changing
  serialization or hashes for existing workflow kinds.

## Integration notes / risks

1. `tests/test_round7_exact_medium.py::test_every_medium_bearing_command_accepts_exact_medium`
   hard-codes the pre-round-8 set of medium commands. It now fails because `pair`, `single`, and
   `minimal-medium` correctly expose `--medium`. That test is outside U1 ownership and was not
   edited. The coordinator should add those three names to its expected set; its separate equality
   check then confirms all three also expose `--exact-medium`.
2. The uv global-cache permission failure is environmental. Setting the task-local
   `UV_CACHE_DIR` made all required commands use the already-synced shared venv successfully.
3. Full-suite SIGTRAP occurs at the first Qt GUI test in this headless worker. U1-owned and
   adjacent non-GUI contracts are green; no GUI file was changed.
4. `result_digest.cross_run_comparable` remains false for the new kinds until repeat-run byte
   determinism is separately measured. The digest still verifies each run's current artifact
   bytes, which is the claim demonstrated above.

## Proposals deliberately not implemented

- Did not edit `CHANGELOG.md` or `README.md`; both are coordinator-owned. The proposed entries and
  command examples are supplied above.
- Did not update the out-of-ownership round-7 exact-medium census test; the required integration
  change is named precisely above.
- Did not change `cmig/core/fva.py`; `single` consumes its public API read-only as required.
- Did not modify GUI code, U2 tidy/interaction code, U3 sweep, U6 dFBA, dependency files, or solve
  goldens.
- Did not bump the workflow-manifest schema: all changes are additive new kinds, and existing
  serialization is byte-identical.
