# P4 round 2 — adversarial verification of the fix (Claude Opus 5)

Target: `/Users/jaeyongryu/orca/CMIG-wt-followup`, branch `feat/p4-manifest-drift`, uncommitted.
**Isolation honoured:** every perturbation ran in `scratchpad/round5/p4/iso2`, a `rsync` copy of the
worktree. I made **zero** in-place edits to the worktree this round and left no scratch inside it.
Verified on exit: `git diff | shasum` = `1dfac3f5c587e28931f57f1e3831849c5b48eb9c0a5bf950a1b84de7b8bc5d71`
(identical to the baseline I took before starting), all 7 untracked files byte-identical, `git status`
clean of anything of mine. `.verify_p4/` from the previous round is gone — not by my hand.

## 0. Headline

| Task | Verdict |
|---|---|
| 1. Attack the probe | **BROKEN — 3 of 8 perturbations change real output under a bit-identical `run_hash`** |
| 2. "Output-identical refactor" | **CONFIRMED**, and on a second GEM pair the fixer did not test |
| 3. Gate blind spot closed | **CONFIRMED** — fires on an edited fixture; deep-copy holds top-level *and* nested |
| 4. Frozen hash + re-bless scope | **CONFIRMED by real execution** — but the scope check **misses a 3-kind blast radius** (new P2) |
| 5. F5 REJECT | **ACCEPTED** — I reproduced the fixer's `sha256:91e7d085…`; my F5 was an artifact of my own harness |

**The fix is a real improvement and it is not sufficient.** It closes every perturbation the fixer
enumerated, including both of mine. But the CHANGELOG's claim — *"Any change to host-map matching
behaviour moves the hash"* (`CHANGELOG.md:50`) — is **demonstrably false**, and the counterexamples
are ordinary feature work, not adversarial contortions.

---

## 1. The probe is broken (P0, same class as the original finding)

### What I did

Eight perturbations of the **post-fix** `build_host_map`, each measured on two axes at once:
the probe digest / `map_spec`, and the real output on real GEMs (host `iHN637`, pool `iYO844`).

| # | Perturbation | real output | probe digest | `map_spec` | verdict |
|---|---|---|---|---|---|
| A1 | cap entries at 100 ("keep the CSV small") | **changed** | unchanged | unchanged | **BREAKS** |
| A2 | cap host-index build at 50 exchanges ("perf") | **changed** | unchanged | unchanged | **BREAKS** |
| A3 | skip annotation match for ids containing a digit | unchanged | unchanged | unchanged | no effect here |
| A4 | drop currency metabolites (h2o/h/co2/o2/pi/nh4) | **changed** | unchanged | unchanged | **BREAKS** |
| A5 | secretion threshold `> 0.0` → `> 1e-9` | unchanged | unchanged | unchanged | no effect here |
| A6 | `can_uptake` `< 0.0` → `< -1e-9` | unchanged | unchanged | unchanged | no effect here |
| A7 | refuse normalized match for ids > 8 chars | unchanged | **moved** | **moved** | gate works |
| A8 | consider only the first pool member | unchanged | **moved** | **moved** | gate works |

### End-to-end through the real CLI

```
### BASELINE (post-fix, unmodified) ###
host-map complete: 67 exact / 6 annotation / 0 normalized / 155 unmatched (of 228 secretions)
  run_hash: 49d362dc8f138b82… (manifest.json)

### A4 (currency metabolites skipped) ###
host-map complete: 62 exact / 6 annotation / 0 normalized / 155 unmatched (of 223 secretions)
  run_hash: 49d362dc8f138b82… (manifest.json)

### A1 (entries capped at 100) ###
host-map complete: 22 exact / 3 annotation / 0 normalized / 75 unmatched (of 228 secretions)
  run_hash: 49d362dc8f138b82… (manifest.json)
```
```
run_hash  base: 49d362dc8f138b826ce289d915995eb78aafe9345c06cc36d0c30ff97849abb1
run_hash  A4  : 49d362dc8f138b826ce289d915995eb78aafe9345c06cc36d0c30ff97849abb1
run_hash  A1  : 49d362dc8f138b826ce289d915995eb78aafe9345c06cc36d0c30ff97849abb1
ALL THREE IDENTICAL: True

map_spec identical base/A4/A1 : True
match_behavior digest         : sha256:6f6f8b856d9ae50070edd865f8c7763620c8e56ab00b4631745b75cd2092667f
  identical across all three  : True

base  interface_map= 67  needs_review= 6  summary.ifmap_checksum=sha256:263176e4d9ca356
A4    interface_map= 62  needs_review= 6  summary.ifmap_checksum=sha256:d1157351339a079
A1    interface_map= 22  needs_review= 3  summary.ifmap_checksum=sha256:8f232858a664cd1

A4 dropped from auto-admitted interface map: 5  ['co2_e', 'h2o_e', 'h_e', 'nh4_e', 'pi_e']
A1 dropped from auto-admitted interface map: 45 e.g. ['galur_e','glc__D_e','glcur_e','gln__L_e',
                                                     'glu__L_e','gly_e','glyb_e','glyc_e']
```

