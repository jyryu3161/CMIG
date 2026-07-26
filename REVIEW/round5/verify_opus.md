# P4 (workflow-manifest coverage + envelope drift gate) — independent adversarial verification, Claude Opus 5

Worktree `/Users/jaeyongryu/orca/CMIG-wt-followup`, branch `feat/p4-manifest-drift`, uncommitted.
Environment: `PYTHONPATH=/Users/jaeyongryu/orca/CMIG-wt-followup`,
`CMIG_PY=/Users/jaeyongryu/orca/CMIG/.venv/bin/python`; shadow verified —
`import cmig` → `/Users/jaeyongryu/orca/CMIG-wt-followup/cmig/__init__.py`.

## 1. Summary

**Claims: 8 CONFIRMED · 4 PARTIAL · 0 fully REFUTED.**

| Claim | Verdict | One-line reason |
|---|---|---|
| C1 host-map determinism | **PARTIAL** | Determinism + byte-identity confirmed; the literal `21dc28d0…` is not reproducible and is pinned nowhere |
| C2 host-map completeness | **PARTIAL** | Forward direction confirmed (7/7 move the hash); **the converse is REFUTED → P0 (F1)** |
| C3 publication-benchmark | **PARTIAL** | 13/13 components move the hash, determinism + `tradeoff_f` confirmed; literals `58fadcbe…`/`8649c6f7…` not reproducible |
| C4 bundle hash | **CONFIRMED** | All four properties, incl. `run_hash: null` retention |
| C5 solve child carried | **PARTIAL** | Carried-not-recomputed confirmed; "manifest scope `solve`" is **wrong as worded** (no `manifest_scope` key exists) |
| C6 cross-surface equality | **CONFIRMED** | Both surfaces → `c5a6c402…` |
| C7 drift gate | **CONFIRMED** | All 3 perturbations rc=2; **perturbation 3 is correctly selective** |
| C8 new/removed kind | **CONFIRMED** | Tests exist and encode exactly the claimed semantics |
| C9 re-bless no-op | **CONFIRMED** | Golden byte-identical after re-bless |
| C10 frozen contract | **CONFIRMED** | `golden verify` green, both frozen hashes unmoved |
| C11 gates | **CONFIRMED** | 823 collected / 820 passed / 2 skipped / 1 failed; ruff clean; mypy 2 pre-existing |
| C12 packaging | **CONFIRMED** | Built wheel+sdist; golden ships and the gate runs from the wheel |

**Findings: 1 × P0, 0 × P1, 4 × P2.**

The headline result: **I broke the hash-vs-output coupling.** Caveat 5 is not a
theoretical caveat — it is an exploitable P0, demonstrated end-to-end through the real
CLI with two runs that produced a 67-entry and an 11-entry interface map under a
**bit-identical `run_hash`**.

### Process note (important for the coordinator)

A **second verifier (Codex `gpt-5.6-sol`) was running concurrently in this same worktree**
with `danger-full-access` (pid 80541), doing its own source-perturbation experiments. It
created the untracked `.verify_p4/` directory (10:23–10:24) and was running `pytest` in the
shared tree. This is a real mutual-contamination hazard: two agents editing and restoring
the same source files can invalidate each other's measurements and can leave the tree dirty
for the merge.

Mitigation I took: after the one end-to-end demonstration (guarded by before/after
`shasum` on the edited file), I moved **all** remaining perturbation work into a private
copy at `scratchpad/round5/p4/iso`. I did **not** delete `.verify_p4/` — it is not mine.
**The coordinator should confirm Codex also restored cleanly before merging.**

