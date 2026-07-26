# CMIG — Orchestrated Functional Evaluation & Improvement, 2026-07-25

**Question asked:** can CMIG actually answer three scientific questions, and does
it produce Nature-Genetics-grade figures? Two models (Claude Opus 5, Codex
gpt-5.6-sol) evaluated independently and cross-reviewed; three further
independent rounds followed; fixes were implemented and re-verified.

## Scope of what was run

| Round | Evaluators | Output |
|---|---|---|
| 1 | Opus 5 (A) + Codex gpt-5.6-sol (B), independent | `report_opusA.md`, `report_codexB.md`, `CROSS_REVIEW_round1.md` |
| fixes | phase 2 (7 items) | 37 new tests |
| 2 | Opus 5 fresh, Codex fresh, Opus 5 **red-team** — all independent | `report_round2_opus.md`, `report_round2_codex.md`, `report_round2_redteam.md`, `CROSS_REVIEW_round2.md` |
| fixes | phase 3 (6 items) | 84 new tests |

**5 independent evaluations, ~90 real CMIG runs**, all on genuine genome-scale
models with a licensed Gurobi solver. Nothing was assessed from source alone.

## Answers to the three scenarios

### S1 — best microbial combination for SCFA production
**Was: PARTIAL / unusable. Now: works, with a documented mathematical limit.**

Before, the documented `scfa` preset existed in `targets.py` and was accepted by
`solve` but **rejected by `search`** — the headline use case required hand-typing
six BiGG ids, and the winning score was a dimensionless `6.33e-05` with 4 of 6
SCFA fluxes exactly zero.

Now `cmig search --target-preset scfa --multi-metric carbon_equivalent` returns
**24.224 mmol C gDW⁻¹ h⁻¹** for `iHN637+iYO844`, with carbon numbers read from
the model formulas. Failed candidates are partitioned out with warnings instead
of silently vanishing, and ties / all-zero rankings are flagged.

**Remaining scientific limit (found by the red-team, and it is real):** a linear
carbon-weighted scalarisation **collapses onto the single highest-yield
metabolite** — the winner's "total SCFA" is acetate and nothing else. The
red-team refuted its own alternate-optima hypothesis with a probe (all six
per-target ranges width ≈ 0), proving this is a property of weighted-sum LP, not
a reporting artifact. A genuine trade-off answer needs Pareto/ε-constraint.
Codex separately noted CMIG's `scfa` set includes lactate and succinate, which is
broader than the conventional core SCFAs.

### S2 — microbe–microbe interaction simulation
**Was: silently confounded, with a P0 crash. Now: a controlled comparison.**

Cross-feeding was always biologically coherent (*B. subtilis* → *Geobacter*
acetate 3.43 mmol gDW⁻¹ h⁻¹, reciprocal branched-chain amino acids). Two defects
mattered:

1. **P0 crash** — a legitimate 2-member community (`iHN637+iYO844`) died with a
   raw `GurobiError`, exit 1. Root-caused to MICOM's pFBA second stage called
   unguarded. Reproduced by the coordinator; **now exits 0** with
   `pfba_stage_failed; reporting non-parsimonious flux distribution`.
2. **The alone-vs-community comparison was not controlled** — and after phase 2
   it *falsely asserted* that it was. Root cause ran deeper than the first fix
   found: an `_m` vs `_e` exchange-namespace mismatch, compounded by
   `apply_medium_checked` gating on `model.medium` so a medium could never
   *open* a closed exchange.

The corrected control **inverts a headline conclusion**: iYO844's reported
"4.75× community benefit" is really a **0.72× cost** (single 0.7773 vs community
0.5604). The coordinator reproduced this independently, and the fixed code
matches the evaluator's control leg to every printed digit.

### S3 — host–microbe interaction + microbial perturbation → host effect
**Was: not composable. Now: a supported command.**

All five evaluations independently reported the same gap: `gene-ko-search`
scored only a target metabolite and had **no host awareness whatsoever**, while
`host-microbe-bigg` accepted no perturbation input. Answering the actual question
required hand-editing a GEM and subtracting two runs.

`cmig host-ko-impact` now does it in one command, holding medium, interface map,
biomass basis, host objective, solver, tradeoff and abundances identical across
arms. Verified end-to-end by the coordinator:

