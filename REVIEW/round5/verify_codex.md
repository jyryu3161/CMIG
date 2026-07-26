# P4 fix — independent completeness verification (Codex gpt-5.6-sol)

Worktree audited: `/Users/jaeyongryu/orca/CMIG-wt-followup`, uncommitted
`feat/p4-manifest-drift`.

All experiments that changed source or fixtures ran in isolated copies under
`/tmp/cmig-p4-codex.zwAGsZ/`. The six relevant source/test files in the worktree had the
same SHA-256 before and after this audit; no tracked file or scratch directory in the
worktree was changed.

## 1. Summary

**Overall verdict: FAIL completeness / do not accept the host-map fingerprint as complete.**

The fix closes every decision point represented by its synthetic fixture, and the four
previously inert policy constants are now load-bearing. It does **not** close the audited
property: a one-line, plausible host-exchange eligibility change altered an exact interface
map on the shipped iAF987 and iYO844 GEMs while both
`map_spec.match_behavior.digest` and the complete `host_map` `run_hash` stayed
bit-identical. The new host-map regression tests all passed under the broken implementation.

| Requested check | Verdict | Observed evidence |
|---|---|---|
| Behavioural digest completeness | **FAIL — P0** | iAF987 + iYO844 exact map 40 → 38; `ac_e` and `fe3_e` removed under unchanged digest and run hash |
| Refactor output identity | **PASS** | CSV, interface JSON, and summary JSON byte-identical on three real-GEM pairs; interface checksums unchanged |
| Envelope drift gate | **PASS** | 13 kinds OK; independently re-derived `989b6207…` → `4cd3fd31…` for `host_map` only; source fixture edit produced selective rc=2 |
| Frozen 11-component solve hash | **PASS** | Real Gurobi `solve-fixture` emitted and independently re-derived `29844e29…29ab` |
| Full regression suite | **PASS with known unrelated failure** | 851 passed / 2 skipped / 1 failed; only the P3-owned render path assertion |

Findings: **1 × P0, 0 × P1, 0 × P2.**

## 2. Findings

### F1 [P0] The finite probe misses real host-bound regimes, so a changed exact interface map can retain the published hash

- `cmig/core/host_map_probe.py:121-160`
- `cmig/core/host_map.py:172-201`
- `tests/test_host_map_behavior_digest.py:256-297`

**What is wrong.** Every host reaction in `_HOST_REACTIONS` has
`upper_bound=1000`; its uptake examples use only `lower_bound=-1000` and `0`.
Consequently, the probe cannot observe host-index policy changes involving a non-positive
host upper bound or an intermediate negative uptake bound. Those are not hypothetical input
classes: the shipped iAF987 has `EX_ac_e` at `[-8.88, -6.84]` and `EX_fe3_e` at
`[-67.37, -49.21]`, and the shipped iSFV_1184 has `EX_cbl1_e` with
`lower_bound=-0.01`. The test at lines 278-279 distinguishes `< 0` from `<= 0`, but
does not distinguish `< 0` from any threshold between `-1000` and `0`; nor does any test
exercise host `upper_bound <= 0`.

This is a direct consequence of the stated probe limit, not a speculative source-reading
concern. I inserted this plausible symmetry/eligibility guard in the real host index:

```diff
--- a/cmig/core/host_map.py
+++ b/cmig/core/host_map.py
@@
     annotation_candidates: dict[str, list[tuple[str, bool]]] = {}
     for rxn in _iter_exchanges(host):
+        if float(rxn.upper_bound) <= 0.0:
+            continue
         met = _sole_metabolite_id(rxn)
```

I then ran the real CLI with host `models/iAF987.xml` and a one-member taxonomy containing
the shipped `models/iYO844.xml`, before and after that edit. Exact reproduction in an
isolated copy:

```bash
cd /tmp/cmig-p4-repro
printf 'id,file\nmember_iYO844,%s/models/iYO844.xml\n' "$PWD" > tax_iYO844.csv
export PYTHONPATH=$PWD
/Users/jaeyongryu/orca/CMIG/.venv/bin/python -m cmig.cli.main host-map \
  --host models/iAF987.xml --taxonomy tax_iYO844.csv --out before
# Apply the one-line diff above, then remove only this copy's __pycache__ directories.
/Users/jaeyongryu/orca/CMIG/.venv/bin/python -m cmig.core.host_map_probe
/Users/jaeyongryu/orca/CMIG/.venv/bin/python -m cmig.cli.main host-map \
  --host models/iAF987.xml --taxonomy tax_iYO844.csv --out after
```