Worktree state on exit — restored byte-exactly:
```
git diff | shasum -a 256
22d040fe75fa64ae3843aaeb83df8d5503ce8ccf5b997755900e2113e08b9792   # == baseline taken at session start
ALL UNTRACKED FILES IDENTICAL TO BASELINE
8 files changed, 808 insertions(+), 35 deletions(-)
```
Only extra entry in `git status` is `?? .verify_p4/` (the other agent's).

---

## 2. Findings

### F1 [P0] host-map's matching behaviour can be changed arbitrarily while `run_hash` stays bit-identical

- `cmig/core/host_map.py:44-65` (`host_map_policy`), `cmig/core/host_map.py:148-230`
  (`build_host_map`), `cmig/core/host_map.py:116-145` (`_host_exchange_index`),
  `cmig/cli/main.py:1093-1094` (`components["map_spec"] = host_map_policy()`)

**What is wrong.** `map_spec` is documented as being "read from the constants and from the
namespace normalizer itself rather than restated, so a change to either necessarily moves
the host-map workflow hash". That is true for exactly two of the eight policy fields —
`interface_map_admits`/`needs_review_match_types` (genuinely consumed by
`_write_host_map_outputs`) and `id_normalization.{exchange_prefix_stripped,
compartment_suffixes_stripped}` (genuinely consumed by `_normalize_metabolite_id`). The
remaining control-flow facts are **inert string/boolean literals that no code path reads**:

| `map_spec` field | Recorded as | What actually decides the behaviour |
|---|---|---|
| `match_order` | `HOST_MAP_MATCH_ORDER` constant | the hard-coded `if/elif` chain at `host_map.py:170-198` — never reads the constant |
| `secretion_criterion` | the string `"exchange_upper_bound_gt_0"` | `if float(rxn.upper_bound) <= 0.0: continue` at `host_map.py:156` |
| `annotation_requires_unique_target` | literal `True` | `len({...}) == 1` at `host_map.py:143` |
| `annotation_sources` | a tuple of *description strings* | hard-coded `.annotation.get("bigg.metabolite")` / `("bigg.reaction")` at `host_map.py:131-136` |

Also uncoupled: `uppercase_stereoisomer_suffix_folded`/`case_folded` (literal `True`s),
`_sole_metabolite_id`'s "exactly one metabolite" rule, `_iter_exchanges`'s exchange-discovery
rule, and `_host_exchange_index`'s first-wins `setdefault` tie-break. The only guard is a
hand-bumped `HOST_MAP_MATCH_POLICY_VERSION = "1.0"`.

The consequence is precisely the failure mode the module docstring says it prevents: the
interface map that **every downstream host-microbe coupling run consumes** can change
completely while the fingerprint that certifies it does not move. A reader re-deriving a
published `host_map` run_hash gets a match and concludes the map is reproduced, when it is
a different artifact.

**Repro (real CLI, end-to-end).** Change one comparison — the secretion criterion — leaving
`HOST_MAP_MATCH_POLICY_VERSION` and every `map_spec` field untouched:

```bash
cd /Users/jaeyongryu/orca/CMIG-wt-followup
export PYTHONPATH=$PWD CMIG_PY=/Users/jaeyongryu/orca/CMIG/.venv/bin/python
printf 'id,file\nmemA,pool/iYO844.xml\n' > $W/tax2.csv      # pool = models/iYO844.xml

# baseline
$CMIG_PY -m cmig.cli.main host-map --host models/iHN637.xml --taxonomy $W/tax2.csv --out $W/pi_before

# perturbation, host_map.py:156
#   -        if float(rxn.upper_bound) <= 0.0:      # can this exchange secrete at all?
#   +        if float(rxn.upper_bound) <= 0.0 or float(rxn.lower_bound) >= 0.0:  # secretion crit.
find . -name __pycache__ -prune -exec rm -rf {} +
$CMIG_PY -m cmig.cli.main host-map --host models/iHN637.xml --taxonomy $W/tax2.csv --out $W/pi_after
```

Observed:

```
host-map complete: 67 exact / 6 annotation / 0 normalized / 155 unmatched (of 228 secretions)
  run_hash: c5a6c402dfa84b4d… (manifest.json)
host-map complete: 11 exact / 0 annotation / 0 normalized / 1 unmatched (of 12 secretions)
  run_hash: c5a6c402dfa84b4d… (manifest.json)

run_hash BEFORE : c5a6c402dfa84b4d4f757014b768f741d2a03482f1928dbdc2b8a887c66257a5
run_hash AFTER  : c5a6c402dfa84b4d4f757014b768f741d2a03482f1928dbdc2b8a887c66257a5
run_hash IDENTICAL: True
map_spec IDENTICAL: True | match_policy_version: 1.0

interface_map entries BEFORE: 67  AFTER: 11
metabolites SILENTLY DROPPED from the auto-admitted interface map: 56
  e.g. ['ac_e', 'ala__D_e', 'alaala_e', 'alltn_e', 'arab__L_e', 'arg__L_e', 'asn__L_e',
        'asp__L_e', 'btd_RR_e', 'citr__L_e']
needs_review BEFORE: 6  AFTER: 0
summary interface_map_checksum BEFORE: sha256:263176e4d9ca356b4
summary interface_map_checksum AFTER : sha256:e27db1bd6932c5a14
```

Note the manifest's own `summary.interface_map_checksum` **did** move (`263176e4…` →
`e27db1bd…`) while `run_hash` did not — the manifest internally contradicts itself, which
is the clearest possible demonstration that the hash is not covering the artifact.

