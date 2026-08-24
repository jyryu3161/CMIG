# CMIG scientific-validity guardrails (중요한 지점)

CMIG encodes the scientific choices that make a metabolic result defensible as
**explicit, mostly mandatory** CLI flags. This file explains *why* each one
exists and how to set it. Read it before any host-microbe run, any weighted
ranking, any dFBA interpretation, or any publication run. The unifying rule:
**a run that skipped a guardrail is not a result — it is a number that looks
like one.** Report the choice you made, don't route around it.

## 1. Host-microbe biomass basis — mandatory, no default

**Why.** Microbial fluxes and host-specific fluxes live on different biomass
scales. A microbial exchange in mmol · gDW⁻¹ · h⁻¹ and a host flux cannot be
compared or transferred without knowing the gram-dry-weight (gDW) basis each is
expressed on. If you skip this, the coupling silently compares incommensurable
quantities.

**What CMIG requires.** `host-microbe-bigg` and `host-search-bigg` have **no
biomass default**. You must pass all of:

- `--microbial-biomass-gdw <positive>` — study microbial dry mass in gDW.
- `--host-biomass-gdw <positive>` — host dry-mass basis represented by the host
  fluxes in gDW.
- `--biomass-basis-kind measured|literature|validation`.
- `--biomass-basis-source "<measurement record, Methods section, or citation>"`.

**The `validation` trap.** `--biomass-basis-kind validation` exists only so
software tests can run without a real basis. It makes CMIG stamp the result
**"biomass basis is validation-only; result is not publication-ready"** in the
run `warnings` and sets `publication_ready` false. Never present a `validation`
run as a scientific finding. For real work use `measured` (you have the dry
masses) or `literature` (you cite them), and put the actual source in
`--biomass-basis-source`.

## 2. Interface maps are computational suggestions, not ground truth

**Why.** CMIG matches host and microbial metabolites using metabolite
annotations and normalized BiGG identifiers. That is a good first pass, but
annotation matches are *guesses* — wrong or missing annotations produce wrong
edges, and a wrong edge is a fabricated interaction.

**What to do.** For a publication host-microbe run:

1. Generate a candidate map: `uv run cmig host-map ...`.
2. Have a human review it — confirm each mapped metabolite pair is real, drop
   spurious matches, add known ones the annotations missed.
3. Pass the reviewed file back with `--interface-map reviewed_map.json`.

Do not treat the auto-generated mapping as final, and say in the result whether
the map was reviewed.

**How the map is partitioned.** `host_interface_map.json` splits its entries:

- `interface_map` — **exact id matches only**, safe to pass through unchanged.
- `needs_review` — annotation / normalized *guesses*. Confirm each and move it
  into `interface_map` before coupling.
- `unmatched` — microbial secretions with no host counterpart.

`host-microbe-bigg`, `host-search-bigg` and `host-ko-impact` **refuse to couple**
while any `needs_review` entry remains. `--accept-unreviewed-map` waives that; the
run is warned and the entries are named, and you must surface both.

**Read `n_exact` / `n_annotation` / `n_normalized` from `host_map_summary.json`
to size the review.** If `n_annotation` and `n_normalized` are both 0, every match
was an exact id match and there is nothing to adjudicate. Measured on the real
Recon3D against iHN637: `63 exact / 0 annotation / 0 normalized / 32 unmatched`
of 95 secretions, with `needs_review: {}` — so a BiGG-namespace host needs no
waiver at all, and reaching for `--accept-unreviewed-map` there would be a
mistake.

**The hazard the gate exists for is D/L stereochemistry.** BiGG spells stereo
descriptors as `__D` / `__L`, and *annotation* matching can pair `lac__D` with
`lac__L` — chemically distinct molecules. When that happens the host is given an
exchange for a molecule it cannot transport, and it *grows on it*. The exact-match
path is not affected (the same Recon3D map carries `lac__D_e → EX_lac__D_e` and
`lac__L_e → EX_lac__L_e` correctly), so the risk concentrates entirely in the
`needs_review` block. Review stereo descriptors there explicitly: `lac__D` vs
`lac__L`, `glc__D`, `arab__D`, and every amino acid. Treat a map that pairs
opposite isomers as a fabricated interaction, not a near miss.

## 3. Never add quantities with different units (weighted ranking)

**Why.** Ranking combinations by a host objective *plus* a target transfer
means adding two quantities that generally have different units and magnitudes.
Adding them raw is meaningless and lets the larger-magnitude term dominate for
non-scientific reasons.