Observed:

```text
probe digest before:
sha256:6f6f8b856d9ae50070edd865f8c7763620c8e56ab00b4631745b75cd2092667f
probe digest after:
sha256:6f6f8b856d9ae50070edd865f8c7763620c8e56ab00b4631745b75cd2092667f

run_hash before:
252fe5209fb3214ab866e71081495b3b315d0c1c4e0455e5128ddfc30ce60af6
run_hash after:
252fe5209fb3214ab866e71081495b3b315d0c1c4e0455e5128ddfc30ce60af6

exact / unmatched:          40 / 188  ->  38 / 190
interface-map entries:      40        ->  38
removed exact mappings:     ac_e, fe3_e
interface_map_checksum:
  sha256:e0276db31f83010cd69cb73a1e0cbd4985c935c0d0c25b1701ae8691b4628724
  sha256:bfdf37539ba30a02fe7e6c3d244b4b6f3f3e0659483c3f6c478be1bfb78d562e
```

All three published artifacts changed:

```text
host_exchange_map.csv
  d74ddbfce6ef7f57c514d566542ffa31c6b9513cc74026ecb19700297590a1cc
  f16a8d615ebbf7784b0da05630ffbe6b3740289b60ec83bec7eb5caff55fb06a
host_interface_map.json
  517db660e06d7bddd71179dbb7eac018e4539b6abdd036eddf8c483be602903e
  17c66c16eada068ed72d75a36a85e3b5ceb5bb124853615f5c7f463da6716c00
host_map_summary.json
  13bbeff740b896a1112b741e1e89bde0490d52a1607bc524e2bee48a428a1c57
  1033485d0a4f3427c81f046765d9ed49f007ca5e1be1abfb278249452c6026f9
```

The current guard does not catch the break:

```text
pytest tests/test_host_map_behavior_digest.py tests/test_host_map.py \
       tests/test_host_map_workflow_manifest.py
50 passed in 1.77s
```

**Observed vs expected.** Expected: any matcher change that alters the real produced map
must move `match_behavior.digest`, hence the `run_hash`. Observed: two exact mappings and
all three artifacts changed while `map_spec` and `run_hash` were bit-identical. A published
hash can therefore certify two scientifically different interface maps.

**Minimal regression patch.** Add host reactions with negative/zero upper bounds and a weak
negative lower bound to `_HOST_REACTIONS`, add corresponding secretable member reactions,
and assert their exact match and uptake status in
`test_the_probe_fixture_still_distinguishes_every_decision_point`. That makes both
reproduced perturbations move the digest:

```diff
--- a/cmig/core/host_map_probe.py
+++ b/cmig/core/host_map_probe.py
@@
 _HOST_REACTIONS = (
+    _rxn("EX_forced_uptake_e", -10.0, -1.0, (_met("forced_uptake_e"),)),
+    _rxn("EX_weak_uptake_e", -0.01, 1000.0, (_met("weak_uptake_e"),)),
@@
 _MEMBER_A_REACTIONS = (
+    _rxn("EX_forced_uptake_e", 0.0, 1000.0, (_met("forced_uptake_e"),)),
+    _rxn("EX_weak_uptake_e", 0.0, 1000.0, (_met("weak_uptake_e"),)),
```

The probe version, pinned digest, envelope golden, and changelog must then be updated
deliberately. This is only the minimum patch for the demonstrated blind spots. A finite fixture
still cannot prove the universal completeness property. The robust closure is to include a
canonical checksum of the **actual production `HostMapResult` or emitted host-map artifacts**
inside the hashed components; then a real output change cannot retain a hash merely because the
synthetic fixture lacked that input class.

## 3. Reverse-validation results

| Attack / input combination | Digest | Run hash | Scientific output |
|---|---|---|---|
| Host-index `upper_bound <= 0` filter; iAF987 host + iYO844 pool | unchanged | unchanged `252fe520…60af6` | **Wrong:** exact map 40 → 38; `ac_e`, `fe3_e` removed |
| Uptake threshold `< 0` → `< -0.01`; iSFV_1184 host + iML1515 pool | unchanged | unchanged `167443e1…b0421` | **Wrong/misleading:** `cbl1_e` changed uptake `True` → `False`, suggestion changed, `n_host_uptake_capable` 26 → 25 |
| Envelope `_COMPONENT_FIXTURES["map_spec"]` given an unblessed sub-key | n/a | n/a | Correctly rejected: rc=2, only `host_map` drifted |