The **exact self-contradiction from round 1 returns**: `summary.interface_map_checksum` moves
(`263176e4…` → `d1157351…` / `8f232858…`) while `run_hash` does not. The manifest again disagrees
with itself about whether the artifact changed.

### Why the probe cannot see these

The digest measures **one fixed, small, synthetic instance**: ~16 secretions, 18 host exchanges,
2 members, ids drawn from a made-up vocabulary (`xmet`, `ord`, `ambig`, `fbk`, `ste`, `sfx`, `hx`).
Two whole classes of behaviour are therefore structurally invisible:

1. **Scale-dependent behaviour.** Any cap, truncation, pagination, `if len(...) > N`, or lazy/partial
   index build with a threshold above ~20 is a no-op on the fixture and a mutilation of a real run
   (228 secretions, 95–229 host exchanges). A1 and A2 are this class.
2. **Vocabulary-dependent behaviour.** The fixture contains none of the real BiGG identifiers, so any
   rule keyed on actual metabolite names is invisible. A4 is this class — and it is the most
   realistic of all three, because **CMIG already ships `--exclude-metabolites` and
   `--include-currency-metabolites`** on the host-coupling surfaces. Wiring the same policy into
   `host-map` is an obvious next feature, and it would silently invalidate every published host-map
   fingerprint.

`test_the_probe_fixture_still_distinguishes_every_decision_point` is a good test and does not help
here. I read it: it is a closed list of assertions, one per decision point that **already exists**
(`ord_e` is annotation, `ambig_e` is unmatched, `ste__d_e` is unmatched, …). It guarantees the
fixture keeps distinguishing the *known* decisions. It cannot assert anything about a decision point
nobody has written yet — which is precisely where A1/A2/A4 live.

Note also that the pinned canary `PINNED_BEHAVIOR_DIGEST` (`tests/test_host_map_behavior_digest.py:53`)
is the *same* digest, so it has the *same* blind spot. There is no second line of defence: A1, A2 and
A4 all pass the full test suite.

### Assessment of the mechanism choice

The fixer's rejection of `inspect.getsource` is well-argued and I accept the two measurements that
bite (comment-only edits move a source hash; bytecode-only installs raise `OSError`). But the
trade was **total coverage → partial coverage**, and the report characterises the residual risk as
"probe-limited (mitigated)". These three results say the residual risk is not mitigated to the level
the CHANGELOG then claims. Both mechanisms have a real hole; the difference is that `getsource`'s
hole is *false positives* (annoying, safe) and the probe's hole is *false negatives* (silent, unsafe).
For a tool whose stated axiom is "a silently wrong number is worse than a crash", that asymmetry
matters.

### Minimal patch — stop trying to certify the implementation from the input side

Enumerating the matcher's behaviour will always be incomplete; the fixture is a model of the code,
and models omit. The reliable move is to fingerprint **the answer**, which the manifest already
computes and then throws away in `summary`:

```diff
--- a/cmig/cli/main.py
+++ b/cmig/cli/main.py
@@ def _cmd_host_map(...)
     _emit_workflow_manifest(
         out, "host_map",
         lambda: _host_map_hash_components(args, taxonomy, tax_dir),
+        # run_hash certifies "same question"; result_digest certifies "same answer". No
+        # input-side fingerprint can certify an implementation it only models, so the answer is
+        # fingerprinted directly and a re-run must reproduce BOTH.
+        result_digest=mapping_checksum({
+            "counts": {...}, "entries": [...],      # the full HostMapResult, not just the map
+        }),
```
with `write_workflow_manifest` recording `result_digest` as a top-level field (outside `run_hash`,
exactly like `env_lock`), and `cmig inspect-run` recomputing it from the artifacts on disk and
failing on mismatch. Then:

* a reader re-running a published `host_map` compares `run_hash` (inputs) **and** `result_digest`
  (output). A1/A2/A4 all move `result_digest`, whatever the probe does or does not model;