**What CMIG requires.** `host-search-bigg --metric weighted` refuses to run
unless you supply positive, finite:

- `--host-weight`, `--target-weight` — relative importance, and
- `--host-reference`, `--target-reference` — reference scales that
  nondimensionalize each term.

The score becomes `host_weight · host_objective / host_reference +
target_weight · target_transfer / target_reference`, which is dimensionless. If
you cannot justify reference scales, **do not invent them** — rank by
`--metric target_transfer` or `--metric objective_value` instead, which use a
single well-defined quantity.

## 4. Solver provenance — approximate ≠ exact

**Why.** The solver determines whether a reported flux is an exact optimum or a
QP approximation. Reporting an approximate number as if it were exact
misrepresents precision.

**The matrix** (`cmig solvers` shows availability):

- `gurobi` — canonical **full-flux** workflow. Required for community FVA and
  for the host / search product workflows. Default for publication runs.
- `osqp` — **QP-only approximate** provenance for supported community solves.
  Useful when Gurobi is unavailable, but every number it produces is
  approximate.

Always report which solver produced a result. CMIG records solver choice and
flux provenance in the run outputs so cached or published results stay
interpretable — surface it, don't bury it.

## 5. dFBA: close untracked uptake *first*, then audit sensitivity

**Why (part 1 — interpretability).** CMIG tracks concentrations only for the
exchanges named by `--initial` (default: glucose, oxygen, acetate, D-lactate).
Every other uptake exchange left open by the model's default medium has **no
concentration**, so it is never depleted and no Michaelis-Menten term applies to
it. Biomass can therefore rise while the tracked substrate is untouched, and a Km
sweep on the tracked substrate measures nothing.

**What to do.** Pass **`--close-untracked-uptake`** to `dfba` *and* to
`dfba-sensitivity` (or track those exchanges explicitly with `--initial`).
Verify by reading `n_untracked_uptake` and `warnings` from `dfba_summary.json`.

Measured on a bundled model, following the naive recipe:

```bash
uv run cmig dfba --model models/iML1515.xml --dt 0.1 --out runs/dfba_plain
# exit 0, status "completed", final_biomass 0.6654843209450042
# n_untracked_uptake: 14  (EX_nh4_e, EX_pi_e, EX_so4_e, EX_k_e, EX_fe2_e, ...)
# warnings: "... a Km sweep on the tracked substrate is NOT interpretable.
#            Re-run with --close-untracked-uptake ..."
```

The run **succeeds and reports a biomass number** while its own warning says the
experiment is uninterpretable. Auditing `--dt`/`--km` on that setup yields a
"robust across Km" conclusion that is meaningless, because Km was never
rate-limiting. This is the trap: the guardrail below is necessary but **not
sufficient**.

**Why (part 2 — numerics).** A well-mixed dFBA trajectory is a numerical
integration. Its endpoint can shift with the integration step `--dt` and the
uptake half-saturation constant `--km`. A single coarse-step run can report an
endpoint that a finer step would contradict.

**What to do.** Run `uv run cmig dfba-sensitivity --close-untracked-uptake` across a
range of `--dts` and `--kms` — **and pair it with a complete `--initial`.**
`dfba-sensitivity` accepts `--initial`; closing untracked uptake removes every
nutrient you did not name, so the default four-substrate `--initial` starves the
model. Measured on `models/iML1515.xml`: `--close-untracked-uptake` alone closed 22
exchanges and gave exit 3 with **4/4 rows stalled at `final_biomass 0.01`** (the
initial value — no dynamics at all). Supplying all 14 nutrients from the plain run's
`untracked_uptake` field gave exit 0, `interpretable: True`, 4/4 completed, and a
real step-size signal (`final_biomass` 0.0536 at dt 0.1 vs 0.0503 at dt 0.2). The
worked command is in `references/workflows.md`.

It returns every run plus integration mass-balance residuals. Read
`acceptance.interpretable` and
`acceptance.not_interpretable_because` in **`dfba_sensitivity.json`** (not
`dfba_sensitivity_summary.json`). The grid is rejected if **any** row is
infeasible or **all** rows stalled — a mixed grid still has dynamics to compare —
and the command **exits 3** when it is not interpretable.

