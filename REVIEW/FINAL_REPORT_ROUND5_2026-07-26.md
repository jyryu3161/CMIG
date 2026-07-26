# CMIG — Round-5 Adversarial Review, 2026-07-26

**Question asked:** does CMIG ever hand a researcher a number that is wrong, and
does the GUI tell the same truth as the CLI? Four tracks were reviewed in isolated
git worktrees; every track was reviewed independently by Claude Opus 5 **and**
Codex gpt-5.6-sol, fixed, then re-verified by both again.

## What was run

| Track | Scope | Reviews | Fix rounds | Verifications |
|---|---|---|---|---|
| P1 | Domain accuracy + workflow/skill coverage | Opus 5, codex | 1 | Opus 5, codex |
| P2 | Qt/PySide6, resources, UX, GUI↔CLI parity | Opus 5, codex | 2 | Opus 5, codex |
| P3 | I/O, exception handling, logging, security | Opus 5, codex | 3 | Opus 5, codex |
| P4 | Manifest coverage + envelope drift gate | — (implementation) | 3 | Opus 5 ×2, codex ×2 |

**8 independent reviews, 9 fix rounds, 8 independent verifications**, all on real
genome-scale models with a licensed Gurobi. Every finding required a reproduction;
nothing was accepted from source reading alone.

Each track ran in its own `git worktree` so the four streams could not corrupt each
other's measurements. The editable install points at the main repo, so each
worktree shadowed it via `PYTHONPATH` — verified per agent before any result was
trusted, because without it all four tracks would have silently tested main.

## The defects that mattered

Every one of these produces a wrong number, or hides a true one, in front of a
researcher who is about to publish.

### A custom medium was silently never applied — and the manifest certified it

`apply_medium_checked` gated on `dict(community.medium)`, which enumerates
*currently-open uptakes*, not the model's exchange reactions. A closed exchange
could therefore never be opened by a medium. Measured: 26 of 257 `EX_*_m`
reactions were reachable — roughly 90 % of nutrients were not, including acetate,
butyrate, lactate, succinate and glycerol, i.e. most SCFAs and most carbon sources.

With `--allow-unknown-medium` the nutrients were dropped in silence while the
manifest still stamped the requested `medium_checksum` and minted a distinct
`run_hash`. A `solve` with a medium returned growth **0.5849 — identical to the
no-medium run** while printing `medium=custom`. The same medium file gave
**0.881561 via `solve` and 1.125065 via `strain-growth`, 27.6 % apart.**

The correct implementation already existed. `apply_medium_translated`'s own
docstring says *"Unlike `apply_medium_checked`, this does not gate on
`model.medium`"* — round 4 had wired it into `strain-growth` only. Both reviewers
found this independently. Both paths now return 1.125065.

**Consequence for existing work:** any previous CMIG run that used a custom medium
is suspect. Its `medium_checksum` records a medium it never applied, and it carries
a `run_hash` certifying that false provenance.

### D/L stereochemistry was destroyed by an id normalizer

The heuristic "if the last `__` token starts uppercase, strip it as a MICOM taxon
suffix" also strips BiGG's stereo descriptors, which are exactly `__D` / `__L`:

```
lac__D_e → lac    lac__L_e → lac    glc__D_e → glc    arab__D_e → arab
```

`solve_bigg_host` normalizes both the reviewed interface-map keys and the microbial
availability with this function, so a reviewed D-isomer mapping matched L-isomer
availability and opened the D exchange — the host grew on a molecule it cannot
transport. Round 4 had recorded the *symptom* (D↔L swaps in the interface map);
this was the cause one layer down. Now `lac__D_e → lac__d` and `lac__L_e → lac__l`,
while `EX_ac_m__Escherichia_coli → ac` still strips correctly.

### Failed computations were published as real numbers

Three separate sites substituted a plausible default for a failure:
- `abundance-impact` wrote `community_growth: 0.0` on a failed solve, and the
  figure writer filtered on `target_abundance` but **never on `status`** — so a
  solve that did not converge was plotted as a measured zero-growth point.
