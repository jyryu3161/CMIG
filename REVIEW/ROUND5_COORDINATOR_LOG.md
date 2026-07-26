# Round-5 coordinator verification log

Baseline (main @ eec5a55): `pytest -q tests/` exit 0, full suite green.

## Cross-checks performed by the coordinator

### CC-1 — P3 claim: `test_render_client_passes_project_rlib` is a pre-existing failure
**Partly confirmed, and more precise than the claim.**
- Full suite on main: **passes** (baseline exit 0).
- Isolated: `pytest -q tests/test_render.py -k project_rlib` → **FAILS**
  `ValueError: '--out' is not in list` at `tests/test_render.py:113`.
- So it is not a plain pre-existing failure; it is an **order-dependent test**
  whose blanket `subprocess.run` monkeypatch also intercepts an unrelated
  `platform.platform()` → `uname -p` call. In full-suite order something has
  already populated the platform cache, so the stray call never happens.
- Verdict: real defect, tag **P2 (test integrity)** — a test that only passes in
  one ordering cannot certify anything. Fix by making the monkeypatch assert on
  the R invocation specifically instead of every `subprocess.run`.

### CC-2 — P3 F1 [P0]: failed abundance-impact solves plotted as real zeros
**CONFIRMED by direct code inspection.**
- `cmig/cli/main.py:2462-2472` — the `except Exception` handler appends a row with
  `community_growth: 0.0`, `target_member_exchange: 0.0`,
  `community_target_exchange: 0.0`, `target_influence_share: 0.0`,
  `target_secretion_share: 0.0`, `target_member_contribution: 0.0` and
  `status: <failure>`. Every scientific field is fabricated as a hard zero.
- `cmig/cli/main.py:4949-4952` — `valid_rows` filters **only** on
  `_optional_float(row.get("target_abundance")) is not None`. `status` is never
  consulted.
- `cmig/cli/main.py:4954-4965` — each series then applies
  `_optional_float(...) or 0.0`, so even a `None` would become 0.0.
- Net effect: a solve that failed is drawn as a real zero-growth / zero-flux data
  point, indistinguishable from a measured collapse. The CSV carries `status` and
  is honest; the figure is not. **P0 upheld.**

### CC-3 — P3 F3: stale `search_unevaluated.csv` survives into the next run
**CONFIRMED structurally.**
- `cmig/cli/main.py:4003` and `:4531` write `search_unevaluated.csv` only when the
  run actually produced unevaluable candidates; `:4069` / `:4640` likewise add it
  to the artifact list only `if result.unevaluated`. Nothing deletes a previous
  run's copy.
- The correct in-repo pattern exists and is used by the solve path:
  `cmig/io/solve_output.py:238-244` treats `manifest.json` as a commit marker,
  unlinks it first, then removes `KNOWN_SOLVE_ARTIFACTS - set(artifacts)` before
  publishing. The search paths simply do not do this.
- Consequence: re-using one `--out` for two searches yields a directory whose
  manifest describes run 2 while an orphan file from run 1 sits beside it. Upheld.
- Fix direction: give the search paths the same known-artifact cleanup, ideally by
  reusing the solve-path helper rather than duplicating the logic.

### CC-4 — codex P3 F1 [P0]: 6-decimal canonicalization collides distinct inputs
**ACCEPTED as a real defect, but the fix is CONSTRAINED. Read this before patching.**

Codex demonstrated that `canonicalize_floats(..., 6)` maps any input below 1e-6 to
`0.0`, so distinct answer-determining inputs share one hash. The realistic case is
not exotic: **solver tolerance** is routinely 1e-6 / 1e-7 / 1e-9, and switching it
changes the numbers while leaving the run_hash identical. That defeats the
manifest's central claim.

The naive fix (represent floats losslessly) would move **every** hash, including
the frozen 11-component `community_solve` hash `29844e29…cef29ab` that
`golden verify` (SC-5) protects. That is a contract break, not a fix.

Coordinator ruling — do it in this order:

1. **Split the problem by contract.** `cmig/core/manifest.py` (11-component solve
   hash) is frozen and protected by `golden verify`. `cmig/core/workflow_manifest.py`
   is schema 1.0, newer, and **not** protected by `golden verify`. The
   growth_fraction / target-weight / solver-tolerance collisions live in the
   workflow envelope and can be fixed there **without touching the frozen hash**.
   Do that first — it removes the realistic-risk collisions.
2. **For the frozen solve hash, try the backward-compatible scheme first:**
   emit `round(x, 6)` when `round(x, 6) == x`, else a lossless representation.
   Every value that is already exactly 6-decimal keeps its current serialization,
   so existing hashes are preserved. **This is not guaranteed safe — verify
   empirically**: the 3-member golden fixture records `abundance = 0.333333`, and
   if the runtime actually passes `1/3` (= 0.3333333333333333) then
   `round(x,6) != x` and the frozen hash WILL move. Run `golden verify` and check.
3. **If step 2 moves the frozen hash, STOP.** Do not re-bless it in this pass and
   do not weaken `golden verify`. Instead: leave the solve-level hash as is, record
   the residual limitation explicitly in the manifest documentation (inputs below
   1e-6 are not distinguished at solve level), and DEFER the versioned migration
   with a written proposal. A documented limit beats a silent contract break.
4. Add a regression test that pins the collision behaviour you end up with, so the
   decision is encoded rather than remembered.

**Known downstream interaction:** track P4 is building a drift gate that pins
workflow-envelope hashes. If step 1 changes that serialization, P4's golden values
must be regenerated — and the gate *firing* on this change is the gate working
correctly, not a failure. Sequence P3's envelope change before P4's re-bless.