> `inspect-run` reflects that verdict: `acceptance.interpretable: false` is a
> **veto** reported as `status: failed` with
> `status_source: acceptance.interpretable`, and it overrides a rosier manifest
> tier. Still check `$?` — `inspect-run` exits non-zero only on
> `artifact_integrity: mismatch`.

Also: `--initial` values are **strict** — they must exist in the model; a typo'd
exchange id is an error, not a silent skip.

## 6. Knockout screens must not silently sample a subset

**Why.** If a gene-KO screen quietly evaluated only some genes, its "top
knockouts" ranking is misleading — you cannot tell whether the real best target
was simply never tested.

**What CMIG does.** In `gene-ko-search`:

- `--max-genes 0` evaluates **every** target (prefer this for a complete
  screen).
- If `--max-genes` truncates, CMIG writes an explicit `warnings` entry and
  records `n_genes_total`, so truncation is never invisible.
- `--gene-selection id|random` with `--seed` makes any truncated subset
  reproducible.

If you cap the screen, surface the warning and the evaluated-of-total count in
your summary; don't present a capped screen as exhaustive.

## 7. Know what a tool does *not* do

- **`spatial-preview` is a medium-design tool.** It previews 2D
  source/sink/diffusion layouts to help design a run. It does **not** solve FBA
  on each grid cell and is not spatial community dFBA. Never describe its output
  as spatial simulation results.
- **`abundance-impact` is sensitivity, not causality.** It rescales one member's
  abundance under the same model set and medium and recomputes the community. It
  quantifies how outputs respond to that ratio — it is not evidence of ecological
  causation. Pass `--fva`: without the target's FVA interval at each point, a jump
  between neighbouring abundances cannot be told from alternate-optima degeneracy.
- **`edges.parquet.weight` is not a community contribution.** It is an unsigned
  **per-taxon** flux (`mmol gDW_taxon⁻¹ h⁻¹`), so comparing raw edge magnitudes
  ranks members wrongly — per-taxon flux scales roughly as 1/abundance, and the
  inversion is real, not marginal (measured: 3.876 at abundance 0.1 vs 0.459 at
  0.9, where the community contributions are 0.388 vs 0.413 — the ranking flips).
  Multiply by abundance, exclude `cross_feeding` rows (a proportional allocation,
  not a measurement), and sign by direction; the sum then equals
  `profile.parquet.net_flux`. `uv run cmig inspect-run --format text` prints the whole
  recipe as the `edges.weight basis:` line. Full detail in
  `references/outputs.md`.
- **`strain-growth --single-medium model_default` is not an interaction
  measurement.** It reports each member's native capability under its own SBML
  bounds, so the alone-vs-community delta also contains the medium change. Use the
  default `community` when the question is cross-feeding.
- **CMIG does not fetch models.** It never downloads or auto-selects AGORA / VMH
  / Recon / Human-GEM / BiGG catalogues. Users provide local SBML/JSON/MAT GEMs.
  If a request assumes auto-download, correct it.

## 8. Reproducibility is part of validity — and one hash is not enough

A result you cannot reproduce is not defensible. CMIG supports this directly:

- Every analysis run emits a **manifest** and a **run hash**.
- `uv run cmig inspect-run --format json` reads them back in a stable schema.
- `cmig golden verify` is the MICOM/solver-version regression gate (it compares
  **hashes**, parametrized over gurobi and osqp). `cmig golden verify-envelope`
  is its workflow-manifest analogue, catching serialization drift that would
  silently move published workflow hashes. Run **both** when the environment
  changes.
- `cmig publication-benchmark` bundles the quality audit, a community solve,
  search, optional dFBA sensitivity, and optional host coupling into a single
  checksummed manifest with a `publication_ready` flag. Its bundle hash includes
  its children's hashes and is order-insensitive, so a bundle identifies the
  exact *set* of sub-runs. It exposes **33 options** — read its `--help`.
  **`publication_ready` does not certify §5.** The command accepts no
  `--close-untracked-uptake`, so its bundled dFBA leg cannot be made interpretable
  as a substrate/Km experiment. If a dFBA endpoint is load-bearing for your claim,
  run `cmig dfba-sensitivity --close-untracked-uptake` with a complete `--initial`
  separately and cite that run instead of the bundle's dFBA leg.

**The honest split — state it, don't blur it:**

- **`run_hash` certifies the INPUTS.** Identical inputs ⇒ identical hash. It does
  **not** certify the answer. Proof from CMIG's own history: the medium fix moved
  `solve --medium` from 0.881561 to 1.125065 under an *identical* `run_hash`, by
  design, because the hash's components were frozen.