- `gene-ko-search` emitted `score_delta = -baseline.score` (a finite −12.148) and
  gave it a rank, while the sibling branch 25 lines above correctly used NaN.
- `cmig solve` printed `growth: 0.0000` and exited **0** for a `solver_failed`
  community.

In each case the CSV was honest and the headline artifact was not.

### The GUI discarded the CLI's own "not interpretable" verdict

`load_dfba_summary` read four fields and never `warnings` or `n_untracked_uptake`,
and the GUI exposed no uptake-closing control. On real iML1515 the CLI detected 14
unmanaged uptake substrates and said the substrate/Km experiment was not
interpretable; the GUI showed `completed`, a biomass number and a clean timecourse.

### The analysis you clicked was not always the analysis that ran

`run_gene_ko_search` built part of its argv **inside the job closure**, so
`--max-genes` and `--top-k` were read on the worker thread at execution time. With
the pool busy, a click at 50/3 executed as `--max-genes 5000 --top-k 97`. The
manifest recorded what ran, so nothing anywhere contradicted the user's belief
about what they launched.

### A sweep republished a result it never computed

The sweep cache key was rounded to six decimals, so
`--tradeoff-fs 0.5000001,0.5000004` shared one key: the second point's solve was
skipped and the first point's value **and run_hash** were republished under the
second's `condition_id`. `axis_tradeoff_f` was rounded too, so the artifact could
not even reveal the substitution.

### Reproducibility hashes collided below 1e-6

All answer-determining floats were rounded to six decimals before hashing, so
inputs differing below 1e-6 shared a hash. Demonstrated on a real Gurobi model:
objective bounds `1e-7` and `4e-7` gave different objective values and the same
`run_hash`. The realistic case is solver tolerance, routinely 1e-6/1e-7/1e-9.

The fix had to close this **without** moving the frozen 11-component
`community_solve` hash that `golden verify` protects. It did, and the reason is
structural rather than lucky: the solve-output builders already round to six
decimals *before* building components, so noise absorption lived at the boundary
and the canonicalizer was doing it a second time, destroying genuine input
precision as a side effect. Removing the duplicate fixed it.

### Two namespace aliases for one metabolite silently picked a winner

Found independently by both verifiers *after* the medium fix landed, and reachable
precisely because hedging both namespaces was the natural user workaround for the
bug being fixed. `{EX_glc__D_m: 3.0, EX_glc__D_e: 20.0}` applied `-20.0` with
`unknown=[]` and no warning, while `medium_checksum` hashed both entries. Reordering
identical CSV rows moved community growth **1.125065287885022 → 0.9546122023612719
under an identical checksum** `medium:6e5061a08f4080ac…`.

The fix went one level above the suggested patch. Raising inside the application
loop, when measured, made `search` exit 3 with the message buried in per-candidate
diagnostics — a bad input file classified as an *analysis* failure. Validating in
`MediumSpec.validate()` makes it a spec-level input error instead: both `solve` and
`search` now exit 2, agreeing aliases merge deterministically in either order, and
the shipped presets contain zero alias groups.

### A guardrail that certified an uninterpretable run

With `--close-untracked-uptake`, all four iHN637 dFBA grid runs came back
`infeasible` while `acceptance.interpretable` was `true` and the CLI exited 0 — an
explicit stamp of validity on the clearest possible non-experiment. The repair
needed a distinction the first attempt missed: `stalled` and `infeasible` are
different failures, so `interpretable` now fails on **any** infeasible row but only
on an **all**-stalled grid, because a mixed grid still has dynamics to compare.

### The medium fix changed published numbers without moving any hash

`solve --medium` went 0.881561 → 1.125065 under the *identical* hash
`6960d9ca9412a572…`; `search --medium` 18.13 → 13.64 under identical
`cf395ca787e9957b…`. Bumping `cmig_core_version` could not express this — it is a
frozen component. A non-hashed `provenance.medium_policy` marker
(`exchange_reactions_by_metabolite_v2`) now records the discontinuity, stamped by
the writer so no solve path can omit it, and verified absent from both hash
contracts.

## What the multi-model, multi-round design actually bought