For the second attack, `host_exchange_map.csv` and `host_map_summary.json` changed while
`host_interface_map.json` and its checksum remained identical. It independently demonstrates
that the two endpoint values in the probe do not cover the real bound domain.

## 4. Checked and found CORRECT

### Four policy constants are now load-bearing

Static inspection and the passing tests confirm:

- `HOST_MAP_MATCH_ORDER` drives the strategy loop at `host_map.py:270`.
- `HOST_MAP_SECRETION_CRITERION` selects the predicate used at `host_map.py:236`.
- `HOST_MAP_ANNOTATION_SOURCES` drives annotation readers at `host_map.py:188`.
- `HOST_MAP_ANNOTATION_REQUIRES_UNIQUE_TARGET` drives the uniqueness condition at
  `host_map.py:198`.

The existing fixture distinguishes all ten perturbations encoded by the fixer. F1 shows that
those ten are not all realistic branches of the real matcher.

### Refactor is output-identical on real GEMs

I exported `HEAD` into one isolated directory, ran its pre-refactor matcher, and compared it
with the current worktree snapshot using the same real model files. Every `cmp` returned 0:

| Host / pool | Counts exact / annotation / normalized / unmatched | CSV SHA-256 (both) | Interface JSON SHA-256 (both) | Summary SHA-256 (both) | `interface_map_checksum` (both) |
|---|---:|---|---|---|---|
| iHN637 / iYO844 | 67 / 6 / 0 / 155 | `c112d143…7d629` | `3bce7996…827e9` | `83929509…967b0` | `sha256:263176e4…1bec3` |
| iAF987 / iYO844 | 40 / 0 / 0 / 188 | `d74ddbfc…a1cc` | `517db660…903e` | `13bbeff7…1c57` | `sha256:e0276db3…8724` |
| iSFV_1184 / iML1515 | 318 / 0 / 0 / 13 | `6cd731f9…a1e0` | `1a75806f…11d` | `a4a6f682…c730` | `sha256:42f34582…6cb5` |

Thus the refactor itself did not change the CSV, interface map, summary, or checksum on any
of the three real-GEM combinations tested.

### Envelope drift gate

Clean command:

```text
python -m cmig.cli.main golden verify-envelope
13 workflow kinds [OK], float-normalization probe [OK], rc=0
```

Independent old/new derivation:

```text
host_map without map_spec.match_behavior:
989b6207bc8bbe927963538fb3148cb24ffd8f2913008f5719eb0cc1bd2c48f4
current host_map:
4cd3fd31caed9b3ce06082559c7b9b7be02edb5bfa2841123bed69ebdaedb58e
```

`host_map` is the only declared kind whose component tuple contains `map_spec`; therefore
the added sub-object changes only that golden kind. After source-editing
`_COMPONENT_FIXTURES["map_spec"]` in an isolated copy without rewriting the stored JSON,
`golden verify-envelope` returned rc=2:

```text
[DRIFT] kind 'host_map': stored input no longer matches the declared component fixture
12 other kinds [OK]
float normalization probe [OK]
```

This confirms the earlier stored-input blind spot is fixed.

### Frozen solve hash, end to end

```text
python -m cmig.cli.main solve-fixture --solver gurobi --out <isolated-output>
run_hash: 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab
```

The emitted manifest had `manifest_scope: "solve"` and exactly the frozen 11 components.
Reconstructing `RunHashComponents(**manifest["components"])` and calling the canonical
`compute_run_hash` returned the same full value. `golden verify` also reported both Gurobi
and OSQP `[OK]`.

### Full suite

Command:

```text
PYTHONPATH=<isolated-current-snapshot> QT_QPA_PLATFORM=offscreen \
  /Users/jaeyongryu/orca/CMIG/.venv/bin/python -m pytest -o addopts='' -q tests/
```

Observed:

```text
1 failed, 851 passed, 2 skipped, 11 warnings in 140.04s
```

The sole failure was
`tests/test_render.py::test_render_client_passes_project_rlib`: it asserts that the R library
path ends in `/CMIG/.Rlib`, while the isolated checkout correctly produced
`/private/tmp/cmig-p4-codex.zwAGsZ/suite/.Rlib`. Neither `tests/test_render.py` nor
`cmig/render/client.py` is in this worktree's diff. No P4 regression was observed.

## 5. Could not verify / out of scope

No requested check remains unexecuted. I did not run the complete multi-leg
`publication-benchmark` workflow because the requested host-map completeness failure was
already reproduced end to end through the real `host-map` CLI and real GEM artifacts.