- **`result_digest` certifies the ANSWER.** It fingerprints the artifact bytes
  the run wrote, **including figures**, and `inspect-run` recomputes it. A
  tampered declared artifact sets `artifact_integrity: mismatch`, flips `status`
  to `failed`, and exits 3.
- `result_digest` exists for the 13 **workflow-manifest** kinds. **`cmig solve`
  does not emit one**, so `result_digest: not recorded` on a fresh solve is
  expected, not tampering.
- **Digests are comparable across runs only where `cross_run_comparable` is
  true** — currently `host_map` alone, because its artifacts are byte-deterministic
  for identical inputs. Elsewhere the digest certifies *those bytes*; two runs with
  identical inputs may legitimately differ (embedded figure rasters, parquet write
  ids, timestamps), so cross-run digest comparison for other kinds manufactures
  false alarms. Use `run_hash` to ask "same inputs?" and `result_digest` to ask
  "are these still the bytes this run produced?".
- `match_behavior` is a best-effort **input-side** signal only. `result_digest`
  is the guarantee.

When you report a run, include its `status`, `run_hash`, `result_digest` /
`artifact_integrity`, and the solver.

## 9. A multi-target "total" question needs the right scalarisation

**Why.** Ranking combinations against several targets means combining them into
one number. A **linear** weighted sum is optimised at a **vertex** of the
achievable set, so it systematically returns a **single-metabolite specialist**
rather than a balanced producer. "Best total SCFA" answered with the default
metric is a wrong conclusion, not an approximation.

**Measured** (`--target-preset scfa` = `ac,but,lac__D,lac__L,ppa,succ`, 2-member
combinations over the 5 bundled models, default
`--multi-metric normalized_weighted`):

```
best: iHN637+iSFV_1184 score=1 (ac=0, but=0, lac__D=17.44, lac__L=0, ppa=0, succ=0)
```

All 9 ranked candidates returned `ac=0, but=0, ppa=0, succ=0`; 8 of 9 produced
exactly **one** non-zero SCFA. The entire "total SCFA" ranking was decided by
D-lactate. CMIG says so itself in the run's `warnings`:

> a weighted-sum objective is optimised at a vertex of the feasible set, so this
> ranking systematically favours a single-metabolite specialist over a balanced
> producer — the winner's 'total' can be one metabolite and zero of the others.

**Re-running the identical pool with `--multi-metric pareto`** returned 7
non-dominated points across 10 consortia and 5 epsilon levels, producing 1, 4, 4,
4, 4, 5 and 5 non-zero SCFAs respectively — and only **1 of 7** front points was a
single-metabolite specialist. The decisive detail:

All three metrics were then run over the identical pool. The **same winning pair**,
`iHN637+iSFV_1184`, under the same medium, is reported as:

| metric | ac | but | lac__D | lac__L | ppa | succ |
| ------ | -- | --- | ------ | ------ | --- | ---- |
| `normalized_weighted` | 0 | 0 | **17.44** | 0 | 0 | 0 |
| `carbon_equivalent` | **8.19** | 0 | 0 | 0 | 0 | **10.41** |
| `pareto` rank 1 | **27.75** | 0 | 0 | 0 | 0 | 0 |
| `pareto` rank 2 | **23.71** | 0 | 0.87 | 0.70 | 0 | 0.71 |

Read the first two rows together: `normalized_weighted` says this community makes
lactate and **no** succinate; `carbon_equivalent` says it makes succinate and **no**
lactate. Those are contradictory biological claims about one community on one
medium, and the only thing that changed is the weighting. And the default metric
reports **zero acetate** for the pool's *largest* acetate producer (27.75).

"This community does not make acetate" — or lactate, or succinate — is exactly the
wrong conclusion any single scalarised run invites. Per-candidate non-zero SCFA
counts make the pattern plain:

```
normalized_weighted : [1, 1, 1, 1, 1, 2, 1, 1, 1]     of 6 targets
carbon_equivalent   : [2, 2, 1, 1, 2, 2, 1, 2, 1]
pareto              : [1, 4, 4, 4, 4, 5, 5]
```

`carbon_equivalent` returned `but=0, lac__D=0, lac__L=0, ppa=0` for **every** one of
its 9 ranked candidates. It is not a way out of the collapse — only the frontier is.

**What to do.**