**Each model found things the other did not.** Codex found the hash collision and
the medium defect; Opus found the worker-thread argv race and the abundance-impact
figure. On P1 both converged on the medium defect independently, which is what
raised confidence enough to make it the first fix.

**Verification caught what the coordinator's own checks missed.** After the
canonicalization fix I verified the frozen hash myself — on gurobi only — and
passed it. The Opus verifier found that the **osqp** golden had silently moved
(`a422eb89… → 6a30a02a…`), because `VARIANT_DECIMALS['osqp'] = 4` while the builder
pre-rounded at 6, so `round(0.333333, 4) ≠ 0.333333` took the new lossless branch.
The invariant needed was `round(x, D) == x` where D is the decimals *that hash
uses*. Every golden pin is now parametrized over both solvers.

That investigation also found `golden verify` **only compared `micom_version`** — a
golden hash could move while the gate stayed green. It now compares hashes.

**Fixes introduced defects, and verification caught those too.** The P2
invalidation fix created on the Search tab exactly the export-stale-run defect it
had just fixed on Host. Its first read-only-table fix was a 15× rendering
regression (3.0 → 46.4 ms) that the fixer caught itself and replaced.

**Newly added tests were audited, not trusted.** Asking "would this fail if the
behaviour it names were deleted?" found 4 of 32 new P3 tests that would not — one
passed *with the bug present* because `_finite_csv` renders `0.0` as `"0"`. On P2 a
12-case mutation battery confirmed the opposite: all 12 pinning tests failed when
their production change was reverted.

**Two models defeated the same design by disjoint routes.** P4's host-map
fingerprint was attacked twice. Opus broke it on scale and real BiGG vocabulary
(interface map 67 → 22 under an unchanged hash); codex broke it on bound regimes
(iAF987's `EX_ac_e [-8.88, -6.84]` and `EX_fe3_e [-67.37, -49.21]`, which the probe
could not represent because every fixture bound was ±1000). Two disjoint blind
spots, one root cause: a finite synthetic fixture cannot enumerate the input space.

That is why the guarantee moved to the answer side. `result_digest` is recorded
additively (not in the hash, so no published hash moves) and `inspect-run`
recomputes it. It catches all four independently-discovered breaks. The honest
split is now stated in the code: **`run_hash` certifies the inputs, `result_digest`
certifies the answer.**

**A deferral rationale was wrong in an instructive way.** One P0 was deferred as
"not reachable from any CLI subcommand or the GUI". Codex reached it through shipped
`strain-growth`, which reported a demand objective as `community_growth` with
`status: ok` and no warnings. The error was scoping reachability to the *named
function* rather than to the *defect*. Re-auditing the remaining deferrals on that
basis confirmed one of them (`analyze_pair`) on **better** grounds: the defect class
is reachable via `strain-growth`, but there it is already handled, and `analyze_pair`
is the unshipped duplicate that lacks the handling.

**Isolated verification re-surfaces defects another track already fixed.** Verifying
P1 alone reported the OSQP frozen hash as failing — true in that worktree, already
repaired in P3's. Recognising this before dispatching a fixer saved a cycle; the
same class of cross-track echo appeared three times.

**Not every failure is a defect.** `test_service_is_qt_independent` failed once in
the integration suite and was nearly filed as a third order-dependent test. Four
controlled re-runs showed it fails only while several concurrent agent sessions are
spawning subprocesses, and passes at zero load. It is subprocess-isolated already
and nothing in the code explains it. It was an artifact of the review's own
orchestration, and the tempting move — dispatching a fixer at it — would have risked
a "fix" to working code.

## Measurements that prevented wasted work

- **`QTableWidget` → `QTableView` migration: not needed.** Worst reachable cases
  measured at 0.3–6.0 ms (search table 100 rows 0.7 ms; 2712 rows 3.0 ms; jobs
  panel at 1000 jobs 6.0 ms/refresh, 1.2 % duty). All inside one frame.
- **The real event-loop stall was elsewhere:** the Constraint Sandbox solved
  synchronously in its slot — 2069–3852 ms measured with **0 heartbeat ticks** —
  and auto-fired 500 ms after any table edit. Now 0.3–0.5 ms with 68–107 ticks. The
  residual ~70 ms gap was proven to be GIL contention by a control the fixer had
  not run: the same solve on a bare `threading.Thread` with no Qt at all gives
  statistically indistinguishable gaps.
