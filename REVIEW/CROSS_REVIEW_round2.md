# CMIG Round-2 Cross-Review — three independent evaluators on the fixed code

Coordinator synthesis of round 2. Three fresh evaluators re-tested the code
*after* the phase-2 fixes, independently, without reading each other or the
round-1 reports:

- **R2-A** — Claude Opus 5, fresh session, full re-test → `REVIEW/report_round2_opus.md` (42.3 KB)
- **R2-B** — Codex gpt-5.6-sol, fresh session, full re-test → `REVIEW/report_round2_codex.md` (41.5 KB)
- **R2-C** — Claude Opus 5, fresh session, **adversarial red-team** → `REVIEW/report_round2_redteam.md` (44.1 KB)

Combined with round 1, five independent evaluations now exist.

## 1. Headline: two phase-2 fixes did not hold

The most important result of round 2 is that **the fix round was itself
defective**, and all three evaluators caught it independently.

| Phase-2 claim | R2-A | R2-B | R2-C | Verdict |
|---|---|---|---|---|
| Solver failure degrades gracefully | HOLDS | PASS | (not challenged) | ✅ **Genuinely fixed** |
| Unevaluable candidates not ranked as zeros | HOLDS | FAIL/incomplete | FAIL | ⚠️ **Partly fixed** |
| Top-level status reflects worst sub-status | PARTIAL | FAIL | FAIL | ❌ **Incomplete** |
| `strain-growth` same medium on both legs | **DOES NOT HOLD** | **FAIL** | **FAIL (F3)** | ❌ **Regressed into a false assertion** |

### The regression that matters most

`strain-growth` now writes `single_medium_equals_community_medium: true` — an
assertion that is **measurably false**. Root cause, identified independently by
R2-A and R2-B: an **exchange-namespace mismatch**. The community uses `_m` ids
(`EX_glc__D_m`) while each single model uses `_e` (`EX_glc__D_e`), so the medium
is applied to *neither* single leg while the summary claims equality. Under
`--allow-unknown-medium`, every row records the exchange as absent yet
`single_medium_applied=true` and `warnings` is empty.

On the default path the community medium is far more permissive than each
member's native medium (R2-A measured iYO844: **+20 metabolites**, nh4/pi/so4
**5.0 → 999999**; R2-C measured a **+377 %** medium artefact). R2-A's control leg
**inverts the sign** of the iYO844 conclusion.

This is worse than the original bug. Before, the comparison was silently
confounded; now the artifact actively certifies that it is controlled when it is
not. A reviewer trusting that field would be misled.

## 2. Scenario verdicts across all five evaluations

| Scenario | R1-A | R1-B | R2-A | R2-B | R2-C | Consensus |
|---|---|---|---|---|---|---|
| S1 — best SCFA combination | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | **PARTIAL (5/5)** |
| S2 — microbe–microbe interaction | SUPPORTED | PARTIAL | NOT SUPPORTED *(as controlled comparison)* | PARTIAL | PARTIAL | **PARTIAL, trending down** |
| S3 — perturbation → host effect | PARTIAL | PARTIAL | PARTIAL *(member-level)* / NOT SUPPORTED *(gene-level)* | **NOT SUPPORTED** | PARTIAL | **NOT SUPPORTED at gene level (5/5)** |
| Figures publication-ready | No | No | No | No | No | **No (5/5)** |

S2's verdict **fell** between rounds — not because the code got worse, but
because round 2 tested the *medium control* claim directly and found it false.
R2-A's framing is the precise one: S2 is a sound **descriptive readout** and an
unsound **controlled comparison**.

## 3. What round 2 added that round 1 missed

**R2-C (red-team), ranked by scientific damage:**

- **F1 (P0)** — `--top-k` truncation **hides failures**. Same pool, same command:
  `--top-k 10` shows the infeasible candidate `iAF987+iYO844`; `--top-k 2` makes
  it vanish. Status stays `ok`, `warnings: []`. The user cannot tell that a
  candidate was never evaluated.
- **F2 (P0)** — `search_summary.json` hardcodes `"status": "ok"` even when
  **100 % of candidates were unevaluable**.
- **F4 (P1)** — `abundance-impact`'s headline `target_influence_share` mixes
  bases and reports an **exactly inverted** trend.
- **F5 (P1)** — the pFBA→FBA fallback mixes flux-normalisation bases *inside one
  sweep*, and `abundance-impact` drops the warning entirely — so one column can
  contain numbers computed on two different bases with no marker.
- **F7 (P1)** — `gene-ko-search` ranks by absolute post-KO score, so rank 1 is a
  knockout with `delta = 0`, unflagged. (Round 1 found the inverse-ranking issue;
  round 2 found it also promotes no-effect KOs.)