| Metric | Meaning | Use for | Linear? |
| ------ | ------- | ------- | ------- |
| `normalized_weighted` (default) | dimensionless min-max over *this run's* candidates | never a "total" claim; **not comparable across runs** | yes — collapses |
| `carbon_equivalent` | mmol C gDW⁻¹ h⁻¹, each target weighted by carbon number | "most carbon routed to SCFA"; absolute and run-comparable | yes — **still collapses** |
| `raw_sum` | plain molar sum | only if the user explicitly wants molar sum; it adds C2 and C4 acids as equals | yes — collapses |
| `pareto` | the **non-dominated trade-off set** via an epsilon-constraint sweep, in absolute units | **"which community is best overall"** | no |

**The collapse is a property of linear scalarisation, not of the weighting.** All
three scalar metrics are linear objectives, so all three land on a vertex; changing
weights only changes *which* vertex. Choosing `carbon_equivalent` fixes the units
problem, not the specialist problem. Only `pareto` reports the trade-off.

`--multi-metric pareto` is a *different code path*, not a different weighting: it
sweeps epsilon levels per consortium and keeps the N-dimensional non-dominated
subset (`solution_semantics: epsilon_constrained_lp_non_dominated_set`,
`normalizer: none_pareto_front_absolute_units`). It works for any number of
targets and is much slower than the scalar metrics.

Two things to carry into the write-up:

- **Front members are not totally ordered.** In `pareto` mode `rank` is a
  *reporting order* (weighted sum), not a claim that rank 1 is best. Present the
  frontier; let the user choose the trade-off.
- The run states how many front points are themselves single-metabolite
  specialists, which is the honest measure of how much trade-off the pool offers.

**Do not confuse the mode with the column.** A **scalar**-metric ranking also
carries a `pareto` boolean column, and that column is computed **only for exactly
two targets**; with more, every cell stays `False`, meaning "not evaluated", not
"dominated". Filtering a 6-target scalar ranking on `pareto == True` returns
nothing — that is not a finding.

Also read the run's other warnings: targets reported as exactly `0` alongside
positive ones **may be a vertex-selection artifact** rather than an inability to
produce them.

> **`--robustness-fva` does not help you here — it is silently inert in
> multi-target mode.** `_cmd_search` returns to the multi-target path
> *before* `args.robustness_fva` is ever read, and the
> multi-target body never reads it. The flag is accepted, no FVA columns are
> written, **no warning is emitted, and the run exits 0.** So there is currently
> **no** way to separate a multi-target ranking from a tie between alternate optima
> from within the run, which is precisely the mechanism behind the collapse above.
> Until that is fixed, treat close multi-target scores as indistinguishable, and use
> `--multi-metric pareto` — whose epsilon sweep explores the trade-off surface
> directly — rather than trying to bound a scalarised ranking.
> `--robustness-fva` *does* work in **single**-target mode, where it is worth
> passing.

## 10. A custom medium is only trustworthy in a post-fix run

**Why.** CMIG applies a medium by translating it to the community's exchange
*reactions* per metabolite, so a currently-closed exchange **does** get opened.
An earlier implementation gated on the already-open uptakes, which silently
applied almost nothing — acetate, butyrate, lactate, succinate and glycerol among
the nutrients that never took effect — while the manifest still stamped the
requested `medium_checksum` and minted a `run_hash` certifying it.

**Consequences to act on.**

- **Any pre-fix run that used `--medium` is invalid and must be re-run.** Do not
  reuse the cached numbers.
- **The hash will not tell you.** The fix deliberately changed published numbers
  *without* moving any hash. Detection is via
  `provenance.medium_policy: "exchange_reactions_by_metabolite_v2"` — check it
  with `uv run cmig inspect-run --format json`. Absent, or
  `open_uptakes_exact_key_v1` ⇒ re-run.
- **Do not hedge namespaces.** Listing one metabolite under two namespaces (e.g.
  `EX_glc__D_m` *and* `EX_glc__D_e`) is rejected as a spec-level input error
  (exit 2) in both `solve` and `search`. Pick one. It used to pick a silent winner
  and reordering identical rows changed community growth under an identical
  checksum.