### CC-5 — `test_render_client_passes_project_rlib` has TWO independent defects
Three sources converged on this test from different angles, and they are not the
same bug:
1. **Order dependence** (coordinator, CC-1): fails in isolation on `main` with
   `ValueError: '--out' is not in list` — the blanket `subprocess.run` monkeypatch
   also swallows an unrelated `platform.platform()` → `uname -p` call.
2. **Directory-name dependence** (codex P3, P4 implementer): asserts the resolved
   R library path ends with `/CMIG/.Rlib`, which is false in any checkout not
   literally named `CMIG` — so it fails in every worktree.
On `main`, in full-suite order, both conditions happen to be satisfied, which is
why the baseline is green. Track P3 owns fixing both; P4 correctly identified it
as not caused by its own changes.

### CC-6 — codex P2 F1 [P0]: the GUI drops dFBA's "NOT interpretable" verdict
**CONFIRMED by direct code inspection of `cmig/gui/views.py`.**
- `load_dfba_summary(payload, *, run_dir)` reads exactly four fields from the
  summary: `status`, `final_t`, `final_biomass`, `final_concentrations`. It never
  reads `warnings` and never reads `n_untracked_uptake`, then sets the row to
  `status` and prints `dFBA loaded: {run_dir}`.
- `dfba_request()` builds `{model, out_dir, initial, t_end, dt, initial_biomass}`
  — there is no `--close-untracked-uptake` equivalent anywhere in the GUI surface.
- So the CLI can determine that a run's substrate/Km experiment is *not
  interpretable* (untracked uptake substrates letting growth proceed on nutrients
  the experiment does not control) and the GUI will still present it as an
  ordinary `completed` result with a biomass number and a timecourse figure.
- This is not a re-report of the previously fixed CLI honesty gap; it is the GUI
  half of it, which was never closed. **P0 upheld** — same class as CC-2: the
  honest signal exists in the data and the presentation layer discards it.
- Fix direction: `load_dfba_summary` must surface `warnings` / `n_untracked_uptake`
  prominently (not as a tooltip), and the GUI must expose the uptake-closing
  control so the user can actually make the run interpretable rather than only
  being told it is not.

### CC-7 — codex P1 F1 [P0]: the id normalizer destroys D/L stereochemistry
**CONFIRMED, and broader than reported.** `cmig/core/namespace.py:365-378`.

The heuristic is: if the last `__`-separated token starts with an uppercase
letter, treat it as a MICOM member (taxon) suffix and strip it. BiGG's
stereoisomer convention is exactly `__D` / `__L` — a single uppercase letter — so
every stereo descriptor is silently destroyed. Measured directly:

```
lac__D_e     -> lac        lac__L_e     -> lac
arab__D_e    -> arab       arab__L_e    -> arab
ala__D_e     -> ala        ala__L_e     -> ala
glc__D_e     -> glc        ac_e         -> ac
```

The reviewer reported `arab`/`lac`/`ala`; **`glc__D` collapses too**, so the blast
radius includes the most common carbon source in the bundled models, not only
niche amino acids.

Why it is P0 and not cosmetic: D-lactate and L-lactate are different molecules
with different transporters. `solve_bigg_host` normalizes *both* the reviewed
interface-map keys and the microbial availability with this function, so a
reviewed D-isomer mapping matches L-isomer availability and opens the D exchange.
The host then takes up — and grows on — a molecule it cannot transport. That is a
fabricated biomass number, produced by the reviewed-interface-map path that exists
specifically to be trustworthy.

Relation to prior rounds: round-4's known-open item 9 recorded the *symptom*
("interface map ships D↔L swaps in the same flat dict as exact matches"). This is
the **root cause** underneath it, one layer down, and it was not fixed.

Fix direction (minimal): the collision is single-character stereo descriptors vs
multi-character taxon names. Only strip the trailing `__<token>` when the token is
a plausible taxon (length > 1), and/or never strip a token in the known stereo set
`{D, L, R, S}`. Guard with a regression test asserting `lac__D_e` and `lac__L_e`
normalize *differently*, plus an end-to-end assertion that a D-only host offered
L-only microbial availability does **not** grow.

**Merge-order note:** track P4 also edits `cmig/core/namespace.py` (hoisting
`NORMALIZE_EXCHANGE_PREFIX` / `NORMALIZE_COMPARTMENT_SUFFIXES` to module
constants). Expect a small conflict in this file; P1's semantic fix takes
precedence and P4's constants should be preserved around it. P4's `map_spec`
derives from those constants, so after P1's fix the envelope golden must be
re-blessed — the drift gate firing here is correct behaviour.

### CC-8 — Opus P2 F3 [P0]: gene-KO argv is built on the worker thread
**CONFIRMED by direct code inspection.** `cmig/gui/app.py:935-944`.

`run_gene_ko_search` snapshots `model_dir`, `members`, `target`, `member`, `genes`
and `out_dir` in the enclosing scope — correctly — and then builds the rest of the
argv *inside* `_job(ctx)`, which executes on the `ThreadPoolExecutor` worker:

```python
def _job(ctx: JobContext) -> dict[str, Any]:
    argv = [... "--max-genes", str(self.search_view.ko_max_genes_spin.value()),
                "--top-k",     str(self.search_view.top_k_spin.value()), ...]
```

Two distinct defects in one expression:
1. **Late read → the executed analysis is not the requested one.** When the pool is
   busy the job starts later than the click, so a spinbox edit in between silently
   redefines the run. The reviewer reproduced it with `JobRunner(max_workers=2)`
   saturated: clicked at 50/3, executed at `--max-genes 5000 --top-k 97`. The
   manifest records what ran, so provenance is internally consistent — which makes
   it worse, not better: nothing anywhere contradicts the user's belief about what
   they launched.