* the probe remains valuable as the cheap early warning that fires at *manifest-emission* time;
* no fixture has to be complete for the guarantee to hold.

Keep `match_behavior` — it is genuinely useful and it caught 5 of my 8 probes. Just stop asserting
in the CHANGELOG that it is total. At minimum, correct `CHANGELOG.md:50` to something like
"Changes to the matcher's modelled decision points move the hash", and record the known limitation
next to `HOST_MAP_BEHAVIOR_PROBE_VERSION`.

---

## 2. "Output-identical refactor" — CONFIRMED, on two pairs

Making four inert constants load-bearing is exactly the kind of change that quietly alters
behaviour, so I ran the **actual pre-fix matcher** (`host_map.py` sha
`e71b5d1a60dbc007c11737d2038bdeb67f5e91d92a7d48c03c96f9ca46ded79c`, saved before the fixer touched
the file) against the post-fix one through the real CLI, on the fixer's pair **and** a second pair it
did not test.

```
PAIR 1 (host iHN637 / pool iYO844)          PAIR 2 (host iYO844 / pool iHN637)
  host_exchange_map.csv    BYTE-IDENTICAL     host_exchange_map.csv    BYTE-IDENTICAL
  host_interface_map.json  BYTE-IDENTICAL     host_interface_map.json  BYTE-IDENTICAL
  host_map_summary.json    BYTE-IDENTICAL     host_map_summary.json    BYTE-IDENTICAL

pair1: ifmap_checksum pre=sha256:263176e4d9ca356b4 post=sha256:263176e4d9ca356b4  same=True
pair2: ifmap_checksum pre=sha256:263176e4d9ca356b4 post=sha256:263176e4d9ca356b4  same=True
pair1: run_hash pre=c76e603fa4b0e908… post=49d362dc8f138b82…  moved=True  (deliberate)
pair2: run_hash pre=2fd990ae4e7a2607… post=a5ddb2ed0210e59b…  moved=True  (deliberate)
summary counts identical on both pairs: True
```

Pair 2 exercises a different code path (2 annotation matches vs 6, 95 secretions vs 228, and the
host/pool roles swapped). **The refactor is genuinely behaviour-preserving.** Only the fingerprint
moved, once, as intended.

---

## 3. Gate blind spot — CLOSED

Editing `_COMPONENT_FIXTURES` the way the real component grew (adding a sub-key to `map_spec`):

```
→ workflow-envelope drift: published workflow run_hashes no longer reproduce.
  [DRIFT] kind 'host_map': stored input no longer matches the declared component fixture
```
rc=2. Before the fix this reported 13/13 OK.

`golden_components()` reference leak, tested at both depths:
```
top-level leak : False
nested leak    : False
fixture intact : True
=> deep copy holds: True
```
Both closed. The ordering choice is also right — the new check runs **last**, so a widened or
narrowed contract still reports its own more specific reason rather than the generic fixture message.

---

## 4. Frozen hash and re-bless scope — confirmed, but the scope check misses three kinds

### Confirmed by execution, not by reading

The fixer **added a key to the solve manifest payload** (`manifest_scope: "solve"`), so reading a
test assertion is not enough. I ran the real thing:

```
$ cmig solve-fixture --solver gurobi
  run_hash: 29844e2910360332…
run_hash        : 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab
FROZEN expected : 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab
UNCHANGED       : True
manifest_scope  : solve | schema: 2.0
scope key is OUTSIDE the hashed components: True
```

Re-bless scope, all 13 golden entries against the values I recorded in round 1:
```
host_map                         MOVED  989b6207bc8b -> 4cd3fd31caed
abundance_impact … sweep         same   (12 kinds unchanged)
MOVED KINDS: ['host_map']
```
Float probe unchanged. Both surface claims hold.

### F6 [P2] — what that check misses: the F2 fix silently moved three more kinds

F2 changed `host_spec_component` to hash `Path(x).name` instead of the full path. That component is
recorded by **five** kinds, so five kinds' **real published run_hashes** moved:

```
host_microbe_bigg        real hash moves: True   5dd35e56c197 -> d9d47bc8e0d1
host_search_bigg         real hash moves: True   56c46db78851 -> aa7def5c68ef
host_ko_impact           real hash moves: True   4634af04c32f -> 8b1b52abb31e
host_map                 real hash moves: True   b9d5963b5cb0 -> fc9bd676681d
publication_benchmark    real hash moves: True   3c6e9bab55c3 -> b775531698f6
```