```
baseline: host_objective=1.08736  host_status=optimal
iHN637:ACKr  delta_host_objective=+0.0606 (+5.57%)
iHN637:PTAr  delta_host_objective=+0.0582 (+5.35%)
warning: biomass basis is validation-only; this comparison is not publication-ready
```

It emits a delta only when **both** arms solve optimally — an infeasible baseline
yields a null delta and `status=failed` rather than a fabricated number.

**The standing limitation is not a defect:** no human GEM ships, so every host
number is a surrogate. CMIG labels this honestly everywhere. Scenario 3 becomes
publication-grade only with a real host model (Recon3D / Human-GEM) and a
reviewed interface map.

## Figures

**Both round-1 evaluators and all three round-2 evaluators independently called
the figures NOT publication-ready**, with near-identical quantitative findings.
Phase 3 fixed the mechanical blockers; coordinator-verified:

| Criterion | Before | After |
|---|---|---|
| Categorical palette | `#d62728`/`#1f77b4` (matplotlib `tab10`), 3 inconsistent palettes, deuteranopia ΔE76 **4.7–7.9** (floor 18.3) | **Okabe-Ito** (`#0072b2`, `#009e73`) |
| TIFF | 300 dpi, **RGBA**, `compression=raw`, 8.8–21.3 MB | **600 dpi, RGB, LZW**, 0.36–0.73 MB (~25× smaller) |
| Axis units | **0 of 10** figures | units on 14 axis labels (`Growth rate (h⁻¹)`) |
| `--journal-preset` | accepted, recorded in provenance, **never applied**; invalid names accepted | applied (`nature` → 3.5×3.0 in @300 dpi, PDF MediaBox 252×216 pt) and **rejects unknown names with exit 2** |
| SVG text | outlined to paths, **0 `<text>` elements** | selectable `<text>` (16 elements) |
| Panel letters | none anywhere | A/B/C added |
| Legends | circle & bubble had **none** | colour *and* size channels decoded |

The provenance layer (`figure_spec.json`, `render_provenance.json` with script
and input SHA-256) was already better than most published pipelines — both
round-1 evaluators said so unprompted.

## What the multi-round design actually bought

Round 2 existed because you asked for it, and it paid for itself twice:

1. **It caught a fix round that had introduced a false correctness assertion.**
   Phase 2 reported success on the medium fix; three independent evaluators
   proved the artifact was now *certifying* a controlled comparison that was not
   controlled. That is worse than the original bug, and no amount of re-reading
   the phase-2 diff would have found it — only re-running the science did.
2. **It found the mathematical reason S1 cannot answer its headline question**
   as posed, via a red-team probe that *refuted its own hypothesis*.

Divergences between evaluators were informative rather than noise: Opus rated S2
SUPPORTED where Codex rated it PARTIAL — same observed facts, different
threshold for "is an inferred edge safe to publish". Codex's stricter reading was
adopted.

**A coordinator error worth recording:** round-1 evaluator B ran partly against a
worktree that evaluator A was concurrently modifying. B detected this itself,
recorded source SHA-256 hashes, re-ran its decisive workflows, and correctly
discarded one transient error as non-reproducible. Phase 2/3 should have been
sequenced after both round-1 reports landed.

## Gates

`uv run pytest -q` → **612 passed, 2 skipped, 0 failed** (both skips pre-existing
Recon3D-fixture skips). `uv run ruff check cmig tests` → clean.
**121 new regression tests** across 9 new test files, each written against a
specific evaluator repro.

Changes: 13 files modified (+1864/−184), plus `cmig/core/host_ko_impact.py` and
9 new test files. Nothing committed — all changes are uncommitted working-tree
edits for your review.

## Status update — phase 4 (2026-07-26): all items below are now FIXED

Everything in this section was subsequently implemented and verified in phase 4
(commit `3b6d57c`, branch `fix/reproducibility-and-scenario-validity`). The list
is retained as the record of what the five evaluations found. Highlights:

- **Item 1 (manifest / `run_hash`)** — a versioned workflow manifest now covers
  every science command, recording the answer-determining parameters. The frozen
  11-component `community_solve` hash is untouched and verified bit-identical
  (`29844e29…cef29ab`); `golden verify` is green on both solvers. Hash
  determinism was checked in both directions: identical inputs reproduce it,
  changing `--growth-fraction` changes it.
- **Item 2 (linear-scalarisation collapse)** — `--multi-metric pareto` returns a
  genuine non-dominated front. Where the weighted sum returned only the acetate
  vertex (ac 12.112, rest 0), the front now also surfaces a trade-off point at
  ac 5.05 with lac__D 1.078, lac__L 1.062, ppa 0.783, succ 0.853.
- **Item 5 (edge identifiability)** — verified on a real 3-member solve: 16
  cross-feeding edges labelled `proportional_shared_pool` / `identifiable=False`
  against 80 direct exchange edges `direct_flux` / `identifiable=True`.
- **Item 3** — `target_influence_share` is now a flat 0.500 across the sweep
  (was an exactly inverted 0.75/0.50/0.25).
- **Item 4** — a failed scientific solve exits non-zero and figures drawn from a
  failed solve carry a "NOT A RESULT" banner.

The tidy schema bump (1.1 → 1.2) required regenerating the golden parquets. This
was done by a self-gating script that refuses to write unless every number is
bit-identical once the version stamp and new columns are excluded; independent
inspection confirmed `nodes`/`profile` differ **only** by `schema_version` and
that `weight` values are unchanged.

Gates after phase 4: **pytest 731 passed, 2 pre-existing skips, 0 failed**
(+121 regression tests total), ruff clean, `golden verify` green.

**What genuinely remains is not a defect:** no human GEM ships, so every S3
number is a surrogate — scenario 3 becomes publication-grade only with a real
host model (Recon3D / Human-GEM) and a reviewed interface map. The bundled pool
is also only 5 GEMs, so S1 tractability at 20–100 members remains unmeasured.

## Known-open items as found (now resolved — see above)

Reconciled against phase 3's explicit deferral list.

1. **No manifest / `run_hash` for the science commands** — null for every
   workflow except `solve`, so a published `search` / `host-*` / KO result cannot
   be re-derived. Flagged in all 5 evaluations and named by phase 3 as *the
   largest remaining reproducibility gap*.
2. **S1's linear-scalarisation collapse** — needs a Pareto/ε-constraint mode to
   answer "most total SCFA" as a genuine trade-off rather than an acetate
   specialist.
3. `abundance-impact`'s `target_influence_share` omits the abundance weight and
   reports an **exactly inverted** trend (red-team F4): 0.75/0.50/0.25 across the
   sweep where the abundance-weighted truth is a flat 0.50.
4. **Analysis failure still exits 0**, and a full interaction figure set is
   written from a *failed* host solve with no failure annotation (F9 / D10).
5. Inferred cross-feeding edges carry no `allocation_method` / `identifiable`
   field, and FVA-interval plumbing is absent for abundance sweeps and edges
   (R2-A D4/D5/D6).
6. dFBA can grow on untracked default nutrients while the managed substrate stays
   constant, making the Km experiment uninterpretable (Codex D5). dFBA and
   spatial numerics were not exercised in phase 3.
7. Multi-target search path emits **no figure and no `pool_diagnostics.csv`**
   although `cmig workflows` advertises both (D9).
8. `gene-ko-search` still ranks by absolute post-KO score with no degeneracy
   guard, so a zero-effect KO can hold rank 1 (B12 / B7 / F7).
9. Host interface map ships D↔L stereoisomer swaps (`arab__D_e → EX_arab__L_e`)
   in the same flat dict as exact matches.
10. `n_biomass` counts objective *terms*, not biomass reactions — iAF987's
    objective has **283 terms**, so its "growth rate" is an arbitrary objective
    value plotted under that label.

### Regression caught during phase 3

Partitioning the search paths on evaluability (P0-B) would have turned two
`gene-ko-search` `.ranks[0]` call sites into `IndexError` once a ranking could
legitimately be empty; both were fixed in the same pass. Three pre-existing tests
were deliberately updated because a fix changed their contract: strain-growth
status `optimal` → run-status tier, multi-target ranks `[1,2,3,4]` → `[1,2,3,0]`,
and a medium error message that is now English and generic.