- **F9 (P2)** — a complete interaction figure set is written from a **failed**
  host solve, unannotated, exit 0.
- **F12 (P2)** — provenance fields accept text that contradicts what the run did.

**R2-C's honest negative (methodological integrity):** it hypothesised that the
winning consortium's `but/ppa/lac/succ = 0` values were non-identifiable
alternate optima, then **refuted its own hypothesis** with a probe pinning the
joint objective and re-optimising each target: all six ranges came back width
≈ 0. This yields a genuine scientific insight rather than a bug:

> **A linear carbon-weighted scalarisation of a multi-metabolite objective
> collapses onto the single highest-carbon-yield metabolite.** The winner's
> "total SCFA" is acetate and nothing else — that is a property of linear
> scalarisation, not a reporting artifact.

So S1's deeper limitation is *mathematical*, not cosmetic: answering "which
combination makes the most SCFA" with a weighted-sum LP will always return an
acetate specialist. A genuine trade-off answer needs Pareto/ε-constraint or a
non-linear formulation. **No evaluator in round 1 reached this.**

**R2-B (Codex)** added a scientific critique of the preset itself: CMIG's `scfa`
set includes **lactate and succinate**, which are broader than the conventional
core SCFAs (acetate, propionate, butyrate). Users comparing against SCFA
literature would be comparing different quantities.

**R2-A** added that the multi-target path emits **no figure and no
`pool_diagnostics.csv`** although `cmig workflows` advertises both, and that
`--medium` is broken by the same `_m`/`_e` mismatch.

## 4. Confirmed genuinely fixed

- **The P0 crash is really gone.** Round 1's `GurobiError` traceback (exit 1) now
  returns `status=solver_failed` with a structured diagnostic. R2-A probed it
  directly and confirmed no exception escapes; R2-B passed five focused
  solver-guard tests. Coordinator independently verified: exit 0 with
  `warning: pfba_stage_failed; reporting non-parsimonious flux distribution`.
- **The SCFA preset and a physical metric now exist.** `--target-preset scfa` and
  `--multi-metric carbon_equivalent`, with carbon numbers read from model
  formulas (`ac:2 but:4 lac:3 ppa:3 succ:4`) and `score_unit: mmol C gDW^-1 h^-1`.
  All three round-2 evaluators independently confirmed this works.
- **Zero-ranking guard works** on the multi-target path: R2-A observed
  `no candidate achieved a non-zero target flux; the ranking order is arbitrary
  and rank 1 must not be reported as the best producer`.
- **`host-microbe-bigg` is the most honest command in the tool** (R2-C's words):
  reports `status: failed` on host infeasibility, keeps `lumen_uptake_ranges`
  with an `identifiable` flag, and warns that member allocation "is not causal or
  uniquely identifiable".

## 5. Unanimous across all five evaluations

These are no longer debatable:

1. **No KO → host-effect workflow exists.** `gene-ko-search` reports target
   metabolite flux only and emits no modified model; `host-microbe-bigg` accepts
   no perturbation input. Both round-1 evaluators and all three round-2
   evaluators independently reached this, and two of them built the manual
   bridge to prove the semantics are well-defined.
2. **Figures are not publication-ready**: no axis units, no panel letters,
   `--journal-preset` ignored *and* unvalidated, non-Okabe-Ito inconsistent
   palettes, automatic TIFFs 300 dpi RGBA uncompressed (vs the R path's correct
   600 dpi RGB LZW), missing legends on the network figures.
3. **Reproducibility is incomplete**: `run_hash` is null for every workflow
   except `solve`.
4. **Inferred cross-feeding edges are not labelled as inferred** in
   `edges.parquet` or the manifest.

## 6. Assessment

Round 2 did exactly what a second opinion is supposed to do: it caught a fix
round that had introduced a **false correctness assertion**, and it found the
mathematical reason S1 cannot answer its headline question as currently posed.
Neither would have surfaced from a single evaluation, and the false assertion
would not have surfaced without re-testing the fixes specifically.

Phase 3 has been dispatched against P0-A (medium namespace + honest assertion),
P0-B (single-target search status/truncation), P0-C (unevaluable candidates
holding ranks), P0-D (worst-status semantics), P1-E (the composed KO → host
workflow), and P1-F (figure fundamentals).

The remaining strategic gap is not a defect at all: **no human GEM ships**, so
every S3 number is a surrogate. CMIG labels this honestly everywhere, which is
the right behaviour — but scenario 3 cannot become publication-grade until a
real host model (Recon3D / Human-GEM) and a reviewed interface map are supplied.