`CHANGELOG.md` names only `host_map` and `publication_benchmark` as breaking. The `host_spec` bullet
describes the change but names no kinds and says nothing about re-deriving. **A reader holding a
published `host_microbe_bigg`, `host_search_bigg` or `host_ko_impact` run_hash is not told it moved.**

And the drift gate structurally cannot catch it. The envelope golden's `host_spec` fixture is a
**hard-coded literal** (`workflow_envelope_golden.py:90`, `"host_model": "golden/host.xml"`), not
built by `host_spec_component`. So the gate re-derives from a literal that no longer reflects what
the builder produces, reports "only `host_map` moved", and that statement is true of the synthetic
fixtures and false of reality.

This generalises: **every component builder** — `host_spec_component`, `medium_component`,
`bundle_component`, `pool_model_checksum` — is mirrored in the golden as a literal. A change to any
builder's *shape* moves real hashes invisibly to the gate. This is the same species as the original
P0 (a described input standing in for a derived one), one level up.

Patch — make the fixtures derive from the builders, so the gate sees builder changes:
```diff
-    "host_spec": {
-        "host_model": "golden/host.xml",
-        "host_model_checksum": "sha256:2222",
-        ...
-    },
+    "host_spec": host_spec_component(
+        host_model="golden/host.xml", host_model_checksum="sha256:2222",
+        host_objective="biomass_host", interface_map="golden/interface.json",
+        interface_map_checksum="sha256:3333", exchange_suffix="_e",
+        exclude_metabolites=["co2", "h", "h2o"], keep_host_uptake=True,
+    ),
```
(and the same for `medium`/`bundle_spec`). Re-blessing then correctly reports every kind whose real
hashes moved. Independently: add the three missing kinds to the CHANGELOG entry.

---

## 5. F5 — I accept the REJECT

The fixer is right and I was wrong. `_resolve_taxonomy` (`publication_benchmark.py:78-87`) is called
at line 349, **before** the checksum, and rewrites `file` to an absolute resolved path; and
`taxonomy_model_checksum` excludes the `file` key from `taxonomy_metadata`, so the absolute path
never enters the hash. Reproduced on the exact relative layout my F5 claimed would fail:

```
taxonomy 'file' column (relative): ['pool/iYO844.xml']
standalone  host-map checksum: sha256:91e7d08534bd9b0c421e8d4bbb74c45c9fa4f06155bfa807fec59135aa97a86c
pub-benchmark      checksum: sha256:91e7d08534bd9b0c421e8d4bbb74c45c9fa4f06155bfa807fec59135aa97a86c
EQUAL: True
```

Exactly the value the fixer reported. My `ValueError` came from my own component-level
reconstruction calling line 354's checksum without line 349's resolution — a defect in my harness,
not in the code. **F5 withdrawn.** This also strengthens C6: cross-surface equality holds for
relative taxonomy layouts, not only absolute ones.

---

## 6. Gates

```
854 collected / 851 passed / 2 skipped / 1 failed
FAILED tests/test_render.py::test_render_client_passes_project_rlib
```
The single failure is the pre-existing `.Rlib` path assertion (confirmed unrelated in round 1;
neither `tests/test_render.py` nor `cmig/render/client.py` is in the diff). Test count grew
823 → 854 (+31), consistent with the new `test_host_map_behavior_digest.py`.

---

## 7. Open items

1. **P0 — the probe's blind spot** (§1). Three realistic changes alter the published interface map
   under a bit-identical `run_hash`. Recommend the `result_digest` route; at absolute minimum,
   retract the CHANGELOG's totality claim so the guarantee is not oversold.
2. **P2 — F6, undisclosed blast radius** (§4). Three kinds moved without being named, and the gate
   cannot see builder-shape changes because its fixtures are literals.
3. **Accepted and closed:** the original F1 class (all 12 fixer perturbations + my 2 now move the
   hash), F2, F3, F4, the gate fixture blind spot, and the output-identical refactor.
4. **Withdrawn:** F5.

## 8. Could not verify

- **Whether A4-style currency filtering is actually planned.** I argue it is realistic because
  `--exclude-metabolites` / `--include-currency-metabolites` already exist on the host-coupling
  surfaces; I did not find a ticket proposing it for `host-map`. The finding does not depend on it —
  A1 and A2 are equally ordinary — but the "most realistic" label on A4 is my judgement, not a fact.
- **A full `publication-benchmark` end-to-end run** (multi-leg solve + dFBA + host coupling) remains
  outside the time budget; §4's blast-radius numbers are component-level hashes computed from the
  real builders, not from a completed benchmark.