2. **Cross-thread QWidget read**, which is undefined behaviour in Qt regardless of
   the race.
Every sibling `run_*` snapshots first, so this is a local slip, not a design
choice. Fix: hoist both `.value()` reads next to the other snapshots. **P0 upheld.**

### CC-9 — two P2 negatives worth protecting from a wasteful "fix"
- **Do NOT migrate `QTableWidget` → `QTableView`/`QAbstractTableModel`.** Measured
  worst reachable cases: search table (capped at 100 rows) 0.7 ms; 300-row
  profile/FVA 1.9 ms; 330 iML1515 exchanges 0.3 ms; 2712 rows 3.0 ms; jobs panel
  at 1000 tracked jobs 6.0 ms per refresh (1.2 % duty). All inside one frame. The
  category-5 concern does not reproduce here; a migration would be cost with no
  benefit.
- **The real event-loop stall is elsewhere:** the Constraint Sandbox solves
  synchronously in its slot — **2190 ms measured on the 3-member golden fixture,
  0 heartbeat ticks** — and auto-fires 500 ms after any table edit. That is the
  blocking defect to fix.

### CC-10 — GUI↔CLI parity: numbers pass, reporting fails
Both reviewers agree the computation is faithful. Opus measured bit-identical
`score` / `target_flux` / `community_growth` and an identical `run_hash`
(`338686edd7f37907…`) between GUI Run Search and `cmig search` on the same pool,
stable across `--out` dirs **and across a Korean-named model directory** (so the
CJK-path concern does not reproduce for this path). No silent default divergence
for any parameter the GUI actually sends.

The failure is exposure, not arithmetic: ~15 CLI parameters unreachable from the
GUI (notably `--direction`, `--targets`, `--medium`, `--growth-fraction`), warnings
and diagnostics dropped, and manifests written to an unnamed OS temp dir never
shown to the user. Treat "parity" as PASS for numbers, FAIL for reporting — and do
not let a fixer "fix" the numbers.

### CC-11 — P1 F1 / codex P1 F3 [P0]: a custom medium is silently not applied
**CONFIRMED, both reviewers converged independently, and the codebase documents
the defect against itself.** This is the most serious finding of round 5.

`cmig/core/medium_spec.py:96-116` — `apply_medium_checked` computes
`known = set(dict(community.medium))` and then keeps only
`{ex: v for ex, v in spec.uptake.items() if ex in known}`. But `model.medium`
enumerates **currently-open uptakes**, not the model's exchange reactions. So an
exchange that is currently closed can never be opened by a medium. Opus measured
26 of 257 `EX_*_m` reactions present in `community.medium` — i.e. ~90 % of
nutrients are unreachable, including acetate, butyrate, lactate, succinate and
glycerol, which is most SCFAs and most carbon sources.

Two user-visible outcomes, both bad:
- `strict=True` → a factually false error ("not present in the target model") for a
  metabolite that *is* in the model.
- `--allow-unknown-medium` → the nutrients are **silently dropped** while the
  manifest still records the requested `medium_checksum` and mints a distinct
  `run_hash`. Measured: `solve --medium <file> --allow-unknown-medium` gave growth
  **0.5849, identical to the no-medium run**, while printing `medium=custom` and
  stamping `medium_checksum: medium:842bb87d…`. A run that did not use the medium
  is published as a run on that medium, with a unique fingerprint certifying it.

The correct implementation already exists — `apply_medium_translated`, whose own
docstring at `cmig/core/medium_spec.py:207` says *"Unlike `apply_medium_checked`,
this does not gate on `model.medium`"*. The round-4 fix wired it into
**`strain-growth` only** (`cli/main.py:2155-2226`). Every other consumer still
calls the broken function:

```
cmig/core/search_product.py:209, 563, 640, 685   (all search paths)
cmig/core/host_coupling.py:214                    (host-microbe)
cmig/core/medium_spec.py:86                       (apply_medium)
cmig/cli/main.py:2396                             (solve)
cmig/service/engine_service.py:149                (service facade → the GUI)
```

Consequence measured by Opus: the same medium file gives **growth 0.881561 via one
subcommand and 1.125065 via another — 27.6 % apart**. And because
`engine_service.py` is in the list, the GUI inherits it too, so this is not a
CLI-only defect.

Fix direction: make `apply_medium_checked` gate on the model's exchange
**reactions** (the `apply_medium_translated` semantics) and route every consumer
through one path, so the namespace translation and the open-a-closed-exchange
behaviour cannot diverge by subcommand again. Expect existing tests that encoded
the old behaviour to need deliberate updates — document each one. The golden
fixture uses the micom default medium and should be unaffected; verify that.

### CC-12 — P4 verification: the self-declared weak point IS exploitable [P0]
The Opus verifier was tasked to attack `map_spec`'s reliance on a hand-bumped
`HOST_MAP_MATCH_POLICY_VERSION`, and **succeeded through the real CLI on real
GEMs**. Changing one comparison in `build_host_map` (`cmig/core/host_map.py:156`,
the secretion criterion), leaving the policy version and every `map_spec` field
untouched:

```
run_hash BEFORE : c5a6c402dfa84b4d…c66257a5   interface_map: 67 entries
run_hash AFTER  : c5a6c402dfa84b4d…c66257a5   interface_map: 11 entries
run_hash IDENTICAL: True    map_spec IDENTICAL: True
```

56 metabolites silently dropped from the auto-admitted interface map under an
unchanged fingerprint. A second independent break via `match_order` relabels all
six D/L stereoisomer needs-review entries, also under a stable hash. Damningly,
the manifest's own `summary.interface_map_checksum` **did** move while `run_hash`
did not — the artifact contradicts itself.