A second, independent break (`match_order`), same host/pool, `map_spec` byte-identical:

```
P-B  needs_review entries, BEFORE -> AFTER:
   ala__L_e      annotation -> normalized   EX_ala__D_e
   arab__D_e     annotation -> normalized   EX_arab__L_e
   cys__D_e      annotation -> normalized   EX_cys__L_e
   glcn__D_e     annotation -> normalized   EX_glcn_e
   glu__D_e      annotation -> normalized   EX_glu__L_e
   met__D_e      annotation -> normalized   EX_met__L_e
map_spec identical: True
```
These are exactly the D/L stereoisomer pairs the code comments flag as the dangerous case;
the `match_type` label a human reviewer uses to decide whether to trust the suggestion is
rewritten under a stable hash.

**Observed vs expected.** Expected: any change to what `build_host_map` produces moves the
`host_map` run_hash (the stated design goal). Observed: 56 of 67 auto-admitted interface-map
entries changed, and all 6 needs-review provenance labels changed, with `run_hash` and
`map_spec` bit-identical.

**Minimal patch.** Stop *describing* the policy and start *fingerprinting* the code that
implements it, so no manual version bump is required:

```diff
--- a/cmig/core/host_map.py
+++ b/cmig/core/host_map.py
@@
+import hashlib
+import inspect
+
+
+def _match_implementation_checksum() -> str:
+    """Fingerprint of the functions that actually decide the map.
+
+    `match_order`, `secretion_criterion`, `annotation_requires_unique_target` and
+    `annotation_sources` are recorded as data but are not read by the matcher, so a change to
+    the matcher moved the produced interface map without moving the workflow hash. Hashing the
+    implementation removes the reliance on a hand-bumped policy version.
+    """
+    return "sha256:" + hashlib.sha256(
+        "".join(
+            inspect.getsource(func)
+            for func in (
+                _sole_metabolite_id, _iter_exchanges, _host_exchange_index, build_host_map,
+                _normalize_metabolite_id,
+            )
+        ).encode("utf-8")
+    ).hexdigest()
+
+
 def host_map_policy() -> dict[str, Any]:
@@
     return {
         "match_policy_version": HOST_MAP_MATCH_POLICY_VERSION,
+        "match_implementation": _match_implementation_checksum(),
         "match_order": list(HOST_MAP_MATCH_ORDER),
```

(`host_map_policy` is defined above the functions it inspects, but is only *called* at
manifest time, so the forward references resolve.) This is a deliberate contract change:
existing published `host_map` and `publication_benchmark` hashes move once, and the change
must be announced in the changelog — but it converts caveat 5 from "a developer must
remember" into "the machine notices". The envelope golden is unaffected, because its
`map_spec` fixture is synthetic.