- **`--medium` is an OVERLAY, not a replacement — so it does not close oxygen.**
  CMIG merges the requested uptakes onto MICOM's default community medium, which
  is permissive, so **every metabolite the file does not name keeps its default
  bound.** Measured on a glucose-only spec applied to `iML1515 + iYO844`: 23
  uptakes stayed open that the spec never requested, `EX_o2_m` among them at
  **999999.0**. Every "anaerobic gut community" result CMIG produced on a custom
  medium before this was found was computed with oxygen freely available. The cost,
  measured on `iML1515+iYO844+iHN637` at `cooperative_tradeoff(f=0.5)`, Gurobi:
  community growth **1.2677557** with the inherited oxygen against
  **0.6990206751** with `EX_o2_m = 0.001` — an **81 % overestimate from one
  absent row**.
  - Use the shipped `medium_presets/gut_overlay_*.csv`. Each names oxygen
    explicitly at MICOM's own published `0.001` and carries a
    background-closure block (`uptake_limit = 0`) for every metabolite the pool
    would otherwise leave open; `uptake_limit = 0` is the only way a CSV can say
    "the environment does not supply this" under merge semantics.
  - **Do not cite `western_diet.csv` or `high_fiber.csv` as diets.** They are
    single-row glucose files with no source, 134× and 76× the published AGORA
    bounds, with no oxygen row and — despite the name — no fibre at all. They are
    retained only as a smoke fixture.
  - A closure block is **pool-specific**, so an overlay carried to a different
    model set may leave nutrients open again. Re-measure rather than assume.
- **`--allow-unknown-medium` costs more than it looks.** Without it, a medium id
  with no counterpart in the community is a hard input error (**exit 2**). With
  it, those nutrients are **dropped** and the run continues. Measured on a
  2-member community with one bogus id: **exit 0**, `status: degraded`, a
  `medium_unapplied` diagnostic naming the dropped id — and a `medium_checksum`
  still computed over the **full requested** medium. So `$?` says success and the
  hash certifies a medium only partly applied. Use it to *diagnose* a medium
  file, never for a reported result, and always quote the dropped ids.
  The flag is available on `solve`, `search`, `strain-growth`,
  `abundance-impact`, `gene-ko-search`, `sweep`, `host-microbe-bigg`,
  `host-search-bigg`, and `host-ko-impact`; strict application remains the
  default on all nine commands.

Units, while you are here: `MediumSpec` is `exchange_id,uptake_limit` with
`uptake_limit >= 0` — an unsigned magnitude in **mmol gDW⁻¹ h⁻¹**, which CMIG maps
to `lower_bound = -uptake_limit`. Literature diets are usually given per person
per day; show the conversion arithmetic and its assumptions rather than pasting a
number.

## 11. Exit codes are part of the contract

| Code | Meaning |
| ---- | ------- |
| `0` | ran, and the scientific solve succeeded (or `--allow-failed-run` was passed) |
| `2` | **input** error — bad medium spec, aliased namespaces, missing exchange counterpart |
| `3` | artifacts were written but **the scientific solve did not succeed**; also `inspect-run` on `artifact_integrity: mismatch` |

Artifacts are written on failure *on purpose*, so a failed run is diagnosable —
which is exactly why `$?` must be checked before reading them.
`--allow-failed-run` turns a 3 into a 0 for pipelines that want the artifacts
anyway; it does **not** make the run a result. If you pass it, say so and quote the
failure.

**It is not universal.** It exists on `solve`, `search`, `strain-growth`,
`abundance-impact`, `gene-ko-search`, `sweep`, `dfba-sensitivity`,
`host-microbe-bigg`, `host-search-bigg` and `host-ko-impact`. It is **rejected** by
`dfba`, `model-quality`, `publication-benchmark`, `spatial-preview` and
`model-review`:

```
$ uv run cmig dfba --model models/iHN637.xml --allow-failed-run --out runs/x
cmig: error: unrecognized arguments: --allow-failed-run       # exit 2
```

That is an **argparse** error, so it exits 2 — the same code this table assigns to a
bad medium spec or aliased namespaces. If you see exit 2 after adding
`--allow-failed-run`, check the flag before you go debugging your medium file.

`inspect-run` is **not** a substitute: it describes a run rather than re-judging
it, and it exits non-zero only on `artifact_integrity: mismatch`. It no longer
invents `ok` for a summary that carries no verdict — such a run reports
`status: unknown` with `status_source: no_status_signal`, and `unknown` is a real
answer rather than a pass. Read `status_source` to know what the status is worth,
and note that `infeasible` / `stalled` still reach `status` verbatim, so a gate
matching only the four tiers will miss them. Full field reference in
`references/outputs.md`.