- **GUI↔CLI numbers are already exact.** Identical `score`, `target_flux`,
  `community_growth` and an identical `run_hash` (`338686edd7f37907…`), stable
  across output directories **and across a Korean-named model directory**. The
  parity failures were exposure failures, not arithmetic ones.
- **A proposed Gurobi licence probe was rejected on measurement**: `gurobipy.Env()`
  *succeeds* under a size-limited licence (the limit bites at model size — a
  2001-variable model fails, a 50-variable one does not), so the patch could not
  detect the case it was written for while making `available` look authoritative.

## Verified correct, so future rounds need not re-check

State restoration around knockout / FVA / minimal-medium / host / dFBA; the uptake
sign convention (`10 → lower_bound = -10`); objective replacement without
accumulation; micom `scale == 1.0`; `Σ abundance × member_flux == external_exchange`;
byte-identical data-artifact reruns of `solve`/`search`/`dfba`; GA and random
seeding; SBML round-trip fidelity on iYO844 (bounds, annotations, formulas, charge,
subsystem, gene names, objective — and mixed AND/OR gene rules survive exactly);
no `eval`/`exec`/`compile` on user input, no `pickle`/`marshal`/unsafe `yaml.load`,
no `shell=True`, no archive extraction; malformed-input handling across 7 cases;
CJK filenames.

## Follow-up work delivered (item 10)

Workflow-manifest coverage went from 11 kinds / 12 commands to **13 / 14**, adding
`host_map` (the interface-map decisions every host run depends on) and
`publication_benchmark` (which claims to bundle the whole audit). The bundle hash
**includes its children's hashes** — a bundle is a claim about a specific set of
runs, so two bundles built from identical arguments over different sub-runs must
not share a fingerprint. It is order-insensitive: identity is the set.

The **envelope drift gate** ships as `cmig golden verify-envelope`, wired into
pytest and into the licence-free CI job across all four matrix legs. Its golden
lives inside the package rather than in `fixtures/`, because `fixtures/` is excluded
from the sdist and a gate whose golden is missing from the distribution silently
skips. Verified by actually building the wheel: the golden ships at 44,057 bytes,
byte-identical to source, and the gate passes from the unpacked wheel.

Its golden fixtures are **built by the component builders**, not transcribed as
literals — the transcription version had the same defect species one level up, and
rebuilding immediately revealed five kinds whose published hashes had moved with
only two disclosed.

**The gate proved itself on real work.** On the first integration merge it fired
unprompted on P3's lossless `f64:` canonicalization — a genuine cross-track
serialization change that would otherwise have altered published workflow hashes
silently.

## What the top-level review found after the merge

The merge itself was reviewed by a fresh Opus 5 reviewer that had seen none of the
four tracks. Its verdict: **the merge is correct and could not be broken** — no
composition failure, verified by mechanical lost-line analysis across all six files
touched by more than one track, with every residual difference traced to a
documented deliberate substitution.

But it found **three live instances of this round's own central defect class**,
named in no known-open list and byte-identical on `main` — pre-existing, not merge
regressions:

- **`cmig/cli/main.py:5374`** — the strain-growth figure used
  `_optional_float(...) or 0.0`, so a member whose alone-solve raised was drawn as a
  **measured zero bar**. The CSV wrote blank; only the figure fabricated, and the
  `.tiff` is what goes in a manuscript. A zero-height "Single model" bar beside a
  real "Community" bar reads as obligate syntrophy — a biological conclusion invented
  by a plotting default. The warning comment from the identical abundance-impact fix
  sat 80 lines below it.
- **`cmig/cli/main.py:6786`, `:6826`** — `sweep` hard-coded `"status": "ok"` and
  derived the manifest status from `rows`, which includes failures. Reproduced with a
  plain medium file and no flags: every condition `status: failed` with `value: NaN`,
  while the summary, manifest, `inspect-run` **and exit code** all said ok.