Root cause: four `map_spec` fields (`match_order`, `secretion_criterion`,
`annotation_requires_unique_target`, `annotation_sources`) are inert literals that
**no code path reads**. They describe the policy; they do not derive from it.
10 perturbations were tried, 2 reproduced end-to-end, the other 8 are equally
uncoupled but need different models to bite.

This is a P0 in P4's own deliverable and must be fixed before merge. The verifier
supplied a patch fingerprinting the matching implementation via
`inspect.getsource`, removing the hand-bump dependency.

Also confirmed: **C12 packaging is real** — hatchling was driven through the PEP
517 backend (without `uv`); the golden ships in both wheel (44,057 bytes) and
sdist, byte-identical to source, and `assert_envelope_golden()` passes from the
unpacked wheel with all 13 kinds. Note `scripts/audit_distribution.py` is an
allowlist checker and can never assert presence, so the build was necessary.

Tally: 8 CONFIRMED · 4 PARTIAL · 0 refuted. The PARTIALs are honest: C1/C3's
literal hashes are path-string-sensitive and appear in no test or fixture, so they
are unverifiable as stated — the underlying properties were verified instead and
held.

### CC-13 — COORDINATOR ERROR: I ran two verifiers concurrently in one worktree
I dispatched the Opus and codex P4 verifiers into `CMIG-wt-followup` at the same
time, both authorised to make destructive perturbations. The Opus verifier
detected the collision itself, moved its remaining work into a private copy, and
flagged it. **This is precisely the mistake recorded in round 1** (`FINAL_REPORT`:
"evaluator B ran partly against a worktree that evaluator A was concurrently
modifying"), and I repeated it.

Damage assessment (coordinator-run, after codex died):
- `golden verify` green on both solvers
- `golden verify-envelope` 13/13 OK — no lingering serialization perturbation
- 134 P4 tests pass; `ruff` clean
→ no tracked file was left perturbed. codex's scratch `.verify_p4/` (2.0 MB) was
removed by the coordinator after inspection (run outputs + a distribution build).

The codex P4 verification itself **did not complete**: the provider's safety
filter terminated it ("flagged for possible cybersecurity risk"), because my
prompt asked it to construct a change that alters output while leaving the hash
unchanged — which reads as tampering instructions out of context. Rerun required
with the request framed as a reproducibility-completeness check, and **sequenced
after** the P4 fixer rather than concurrently.

### CC-14 — P2 fix landed; coordinator spot-check of the headline P0
`cmig/gui/app.py` `run_gene_ko_search` now reads both spinboxes **before** the
closure and the closure consumes the captured strings:

```
26:  max_genes = str(self.search_view.ko_max_genes_spin.value())
27:  top_k     = str(self.search_view.top_k_spin.value())
32:  def _job(ctx): ...
40:      "--max-genes", max_genes,
41:      "--top-k", top_k,
```

That is the minimal correct fix and it matches every sibling `run_*`. **CC-8
closed.**

Fixer totals: P0 12/12 fixed, P1 9 fixed + 3 deferred, P2 6 fixed + 4 deferred,
0 rejected on the merits. 26 new tests in `tests/test_gui_round5_p2.py`, 22 of
which were captured failing before the fix. Frozen hash untouched by construction
— zero lines changed under `cmig/core/`, `cmig/cli/`, `cmig/io/`.

Sandbox event-loop blocking, same 20 ms heartbeat detector on the real 3-member
golden fixture with real Gurobi: **2069 ms → 0.5 ms**, heartbeat ticks during
solve **0 → 97**, worst gap ≥2069 ms → 102.5 ms. Residual attributed to GIL
contention with the Gurobi C call — the verifier is re-measuring and testing that
explanation rather than accepting it.

Three fixer judgement calls the coordinator endorses:
- Member vs community exchange are now shown **side by side** (7.144 next to 0.0)
  rather than swapping which one is displayed. The contradiction stays visible
  instead of being resolved by fiat — correct for a tool whose job is honesty.
- The GUI **refuses to auto-tick `--assume-bigg-namespace`**. That flag is a
  scientific-review bypass audit; setting it on the user's behalf would have been
  the worst available "fix".
- Multi-target is **rejected with a message** rather than routed through an
  unexercised GUI path in a fix pass.

Deferred with named owners, all defensible: encoding fix needs writer+reader
changed atomically and `cli/main.py` belongs to P3; table sorting deferred because
enabling it naively scrambles rows during fill (introducing a P0 hazard to fix a
P2); true cancel needs process isolation.

### CC-15 — CC-4 RESOLVED: collision closed AND the frozen contract held
Coordinator-verified independently, both directions:

```
$ cmig solve-fixture --solver gurobi          # real end-to-end run, not a unit test
run_hash: 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab
FROZEN MATCH: True

$ bounds 1e-7 vs 4e-7 through RunHashComponents
1e-07 b717ead00a3661d6821922e4…
4e-07 7fefdfeb548a031697695057…
COLLISION STILL PRESENT: False
```

This was the outcome I ruled *unlikely* in CC-4 — I expected to have to choose
between fixing the collision and preserving the frozen hash. The fixer found the
reason both are possible, and the reasoning is worth recording because it makes
the fix architecturally right rather than lucky:

The risk I flagged was that the fixture passes `1/3` at runtime, which is true —
`result.abundances` really is `0.3333333333333333`. But both
`golden_fixture._run_hash_components` and `io.solve_output.build_run_components`
**already round abundances to 6 decimals before building the components**. So
every float that reaches the frozen hash is exactly six-decimal, `round(x,6)==x`
holds throughout, and the serialization is byte-identical. Noise absorption
already lived at the boundary; the canonicalizer was doing it a *second* time and
destroying genuine input precision as a side effect. Removing the duplicate is
what fixed it.

Envelope schema bumped 1.0 → 1.1, with noise-rounding moved to the two envelope
components that genuinely carry solve-derived floats.

### CC-16 — P3 fix: two items of independent judgement worth keeping
1. **A reviewer patch rejected on measurement, not taste.** Both reports proposed
   a Gurobi licence probe (opus F7 / codex F9). The fixer measured that
   `gurobipy.Env()` *succeeds* under a size-limited licence — the limit bites at
   model size, not env creation — so the patch would not detect the case it was
   written for while making `available` look authoritative. Landing it would have
   been worse than the status quo. Deferred to the solver owner with the evidence.
   This is the correct use of a REJECT verdict.
2. **A defect neither reviewer found.**
   `test_review_regressions.py::test_profile_render_passes_rlib_to_rscript` carries
   the identical blanket `subprocess.run` monkeypatch as CC-1 and also fails in
   isolation (`TypeError: fake_run() got an unexpected keyword argument 'stdout'`).
   Both are now order-independent.

P3 totals: 14 ACCEPT · 3 ACCEPT-MODIFIED · 3 REJECT · 6 DEFER. Gates: ruff clean;
pytest **749 passed, 2 skipped, 0 failed** (this worktree's baseline was
728/2/**1 failed**, so the known render failure is now genuinely fixed rather than
tolerated); `golden verify` green on both solvers.

**Blocking sequence confirmed:** P3 changes workflow-envelope hashes by design, so
it must land **before** P4's re-bless. P4's drift gate firing on this is the gate
working.

### CC-17 — P4 fix landed; coordinator spot-check
`cmig/core/host_map_probe.py` present (14,556 bytes). `map_spec.match_behavior` is
now `{"probe_version": "1.0", "digest": "sha256:6f6f8b85…"}` — a fingerprint of
what the matcher actually *does*, not a literal describing it. Envelope gate 13/13
OK, `golden verify` green on both solvers, frozen hash `29844e2910360332…` intact
end-to-end via a real `solve-fixture`.

The fixer rejected the verifier's `inspect.getsource` proposal on measurement, and
two of the four concerns I raised in the brief turned out to be wrong — `getsource`
*does* work from a wheel and from zipimport. The two that did bite: a comment-only
edit moved the getsource hash while behaviour was unchanged (a gate that fires on
typo fixes trains readers to ignore it), and on a bytecode-only install it raises
`OSError`, which matters precisely because P4 shipped the golden inside the package
so the gate cannot silently skip. Recording this because my brief was partly wrong
and the fixer was right to check rather than comply.

It also found a blind spot in its own gate: `verify_envelope_golden` re-derived
from the *stored* input, so editing `_COMPONENT_FIXTURES` was invisible to it, and
`golden_components` handed out live references into the fixture dict. Both fixed.

### CC-18 — MERGE ORDER (final), and why
`id_normalization` in `map_spec` currently records
`uppercase_stereoisomer_suffix_folded: true` — i.e. the CC-7 defect is being
recorded as though it were policy. P1's fix flips that to false, which moves the
`host_map` envelope hash a second time. Therefore:

1. **P1** (`review/p1-domain`) — namespace stereochemistry + medium application.
   Changes `cmig/core/namespace.py`, which P4 also touched (constant hoisting):
   expect a small conflict; P1's semantics win, P4's constants are preserved.
2. **P3** (`review/p3-io-exc`) — float canonicalization + atomicity. Deliberately
   moves workflow-envelope hashes (schema 1.0 → 1.1).
3. **P2** (`review/p2-qt-ux`) — GUI only; zero lines under `cmig/core|cli|io`, so
   it cannot disturb 1 or 2.
4. **P4** (`feat/p4-manifest-drift`) — **last**, and its envelope golden is
   re-blessed only after 1–3 have landed, so the blessed values describe the final
   serialization rather than an intermediate one.

The drift gate firing during steps 1–3 is the gate working, not a failure. What
would be a failure is re-blessing before the semantic changes land.

Two frozen invariants to re-verify after every step, on **both** solvers (CC-15
taught this — checking gurobi alone let the osqp regression through):
`gurobi 29844e29…cef29ab` and `osqp a422eb89…404d3d9d`.

### CC-19 — P1 fix landed; coordinator spot-check of both confirmed P0s
**CC-7 closed.** Measured in the worktree:
```
lac__D_e  -> lac__d      lac__L_e  -> lac__l      D and L now DISTINCT: True
glc__D_e  -> glc__d      arab__D_e -> arab__d     arab__L_e -> arab__l
EX_ac_m__Escherichia_coli -> ac        # MICOM taxon suffix still stripped correctly
```
The fix separates stereoisomers without breaking the taxon-suffix stripping the
heuristic existed for.

**CC-11 closed.** Same `--medium` file, same 2-member community
(`iHN637`+`iYO844`):
```
before  apply_medium_checked    (solve/search)   growth=0.881561  EX_ac_m=None
        apply_medium_translated (strain-growth)  growth=1.125065  EX_ac_m=10.0   27.6% apart
after   both paths                               growth=1.125065  EX_ac_m=10.0   identical
```

Frozen gurobi hash `29844e2910360332…` re-verified end-to-end after the pass.

P1 totals: **17 fixed (10 P0, 1 P1, 6 P2), 6 deferred, 0 rejected** — every finding
in both reports reproduced. Suite 776 passed / 2 skipped / 1 known pre-existing
failure, 779 collected (up from 731).

### CC-20 — RELEASE NOTE required (user-facing consequence of CC-11)
**Any pre-existing CMIG run that used a custom medium is suspect.** Its
`medium_checksum` records a medium the run never actually applied, and it was
issued a distinct `run_hash` certifying that false provenance. This must appear in
the changelog and release notes — it is not enough to fix it forward, because
published results already carry the bad fingerprint. Affected surfaces: `solve`,
`search` (all four paths), `host-microbe-bigg`, `abundance-impact`, and anything
going through `engine_service` (i.e. the GUI).

### CC-21 — P1 deferrals to adjudicate at merge
Four P0-tagged items were deferred, each reproduced with numbers. The one needing
a coordinator decision is **`edges.parquet` abundance weighting** (opus F3 /
codex F2): the weight is an unlabelled per-taxon flux, so an edge's magnitude
inverts against its true community contribution (84.57 at abundance 0.1 vs 12.29
at 0.9, where the true contribution is 8.46 → 11.06). The fixer deferred changing
the *value* because it requires re-blessing the frozen golden `edges.parquet` on
both solvers, the two reviewers proposed **incompatible** `abundance is None`
contracts (weight 1.0 vs raise), and neither patch scales the FVA bounds. It
landed a unit disclosure in the manifest instead. The P1 verifier has been asked
for a recommendation on whether a wrong-magnitude edge weight in a published
parquet is too dangerous to defer.

Two further deferrals (`growth_feasible`, `analyze_pair` media) are real but
unreachable from any CLI subcommand or the GUI, and codex's own patches say they
must land together as one API redesign — deferring those is right.

### CC-22 — P3 final round complete and coordinator-verified
```
$ cmig golden verify
  [OK ] gurobi   [OK ] run_hash 29844e2910360332…
  [OK ] osqp     [OK ] run_hash a422eb89d019f917…
→ golden 이 설치 MICOM 버전·published run_hash 와 일치
```
The gate itself is now stronger: it **compares run_hashes**, which it did not before
— the P3 verifier was right that `golden verify` only checked `micom_version`, so a
golden hash could move while the gate stayed green. That hole is closed and a test
proves the gate fires.

Also verified by the coordinator: sweep cache-key rounding removed;
`medium_checksum` no longer rounds; `cmig/io/atomic.py` exists.

The OSQP regression root cause, stated precisely: the invariant needed is
`round(x, D) == x` where **D is the decimals that hash uses**, not a fixed 6.
`_run_hash_components` pre-rounded at 6 while osqp hashes at 4, so `0.333333` was
not a fixed point at 4 and took the lossless branch. `decimals` is now an explicit
parameter of both builders and all golden pins are parametrized over
`SOLVER_VARIANTS`. The fixer's own diagnosis of why its tests missed it — *every
pin was gurobi-only* — is the correct lesson.

It also found the shipped `expected/osqp/config.json` was internally inconsistent
(components stored at 6, hash computed at 4) so it **no longer reproduced its own
hash**; corrected, published run_hash unchanged.

**V2 confirmed as a real replay, then fixed:** `--tradeoff-fs 0.5000001,0.5000004`
shared one cache key, so the second point's solve was skipped and the first point's
value *and run_hash* were republished under the second's `condition_id`. The
`_axis_tradeoff_f` rounding meant the artifact could not even reveal the
substitution. Both roundings removed.

**Honest correction recorded:** V1b — `build_run_components` abundance pre-rounding
**stays**, because it is what makes the frozen hashes survivable. The earlier claim
"all sub-1e-6 inputs now separate" was too strong; the exact boundary is now
encoded in a test rather than asserted in prose.

**Test audit result: 4 of 32 new tests failed "would this catch deletion?"** — the
tautological one I flagged, plus three the fixer found itself. The most instructive:
a CSV zero-check passed *with the bug present* because `_finite_csv` renders `0.0`
as `"0"`. All four repaired. This validates making the audit mandatory.

P3 gates: ruff clean; **767 collected · 765 passed · 2 skipped · 0 failed**.

### CC-23 — merge conflict surface (measured, not predicted)
Files touched by more than one track:
```
P1 P3      cmig/core/medium_spec.py
P1 P3 P4   cmig/cli/main.py
P1 P3 P4   cmig/io/solve_output.py
P1 P4      cmig/core/namespace.py
   P3 P4   cmig/core/workflow_manifest.py
   P3 P4   tests/test_workflow_manifest.py
```
**P2 touches none of them** — its claim of a clean boundary (zero lines under
`cmig/core|cli|io`) is confirmed, so it can merge at any point without interacting.

Merge order stays **P1 → P3 → P2 → P4** (CC-18), with the full gate after each step
and both frozen hashes re-verified end-to-end on both solvers each time.

Branch snapshots: `review/p3-io-exc` = `ebc3eca`, `review/p2-qt-ux` = `2f5804a`
(work finished, committed). `review/p1-domain` and `feat/p4-manifest-drift` are
deliberately left **uncommitted** at `eec5a55` while their agents are still active —
committing them mid-flight would make `git diff` show clean and mislead the running
verifiers.

### CC-24 — P4 final round: `result_digest` catches all four independent breaks
| break | found by | pair | interface_map | run_hash | match_behavior | result_digest |
|---|---|---|---|---|---|---|
| A1 cap entries at 100 | Opus | iHN637+iYO844 | 67 → 22 | unmoved | unmoved | **MOVED** |
| A2 cap host index | Opus | iML1515+iYO844 | 144 → 73 | unmoved | unmoved | **MOVED** |
| A4 currency filter | Opus | iHN637+iYO844 | 67 → 62 | unmoved | unmoved | **MOVED** |
| eligibility by host upper bound | codex | iAF987+iYO844 | 40 → 38 | moved¹ | moved¹ | **MOVED** |

¹ only after the probe fixture was widened; *before* widening, only `result_digest`
caught it — which is the honest measure of which mechanism is doing the work.
"Output changed but nothing in the manifest moved" is now **NONE** on every pair
tested. `result_digest` is additive (not in `components`, not in `hash_components`),
and `inspect-run` recomputes it, saying on mismatch: *"a matching run_hash does NOT
make this run reproduced: run_hash certifies the inputs, result_digest certifies the
answer, and they disagree."*

codex's diagnosis was confirmed exactly: iAF987 has precisely two exchanges with
non-positive upper bounds (`EX_ac_e [-8.88, -6.84]`, `EX_fe3_e [-67.37, -49.21]`)
and the probe had `upper_bound=1000` everywhere. Fixture widened with those real
bounds; the decision-point test now asserts the regimes are *reachable* so the blind
spot cannot silently return.

**Golden fixtures are now builder-derived** (`medium_component`,
`host_spec_component`, `bundle_component`, `host_map_policy()`), fed deliberately
unsorted/unnormalized inputs so each builder's own normalization is part of the
fixture. Rebuilding immediately made the gate fire on exactly the five kinds that
had moved silently — the transcription hole is closed, and the blast radius is now
disclosed up front.

The CHANGELOG overclaim was corrected in **five** places, not one.

### CC-25 — THE DRIFT GATE PROVED ITSELF ON A REAL CHANGE
Integration branch `round5/integration` = main + P3 + P2 + P4. One conflict only,
in `cmig/core/workflow_manifest.py`: P3 replaced `write_text` with a staged
`os.replace`, P4's side was the untouched original. Resolved in P3's favour. The
merged module carries **13 kinds (P4) at schema 1.1 (P3)** — both survived.

Then, on the first real integration, the gate fired without being asked:
```
[DRIFT] float normalization probe (NaN / ±inf / -0.0 / rounding floor)
  first difference at character 609:
    golden … "at_rounding_floor":0.123456,"below_rounding_floor":0.1
    actual … "at_rounding_floor":"f64:0.1234565","below_rounding_floor":"…
```
That is P3's lossless `f64:` canonicalization being detected as an envelope
serialization change by P4's gate — a genuine cross-track change caught
automatically, not a synthetic perturbation. This is the deliverable the user asked
for in item 10, demonstrated on real work.

`golden verify` on the integration is green on **both** solvers with hash comparison
active (`29844e2910360332…`, `a422eb89d019f917…`), and ruff is clean. P4's reported
osqp mismatch was resolved by P3's fixture correction merging first, exactly as
CC-18's ordering predicted.

**Re-bless is deliberately deferred until P1 merges**, so the blessed values describe
the final serialization rather than an intermediate one.

### CC-26 — P1 merge rehearsed without disturbing its running verifiers
Used `git stash create` in `CMIG-wt-domain` to mint a snapshot commit
(`faa4026b`) **without moving HEAD or cleaning the worktree** — the 15 dirty paths
are still there for the two verifiers reading them. Branched it as
`scratch/p1-trial` and 3-way merged into `round5/integration`, then aborted.

Result: exactly two conflicting files, as CC-23 measured.

**1. `cmig/core/namespace.py`** — P4's hoisted constants vs P1's stereochemistry
fix. Resolution is a **combination, not a choice**: keep P4's
`NORMALIZE_EXCHANGE_PREFIX` / `NORMALIZE_COMPARTMENT_SUFFIXES` with its comment
explaining that the manifest reads the policy from code, and take P1's
`STEREO_DESCRIPTORS`, `_strip_compartment_suffix` helper and rewritten normalizer
body. **One thing must not survive:** P4's docstring paragraph asserting that
folding `glu__D → glu` is "deliberate for candidate suggestion". That statement is
now false and is the exact rationalisation that let CC-7 live; P1's replacement
text says why the descriptor must be preserved.

**2. `cmig/cli/main.py`** — 7 hunks. The important discovery: **P1 and P3 fixed the
same gene-KO defect independently**, and both chose NaN over the fabricated
`-baseline.score`. Their comments even reach the same conclusion in different words
("the reported -12.15 effect was just the baseline with a minus sign" vs "a finite,
large-magnitude, entirely plausible effect size that was never measured"). That
convergence from two separately-briefed tracks is strong evidence the fix is right;
the merge just needs one coherent version rather than both. P3's version
additionally suppresses the "rank 1 (largest effect)" headline when nothing was
evaluable, which P1's does not — so P3's is the superset and should win, with P1's
comment text preserved where it is clearer.

Merge order updated to **P3 → P2 → P4 → P1**, then a single envelope re-bless.
Deferring P1 to last is safe (its conflicts are with files already in place) and
avoids re-blessing twice. `round5/integration` currently sits at `45540d9`
(= main + P3 + P2 + P4) with the drift gate correctly firing on P3's `f64:`
serialization change, awaiting P1 and the re-bless.

### CC-27 — the osqp golden question, settled
Three sources reported this from different angles and they are all consistent once
sequenced:
- **P4** (and the P1 Opus verifier): `a422eb89…404d3d9d` was a **stale stored
  artifact that no code path reproduced** — captured at `golden_decimals: 4` while
  the builder pre-rounded at 6, so a real run recomputed `c491a6a8…`. Pinned by no
  test and invisible to `golden verify`, which compared only `micom_version`.
- **P3** fixed it by correcting the three stored abundance values to 4 decimals so
  the fixture reproduces its own hash again, **leaving the published hash value
  unchanged** — verified before writing.
- **Integration** (`round5/integration` = main+P3+P2+P4) confirms it: `golden
  verify` now compares hashes and reports `[OK] osqp run_hash a422eb89d019f917…`.

So the correct statement is: it *was* unreproducible, P3 made it self-consistent
without moving the published value, and the gate that should have caught it now
does. **Merge consequence:** P4's
`test_the_osqp_golden_is_stale_against_the_current_float_decimals_contract` pins
the stale state and therefore fails in integration — by design, since its author
wrote it to fail "the moment someone recaptures". It must be rewritten to assert
the new invariant (every shipped golden re-derives from its own stored components
at its own recorded decimals) rather than deleted.

### CC-28 — coordinator disclosure: I committed P4's worktree
The P4 fixer correctly detected that its work had been committed against its brief
and flagged it rather than reverting. **That was me**, deliberately, to create merge
bases (`git add -A && git commit` on each finished branch). It also verified what I
would have wanted verified: not pushed (no upstream on `feat/p4-manifest-drift`, no
remote ref contains `9ccb964`), commit hygiene clean (18 files, +4374/−79, no
`REVIEW/`, `runs/`, `.omc/`, scratch or logs), and the committed tree is the tree it
had validated. Its refusal to undo another actor's deliberate git action without
authorisation was the right call.

I had also *reverted* the same commits on `review/p1-domain` and
`feat/p4-manifest-drift` earlier, precisely because their agents were still active —
the P4 recommit came after its fixer finished.

### CC-29 — CORRECTION: `test_service_is_qt_independent` is not a code defect
I reported this as "the third order-dependent test" of the round. **That was wrong
and I am retracting it.** Evidence across four runs of the same integration tree:

| run | conditions | result |
|---|---|---|
| 1 | full suite, 2 codex verifiers + Opus agents running concurrently | **FAILED** |
| 2 | `-k "not envelope_golden"`, same load | passed |
| 3 | full suite, `--tb=long`, lighter load | passed |
| 4 | full suite, **0 codex processes** | passed |

The test is already subprocess-isolated and asserts `r.returncode == 0, r.stderr`.
Under run 1 the machine was spawning subprocesses from three codex sessions, several
Opus agents and pytest simultaneously; a failed spawn explains it and nothing in the
code does. **It was an artifact of my own orchestration load.** Recording it because
the tempting move — dispatching a fixer at a defect that does not exist — would have
cost a cycle and possibly produced a "fix" to working code.

Distinguishing this from the two genuine order-dependent tests
(`test_render_client_passes_project_rlib`,
`test_profile_render_passes_rlib_to_rscript`, both fixed by P3) required re-running
under controlled load rather than reasoning about it.

### CC-30 — integration is at its expected pre-merge state
Full suite on `round5/integration` (= main + P3 + P2 + P4), 0 concurrent load:
**9 failures, and every one is a known, intended merge-time item.**
- 8 × `tests/test_workflow_envelope_golden.py` — the drift gate correctly refusing
  to certify P3's `f64:` serialization change until a deliberate re-bless.
- 1 × `test_the_osqp_golden_is_stale_against_the_current_float_decimals_contract` —
  P4's test pinning the staleness that P3 repaired, failing exactly as its author
  designed it to when someone fixes the fixture (CC-27).

No unexplained failure remains. `test_service_is_qt_independent` passes.

## MERGE CHECKLIST (execute in this order)

1. `round5/integration` already = main + **P3** + **P2** + **P4** at `45540d9`,
   with one resolved conflict (kept P3's atomic `write_workflow_manifest`).
2. Merge **P1** last. Two conflicting files, both understood (CC-26):
   - `cmig/core/namespace.py` — **combine**: keep P4's hoisted constants, take P1's
     `STEREO_DESCRIPTORS` + `_strip_compartment_suffix` + new normalizer body, and
     **delete P4's docstring claim that folding `glu__D → glu` is "deliberate"** —
     that sentence is the rationalisation that let CC-7 survive.
   - `cmig/cli/main.py` — 7 hunks; P1 and P3 fixed the same gene-KO defect
     independently and both chose NaN. P3's is the superset (it also suppresses the
     "rank 1 (largest effect)" headline when nothing was evaluable). Take P3's
     behaviour, keep whichever comment reads more clearly.
3. Flip `map_spec.id_normalization.uppercase_stereoisomer_suffix_folded`
   `true` → `false` (P1's fix makes the recorded policy false as written).
4. Re-bless the envelope golden **once**, after P1 is in:
   `python -m cmig.core.workflow_envelope_golden`. Expect movement on the float
   probe (P3's `f64:` canonicalization) and on the host-spec kinds.
5. Rewrite P4's osqp-staleness test per CC-27.
6. Re-run the full gate: ruff · pytest · `golden verify` (both solvers, hash
   comparison) · `golden verify-envelope`.
7. Re-check `test_service_is_qt_independent` — it fails only in full-suite order
   and only when the envelope-golden tests run, so it may resolve with the re-bless.
   If it does not, it is the **third** order-dependent test found this round
   (after `test_render_client_passes_project_rlib` and
   `test_profile_render_passes_rlib_to_rscript`) and should be fixed as a pattern.

## Track status

| Track | Opus 5 review | codex review | Fix / impl | Independent re-verify |
|---|---|---|---|---|
| P1 domain | running | running | — | — |
| P2 qt/ux | running | running | — | — |
| P3 io/exc | done (P0=3 P1=1 P2=8) | done (P0=6 P1=3 P2=4) | **running** | pending |
| P4 followup | — | — | **done** (13 kinds, gate fires) | **running** (Opus + codex) |

### P4 headline claims awaiting verification
- kinds 11 → 13; `host_map` (8 components) and `publication_benchmark` (14) added
- bundle hash includes child hashes; order-insensitive (set identity)
- drift gate `cmig golden verify-envelope`, demonstrated firing on 3 perturbations
- frozen `29844e29…cef29ab` unchanged; pytest 731 → 823 collected
- self-declared weakest point: `map_spec` guards 4 control-flow fields only via a
  hand-bumped `HOST_MAP_MATCH_POLICY_VERSION` — both verifiers are tasked to attack it