A complementary (non-exclusive) fix is to drive the control flow from the constants —
iterate `HOST_MAP_MATCH_ORDER` over an index dict rather than a hard-coded `if/elif`, and
compare against `HOST_MAP_SECRETION_CRITERION` — so those four fields become load-bearing.

---

### F2 [P2] `host_spec` hashes the host-model *path string*, so the same model at a different path is a different run

- `cmig/core/workflow_manifest.py:449` (`"host_model": str(host_model) if host_model else None`)

`host_model_checksum` already pins the bytes, so the path string adds nothing but
fragility. A reader who re-runs a published `host-map` with an absolute path — or from a
different working directory — gets a different `run_hash` from identical science and
concludes the run did not reproduce.

Repro / observed:
```
relative host path hash : c5a6c402dfa84b4d4f757014b768f741
absolute host path hash : b52137b2b95492a66af098560c37f3da
SAME BYTES, DIFFERENT PATH STRING -> hash moves: True
```

Patch: keep the path in `summary`/`inputs` for human traceability, and drop it from the
hashed component (or normalise to `Path(...).name`):
```diff
-        "host_model": str(host_model) if host_model else None,
+        # Identity is the bytes (host_model_checksum); the path is provenance, not input.
+        "host_model": Path(host_model).name if host_model else None,
```
The same argument applies to `medium.source` and `quality_spec.sources`.

### F3 [P2] `_child_solve_run_hash` carries any `manifest.json`'s `run_hash` without checking it is a solve manifest

- `cmig/service/publication_benchmark.py` (`_child_solve_run_hash`)

It reads `out/community/manifest.json` and returns `payload["run_hash"]` with no check on
`manifest_schema_version` or scope. If that directory ever comes to hold a workflow-scope
manifest, the bundle records a workflow hash labelled `community_solve` and the
[HASH-SINGLE] guarantee is silently void. Degradation is otherwise correct — I confirmed
missing / corrupt / `run_hash`-less manifests all yield `None` rather than a fabricated hash.

Patch:
```diff
-    return None if value is None else str(value)
+    if payload.get("manifest_scope") == "workflow":
+        return None            # a workflow envelope is not the frozen 11-component solve hash
+    return None if value is None else str(value)
```

### F4 [P2] C5's "manifest scope `solve`" does not exist as a fact in the code

- `cmig/io/solve_output.py:192-233` (solve manifest payload), `cmig/core/workflow_manifest.py:237`

The solve manifest emits `"manifest_schema_version": "2.0"` and **no `manifest_scope` key at
all**; only the workflow envelope emits `"manifest_scope": "workflow"`. The test at
`tests/test_publication_benchmark_manifest.py:159` correctly asserts only the negative
(`payload.get("manifest_scope") != "workflow"`). The behaviour is right; the claim's wording
is not. Suggest either adding `"manifest_scope": "solve"` to the solve payload (a manifest
*format* change, outside the hash) or restating the claim as "not workflow-scope".

### F5 [P2, pre-existing — not caused by P4] `publication_benchmark` cannot fingerprint a relative taxonomy that `cmig host-map` accepts

- `cmig/service/publication_benchmark.py:344` — `taxonomy_model_checksum(taxonomy)` with **no** `base_dir`,
  versus `cmig/cli/main.py:1085` — `pool_model_checksum(taxonomy, base_dir=tax_dir)`

Observed when I first attempted C6 with the ordinary relative-to-the-csv taxonomy layout:
```
ValueError: taxonomy model 파일 없음: pool/iYO844.xml
```
Line 344 is untouched by this diff, so it is pre-existing, but it bounds C6: the two
surfaces agree only when the taxonomy resolves from the process CWD. Worth a follow-up
(`taxonomy_model_checksum(taxonomy, base_dir=config.taxonomy_dir)`).

---

## 3. Claim-by-claim evidence