- **`cmig/cli/main.py:1543`** — `host-search-bigg` hard-coded
  `"evaluation_status": "ok"`, and `host_coupling.py:127` *returns* rather than raises
  for a non-optimal host LP, so score 0.0 was ranked and plotted in the "ok" colour
  with `n_candidates_failed: 0` — while that row's own warnings cell said the host
  objective is not a result.

Blocking the merge over them would have been actively harmful: `main` carried all
three *plus* lacked everything the branch fixed. They were fixed before landing
instead. All three now derive status rather than assert it, publish NaN rather than
0.0, and state the excluded count on the figure. `sweep` also gained the
`--allow-failed-run` gate it was the only command to lack.

A fourth finding closed a false claim: `inspect-run` printed "certifies the ARTIFACT
BYTES — verified" while a figure overwritten with `<svg>FABRICATED FIGURE</svg>`
passed, because **no workflow declared its figures in `artifacts`**. Ten writers each
built an accurate list into their summary JSON while each command passed an
independently maintained literal to the manifest. Writers now return the list they
wrote and the manifest declares exactly that, so the two agree by construction and
figures fall under `result_digest`. A tampered declared artifact now sets
`artifact_integrity: mismatch`, flips status to `failed`, reports in `--format json`,
and exits 3.

Reverse validation: 7 combinations built, 5 reproduced, and **one deliberately did
not** — `--tradeoff-fs 0.5000001,0.5000004` now yields distinct hashes at full
precision, confirming the sweep-replay fix holds.

## Corrections to this report's own record

Two claims made during the round were wrong and are corrected here rather than
quietly dropped:

- **`pytest-randomly` is not installed in this environment.** Several runs during the
  round used `-p no:randomly`, which was therefore inert, and "green under randomized
  order" overstated what was tested. What *was* verified, after landing:
  - a seeded per-test shuffle of all 1043 node IDs reached ~15 % (155 tests, all
    passing) and then **stalled** — CPU time advanced 0.04 s over 20 s of wall clock.
    Shuffling per test destroys module-scoped fixture reuse, so genome-scale models
    reload constantly; the run was abandoned rather than reported as a pass.
  - **every one of the 77 test files was then run in its own process: 0 failed in
    isolation.** This is the check that actually caught both genuine order-dependent
    tests this round, and both of them (`test_render_client_passes_project_rlib`,
    `test_review_regressions.py::test_profile_render_passes_rlib_to_rscript`) now
    pass standalone where they previously failed.
  Per-file isolation plus the sequential full run is strong but not equivalent to
  per-test randomization. Installing `pytest-randomly` (or making the expensive
  fixtures cheap enough to shuffle) remains an open, cheap improvement.
- **`or 0.0` occurs 3 times in `cli/main.py`, not 7.** The higher count came from a
  coordinator grep that matched the abundance-impact fix's own explanatory comment.
  Repo-wide there are 19; all were audited and 2 needed fixing. An AST-based test now
  fails on any `BoolOp(Or)` with a numeric-zero right operand in `cli/main.py` —
  parsed rather than grepped, so prose about the defect does not trip it.

## Known open, deliberately

- **`edges.parquet.weight` is an unlabelled per-taxon flux**, so an edge's magnitude
  inverts against its true community contribution (84.57 at abundance 0.1 vs 12.29
  at 0.9, where the true contribution rises 8.46 → 11.06). Fixing the *value*
  requires re-blessing a frozen golden on both solvers, the two reviewers proposed
  incompatible `abundance is None` contracts, and neither patch scales the FVA
  bounds. A unit disclosure landed in the manifest; the value fix is deferred.
- `growth_feasible` and `analyze_pair`'s medium mismatch are real but unreachable
  from any CLI subcommand or the GUI, and must land together as one API redesign.
- Atomic writes are finished for text artifacts (new `cmig/io/atomic.py`); parquet
  and figure writers are explicitly deferred.
- In-flight input labelling shipped for Search and Sandbox; Host and Dynamics are
  the same shape and are deferred rather than rushed.
- `match_behavior` remains a best-effort input-side signal. `result_digest` is the
  guarantee.