### C1 — host-map determinism · **PARTIAL**
Two identical invocations produced the same hash **and byte-identical manifests**:
```
run1: run_hash 8780fe68…   run2: run_hash 8780fe68…
a07e3d93782969e788340cca2f65ae1fc7d4768cb52cfa6240883be65e199208  run1/manifest.json
a07e3d93782969e788340cca2f65ae1fc7d4768cb52cfa6240883be65e199208  run2/manifest.json
diff → BYTE-IDENTICAL   (nothing timestamped) ✔
```
The claimed literal `21dc28d077c071295cdc0d51090a4ddd74ab1684771da75ac8caf9880e4611c0`
I could **not** reproduce and cannot falsify: it depends on the implementer's exact host/pool
**and on the path strings used** (F2), and `grep '21dc28d0' tests/ cmig/` returns nothing —
it is pinned in no test. My own values on `--host models/iHN637.xml` + `iYO844` pool:
`c5a6c402dfa84b4d4f757014b768f741d2a03482f1928dbdc2b8a887c66257a5`.
Verdict: the *property* is confirmed; the *number* is UNVERIFIED (missing evidence: the
implementer's exact command line and cwd).

### C2 — host-map completeness · **PARTIAL**
Forward direction, all 7 non-kind components perturbed individually:
```
--- host_map: 7 non-kind components, base hash 989b6207bc8bbe92…
    cmig_core_version   moved_hash=True      model_checksum   moved_hash=True
    dependency_versions moved_hash=True      medium           moved_hash=True
    solver_setting      moved_hash=True      host_spec        moved_hash=True
                                             map_spec         moved_hash=True
    => ALL 7 MOVE THE HASH: True
```
**The converse — which the claim explicitly asks for — is REFUTED. See F1.** Of 10
behaviour perturbations I built and ran, 2 changed the produced map with `map_spec`
byte-identical (secretion criterion, match order). Full matrix in §4.

### C3 — publication-benchmark · **PARTIAL**
```
--- publication_benchmark: 13 non-kind components
    cmig_core_version/dependency_versions/solver_setting/model_checksum/medium/
    tradeoff_f/target_spec/search_spec/quality_spec/dfba_spec/host_spec/
    biomass_basis/bundle_spec  → moved_hash=True  (13/13)
    => ALL 13 MOVE THE HASH: True
identical inputs twice -> same hash: True
tradeoff_f 0.5->0.7 moves hash: True
```
Literals `58fadcbe…` / `8649c6f7…` are config-specific, pinned in no test, not reproducible
here → UNVERIFIED (missing evidence: the implementer's benchmark config).

### C4 — bundle hash · **CONFIRMED** (all four, plus the null case)
```
base bundle hash                 : 217bb6296dffc0f64a103818
changing a child run_hash moves  : True
dropping a certified child moves : True
reversing child ORDER unchanged  : True          # identity is the set; bundle_component sorts
child with unwritable manifest RETAINED (not dropped): True | its run_hash: [None]
null-hash bundle differs from full bundle: True  # honest: that bundle certifies less
```

### C5 — community_solve child carried · **PARTIAL**
```
carried from existing manifest : cf3c73d97be5c3555d5d9e228c08e5088661cc6f1ba36fc7a333d2a9b2aaa633
  -> equals the frozen KNOWN_SOLVE_RUN_HASH: True     # carried, not recomputed ✔
missing manifest -> None (no fabricated hash): True
corrupt manifest -> None            : True
manifest without run_hash -> None   : True
```
Scope sub-claim refuted as worded — see F4. Robustness gap — see F3.

### C6 — cross-surface equality · **CONFIRMED**
```
standalone `cmig host-map` hash : c5a6c402dfa84b4d4f757014b768f741d2a03482f1928dbdc2b8a887c66257a5
publication-benchmark leg hash  : c5a6c402dfa84b4d4f757014b768f741d2a03482f1928dbdc2b8a887c66257a5
C6 CROSS-SURFACE EQUAL          : True
```
(The standalone value also matches the independent real-CLI run in F1 — a useful cross-check.)
The `solver_setting = {"solver": None}` justification **holds**: `build_host_map` is pure
over cobra model attributes (`upper_bound`, `lower_bound`, `metabolites`, `annotation`) and
never constructs or calls a solver — I confirmed by reading `host_map.py:91-230` and by the
fact that all my in-memory perturbation runs completed with no solver invocation. Caveat:
equality requires identical **path strings** (F2) and a CWD-resolvable taxonomy (F5).

### C7 — the drift gate fires · **CONFIRMED, all three, rc=2**
Run in the isolated copy, `__pycache__` cleared before each and the file restored from a
pristine copy after each (final `shasum` match verified).

Baseline: `→ envelope serialization unchanged for 13 workflow kinds`, rc=0.

**1. separators `(",",":")` → `(", ",": ")` → all 13 kinds + the float probe drift.** rc=2.
```
[DRIFT] kind 'abundance_impact': serialization changed
    first difference at character 18:
          golden … '[["workflow_kind","abundance_impact"],["cmig_core_version"'
          actual … '[["workflow_kind", "abundance_impact"], ["cmig_core_versio'
… (all 13) …
[DRIFT] float normalization probe
```

**2. widen `dfba` with `tradeoff_f`** → rc=2, 12 kinds OK:
```
[DRIFT] kind 'dfba': WorkflowManifestError: workflow kind 'dfba' is missing determining
        components: ['tradeoff_f']
    golden components:   [... 'dfba_spec']
    declared components: [... 'dfba_spec', 'tradeoff_f']
```
(The float probe also drifts, because the probe's kind *is* `dfba` — collateral and correct,
but not mentioned in the claim.)

**3. reorder `host_map`'s tuple → SELECTIVITY CONFIRMED.** rc=2, **only `host_map` drifts;
the other 12 kinds and the float probe all report OK**:
```
[OK ] abundance_impact  [OK ] dfba  [OK ] gene_ko_search  [OK ] host_ko_impact
[OK ] host_microbe_bigg [OK ] host_search_bigg [OK ] model_pool_search [OK ] model_quality
[OK ] multi_target_model_pool_search [OK ] publication_benchmark [OK ] strain_growth [OK ] sweep
[DRIFT] kind 'host_map': serialization changed
    golden components:   [..., 'host_spec', 'map_spec']
    declared components: [..., 'map_spec', 'host_spec']
    golden hash: 989b6207bc8bbe927963538fb3148cb24ffd8f2913008f5719eb0cc1bd2c48f4
    actual hash: bd53b935138ff9f558e5ec187b8fe4a4586e5044582ea2e0937e2a4a7d09572d
[OK ] float normalization probe
```
This is a well-targeted gate, not a noise generator.

### C8 — new kind vs removed kind · **CONFIRMED**
All three tests pass and encode exactly the claimed semantics
(`test_adding_a_new_kind_does_not_break_the_gate` asserts `report["ok"] is True` **and**
`uncovered == ["dfba"]`; `test_removing_a_declared_kind_breaks_the_gate` expects
`EnvelopeDrift` matching `"no longer declared"`; `test_every_currently_declared_kind_is_covered`
asserts `uncovered == []`).

### C9 — re-bless is a no-op on a clean tree · **CONFIRMED**
```
before: 2b5872354fcb322a987c0f3c670b0cea04d9220fde99aa451461e40a02c855ef
python -m cmig.core.workflow_envelope_golden   → 13 kinds + probe printed
after : 2b5872354fcb322a987c0f3c670b0cea04d9220fde99aa451461e40a02c855ef   # byte-identical
```

### C10 — frozen contract untouched · **CONFIRMED**
```
MICOM-version golden regression (SC-5):
  [OK ] gurobi  golden=0.39.0 installed=0.39.0
  [OK ] osqp    golden=0.39.0 installed=0.39.0
tests/test_workflow_manifest.py::test_a_known_solve_run_hash_is_bit_identical PASSED
tests/test_workflow_manifest.py::test_shipped_golden_fixture_run_hash_is_unchanged PASSED
```
`29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab` (gurobi) and
`a422eb89d019f917f7fc334db8e9a2eff7d89ce49031ccbf215df7bd404d3d9d` (osqp) live in
`fixtures/community_3_member/expected/{gurobi,osqp}/config.json`, both **unmodified** in
`git status`. `RUN_HASH_COMPONENTS` is untouched by the diff.

### C11 — gates · **CONFIRMED, exactly as claimed**
```
outcome counts: {'.': 820, 's': 2, 'F': 1}   TOTAL: 823
ruff check cmig tests → All checks passed!
mypy cmig → Found 2 errors in 1 file (checked 71 source files)
  cmig/cli/main.py:1697  (x2, HostKoDelta sort key)
```
Both mypy errors are **pre-existing**: line 1697 is in `_cmd_host_ko_impact`'s
`sorted(..., key=lambda d: d.delta_host_objective)`, and `git diff cmig/cli/main.py` contains
**zero** hunks touching that code (`grep -c 'HostKoDelta\|key=lambda' → 0`).

### C12 — packaging · **CONFIRMED empirically** (the claim the implementer could not test)
`hatchling` and `build` are absent from the venv, so I used hatchling 1.31.0 already unpacked
in uv's archive cache via `PYTHONPATH` and drove the PEP 517 backend directly (no `uv`, no
`pip install`), building in the isolated copy:

```python
import hatchling.build as b
b.build_wheel(dist); b.build_sdist(dist)   # → cmig-0.1.0-py3-none-any.whl, cmig-0.1.0.tar.gz
```
```
WHEEL:  44057  cmig/core/workflow_envelope_golden.json
        16860  cmig/core/workflow_envelope_golden.py
SDIST:  cmig-0.1.0/cmig/core/workflow_envelope_golden.json
        cmig-0.1.0/tests/test_workflow_envelope_golden.py
wheel: 86 files   sdist: 166 members
distribution audit passed: cmig-0.1.0-py3-none-any.whl
distribution audit passed: cmig-0.1.0.tar.gz
```
And the decisive check — the gate actually **runs from the unpacked wheel**, not just the
worktree:
```
module loaded from: …/whl/cmig/core/workflow_envelope_golden.py
golden exists     : True
ok                : True
checked kinds     : 13
drifted/removed/uncovered: 0 0 []
assert_envelope_golden() PASSED from wheel
```
The shipped JSON is byte-identical to the source (`2b587235…` both sides), and
`git check-ignore` confirms it is not gitignored. **The gate does not silently skip.**

Sub-note: `scripts/audit_distribution.py` is an *allowlist* checker — it verifies no member
is outside the allowlist, and can never assert a file is **present**. It could not have
answered C12 on its own; the build was necessary.

---

## 4. Reverse-validation: the wrong-answer input combos I built and ran

Ten perturbations of the host-map matching path, each executed against real GEMs
(host `iHN637`, pool `iYO844` — the pair that yields 6 annotation matches). "Breaks
coupling" = produced output changed **and** `map_spec` did not.

| # | Perturbation | Output change | `map_spec` moved | Verdict |
|---|---|---|---|---|
| P-A | `upper_bound <= 0` → `< 0` | secretions 228→229, unmatched 155→156 | no | summary only (map unchanged) |
| P-B | swap annotation/normalized branches | 6 needs-review entries relabelled | **no** | **BREAKS COUPLING** |
| P-C | `len({...}) == 1` → `>= 1` | none on this pair | no | not reproduced here |
| P-D | drop reaction-level annotation fallback | none on this pair | no | not reproduced here |
| P-E | `exact.setdefault` → `exact[met] =` | none on this pair | no | not reproduced here |
| P-F | `_sole_metabolite_id` `== 1` → `>= 1` | none on this pair | no | not reproduced here |
| P-G | remove `.lower()` from normalizer | none on this pair | no | not reproduced here |
| P-H | stereoisomer fold: uppercase-only → always | none on this pair | no | not reproduced here |
| P-I | secretion criterion → require reversible | **interface_map 67→11, needs_review 6→0** | **no** | **BREAKS COUPLING (P0)** |
| P-J | `model.exchanges` → `EX_` prefix scan | none on this pair | no | not reproduced here |

P-C…P-H and P-J did not change the output *for this model pair* — they are still uncoupled
from the hash and would break on models that exercise them (e.g. P-C needs a host with two
exchanges carrying the same BiGG annotation). I report only the two that reproduced.

I also probed the input direction (does any *user input* change the map without moving the
hash?) and found none: member ids, taxonomy metadata and model bytes all enter
`taxonomy_model_checksum`; host model bytes enter `host_model_checksum`; `host-map` exposes
no other behaviour-affecting flag (`--host`, `--taxonomy`/`--model-dir`, `--recursive`,
`--out` only). The break is in the source-change direction, which is exactly what caveat 5
predicted. The opposite failure — hash moves without an output change — does occur (F2).

---

## 5. Checked and found CORRECT (no need to re-review)

- `WORKFLOW_HASH_COMPONENTS` import-time assertions: arity, no repeats, vocabulary subset,
  `workflow_kind` leads every tuple. 13 kinds, arities as declared.
- Ordered `[[name, value], …]` payload — declared order genuinely participates in the hash
  (proved by C7-3).
- `canonical_workflow_payload` rejects both missing and extra components (`WorkflowManifestError`).
- `bundle_component` sorting and the `run_hash: None` retention path (C4).
- `_emit_workflow_manifest` / `_BundleRecorder.emit` never fabricate a hash on failure; they
  warn to stderr and return `None`, and never discard a finished analysis.
- `env_lock` is recorded but excluded from the hash ([HASH-ENVLOCK]).
- The float-normalization probe genuinely covers NaN / ±inf / -0.0 / rounding floor, and
  fires (C7-1, C7-2).
- `HOST_MAP_INTERFACE_MAP_ADMITS` / `HOST_MAP_NEEDS_REVIEW_TYPES` **are** load-bearing in
  `_write_host_map_outputs` — changing them moves both output and hash. Correctly coupled.
- `NORMALIZE_EXCHANGE_PREFIX` / `NORMALIZE_COMPARTMENT_SUFFIXES` are read by
  `_normalize_metabolite_id` and recorded in `map_spec`. Correctly coupled.
- Caveat 1 (`test_render.py::test_render_client_passes_project_rlib`): **confirmed
  pre-existing and unrelated to P4.** It asserts the R lib path ends with `/CMIG/.Rlib`;
  observed `…/p4/iso/.Rlib`. Neither `tests/test_render.py` nor `cmig/render/client.py` is
  in the P4 diff. Not fixed here (P3 owns it).
- Caveats 2, 3, 4: all confirmed as accurately self-declared. Caveat 3 in particular is the
  root cause of F1 — the envelope fingerprints inputs, and `map_spec` is a *declared* input
  that is not the *actual* input.

## 6. Could not verify / out of scope

- **The literal hashes in C1 and C3** (`21dc28d0…`, `58fadcbe…`, `8649c6f7…`, `8b21cc39…`,
  `54757197…`). None appears in any test or fixture (`grep -r` over `tests/ cmig/` → no
  hits), and all are sensitive to path strings (F2) and to the implementer's exact
  host/pool/config. **UNVERIFIED** — missing evidence: the exact command lines, working
  directory, and benchmark config used to produce them. I verified the *properties* those
  numbers were meant to demonstrate instead, and every property held.
- **A full end-to-end `publication-benchmark` run.** Not executed — it requires a multi-leg
  community solve plus dFBA plus host coupling, beyond the time budget. C3/C4/C5/C6 were
  therefore verified at the component-construction level, using the exact component dicts
  the service builds (read verbatim from `publication_benchmark.py`). C6's result being
  bit-identical to my real-CLI `host-map` run gives independent confidence that the
  component-level reconstruction is faithful.
- **Codex's concurrent restoration.** I verified *my* changes are fully reverted; I cannot
  vouch for the other agent's. `.verify_p4/` was still present on exit.
