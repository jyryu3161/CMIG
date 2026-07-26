# CMIG Round-2 Adversarial Red-Team — Evaluator R2-C

**Evaluator:** R2-C (Claude Opus 5, fresh session, independent)
**Lens:** adversarial — *can CMIG be made to emit a wrong or misleading scientific result that a
competent user would believe?*
**Date:** 2026-07-25
**Environment:** cobra 0.31.1, micom 0.39.0, Gurobi 12.0.3 (academic, exp. 2027-05-27),
matplotlib 3.10.9, Python 3.12. All runs `uv run cmig ...` from `/Users/jaeyongryu/orca/CMIG`.
**Artifacts:** `runs/r2red/<name>` (13 run dirs), probes in `REVIEW/scratch_r2red/`.
**Read-only on source** — nothing under `cmig/`, `tests/`, `pyproject.toml` was modified.

Every number below was read out of a real artifact produced by a command I ran. Every finding was
re-run at least once. Section 6 lists what I suspected but **could not** confirm, including one
hypothesis my own probe **refuted**.

---

## 1. Verdict table

| Scenario | Verdict | Ran end-to-end? | Evidence | Blocking gap |
|---|---|---|---|---|
| **S1** — best SCFA-producing combination | **PARTIAL** | Yes (`runs/r2red/s1_scfa_carbon`, 153 s) | `--target-preset scfa --multi-metric carbon_equivalent` works; carbon numbers read from model formulas (`ac:2 but:4 lac__D:3 lac__L:3 ppa:3 succ:4`, sourced `iAF987:ac_e` …), `score_unit: "mmol C gDW^-1 h^-1"`, `status: "degraded"`, unevaluable + partial-exchange combos warned. | The **single-target** `search` path silently drops candidates that fail to solve and still reports `status: "ok"`, `warnings: []` (**F1, F2**). `pareto` is hard-`false` and never computed for ≠2 targets (**F8**). No figures on the multi-target path. No run provenance (**F6**). |
| **S2** — microbe–microbe interaction | **PARTIAL** | Yes (`s2_strain_growth` 16 s, `s2_abundance` 42 s) | Cross-feeding is genuinely demonstrable: community net acetate export = 0 while iHN637 secretes +7.14 and iYO844 consumes it at exactly the abundance-weighted matching rate. | Alone-vs-community is **not** a controlled comparison by default and the summary asserts it is (**F3**, +377 % medium artefact). The headline `target_influence_share` is mis-based and reports an **inverted trend** (**F4**). pFBA→FBA fallback mixes flux bases inside one sweep with the warning dropped (**F5**). dFBA not tested (§6). |
| **S3** — host coupling + microbial perturbation → host effect | **PARTIAL** | Yes (`s3_host` 14 s, `s3_geneko` 63 s) | `host-microbe-bigg` is the most honest command in the tool: reports `status: "failed"` on host infeasibility, keeps `lumen_uptake_ranges` with an `identifiable` flag, and warns that member allocation "is not causal or uniquely identifiable". | **No command chains a gene/reaction KO to a host-objective delta.** `gene-ko-search` reports target-metabolite flux only; `host-search-bigg` takes no KO input. `gene-ko-search` also ranks by absolute score, so rank 1 is a KO with `delta = 0` and no tie warning (**F7**). Full figure set is written from a failed host solve with no failure annotation (**F9**). |

---

## 2. Findings, ranked by scientific damage

### F1 (P0) — `search` silently excludes candidates that failed to solve; no warning, `status: "ok"`

**Repro — bundled models only, no synthetic input.** Same command twice, only `--top-k` differs:

```bash
# pool3 = symlinks to models/{iAF987,iHN637,iYO844}.xml
uv run cmig search --model-dir REVIEW/scratch_r2red/pool3 --target ac \
  --min-size 2 --max-size 2 --top-k 10 --out runs/r2red/x_real_topk10   # exit 0, 36.7 s
uv run cmig search --model-dir REVIEW/scratch_r2red/pool3 --target ac \
  --min-size 2 --max-size 2 --top-k 2  --out runs/r2red/x_real_topk2    # exit 0, 37.0 s
```

**Observed, `--top-k 10` (`x_real_topk10/search_rankings.csv`):**

```
1,iHN637+iYO844,12.1119592763,...,optimal,
2,iAF987+iHN637,5.11774566687,...,optimal,
3,iAF987+iYO844,,0,0,...,infeasible,target LP returned no solution object (solver_status=infeasible)
```

**Observed, `--top-k 2` (`x_real_topk2/search_rankings.csv`) — the failure is gone:**

```
1,iHN637+iYO844,12.1119592763,...,optimal,
2,iAF987+iHN637,5.11774566687,...,optimal,
```

Both runs: `search_summary.json` → `"status": "ok"`, `"warnings": []`,
`"n_candidates_evaluated": 3`, `"n_candidates_total": 3`.
stdout → `evaluated: 3/3` + `best: iHN637+iYO844 flux=12.11`.
`uv run cmig inspect-run --run-dir runs/r2red/x_real_topk2 --format json` →
`{'status': 'ok', 'status_source': 'summary', 'run_hash': None}`.

Scaled repro (`x_mixed_pool`, 4-member pool, 6 candidates, `--top-k 10`): **3 of 6 candidates
`infeasible`**, `pool_diagnostics` completely clean (4 readable / 4 with biomass / 4 with target
exchange), and still `"status": "ok"`, `"warnings": []`.

**What a scientist would wrongly conclude:** "We exhaustively screened all 3 (or all 6) pairwise
consortia; the ranking is complete and `iHN637+iYO844` is the best acetate producer." The stdout
line `evaluated: 3/3` actively reinforces this.
**Correct interpretation:** one third to one half of the candidate space was never scored. A combo
that could not be evaluated is indistinguishable, in the user-facing artifacts, from a combo that
was evaluated and lost.

**Root:** `cmig/core/search_product.py::search_model_pool` — failed/`missing` combos get
`score = -inf`, sort to the bottom, and are then cut by `ranks[: config.top_k]`.
`_ranking_degeneracy_warnings` only warns about all-zero and ties; the "some combinations were not
evaluable" warning exists **only** in the multi-target path
(`search_product.py::_multi_target_warnings`) and was never ported to the single-target path.
`cmig/cli/main.py::_write_search_outputs` writes `"status": "ok"` as a literal.

---

### F2 (P0) — `search_summary.json` hardcodes `"status": "ok"`, even when 100 % of candidates were unevaluable

`cmig/cli/main.py::_write_search_outputs` line ~3160: `payload = {"status": "ok", ...}`. The
multi-target sibling `_write_multi_target_outputs` correctly uses `_worst_status(...)` — the
round-1 fix was applied to one of the two writers.

**Repro:**

```bash
uv run cmig search --model-dir REVIEW/scratch_r2red/pool3 --target zzz \
  --min-size 2 --max-size 2 --top-k 10 --out runs/r2red/s1_missing_target   # exit 0, 33.0 s
```

**Observed:** every one of 3 candidates `status: "missing"`, `score: null`,
`diagnostic: capability_missing … EX_zzz_m`. Yet:

* stdout: `best: iAF987+iHN637 flux=0 growth=0` — a **"best" is printed for a run in which nothing
  was evaluated**, and it is printed *before* any warning line.
* `search_summary.json` → `"status": "ok"`.
* `inspect-run` → `"status": "ok"`, `"status_source": "summary"`.
* The all-zero degeneracy guard **does not fire**: `_ranking_degeneracy_warnings` returns early
  (`if not evaluable: return warnings`) precisely when *nothing* is evaluable — the worst case.
  The only warning present is the pool-level `"target exchange was not detected in any individual
  pool model"`.
* `search_rankings.csv` assigns `rank` 1/2/3 with `target_flux 0` to all three, which is exactly
  the "unevaluable ranked as zero" pattern the round-2 brief says was fixed.

**Wrong conclusion:** an automated pipeline gating on `status == "ok"` (which is what
`inspect-run` is for, per `SKILL.md`) accepts this run. A human reading stdout records
`iAF987+iHN637` as the top producer.
**Correct:** status should be `failed`; there is no ranking.

---

### F3 (P0) — `strain-growth` alone-vs-community is **not** a controlled comparison by default, and the summary asserts that it is

The `--medium` case was fixed; the **default** case (no `--medium`, which is the documented
example) was not. `cmig/cli/main.py::_cmd_strain_growth` sets
`single_medium_applied = medium_spec is None  # medium 미지정 → 양쪽 모두 모델 기본 경계`.
That premise is false: micom's `Community` medium is the **union** of member media with relaxed
bounds, not each model's own default.

**Repro (probe):** `uv run python REVIEW/scratch_r2red/medium_probe.py`

```
community medium size: 26
iHN637: solo n=22  →  4 nutrients open in community but not solo: ['co2','fe3','glc__D','o2']
                      6 ids with raised uptake bound (1000 → 999999)
iYO844: solo n=13  → 13 nutrients open in community but not solo:
                      ['btn','cl','cobalt2','cu2','fe2','fol','fru','mn2','mobd','ni2','ribflv','thm','zn2']
                      nh4 5.0 → 1000.0, pi 5.0 → 1000.0, so4 5.0 → 1000.0   (200× N, P, S)
```

**Quantified** (`uv run python REVIEW/scratch_r2red/quantify_medium_effect.py`), same model, FBA,
medium is the only thing changed:

| member | CMIG `single_growth` (own medium) | same model on the **community** medium | medium-only inflation |
|---|---|---|---|
| iHN637 | 0.224455 h⁻¹ | 0.299255 h⁻¹ | **+33.3 %** |
| iYO844 | 0.117966 h⁻¹ | 0.563191 h⁻¹ | **+377.4 %** |

**End-to-end run:**

```bash
uv run cmig strain-growth --model-dir REVIEW/scratch_r2red/pool2 --out runs/r2red/s2_strain_growth
```

`strain_growth_summary.json`:

```json
"medium_basis": { "medium_source": "model_default_bounds",
                  "medium_checksum": "micom_default_medium",
                  "single_medium_equals_community_medium": true }
"members": [ {"member":"iYO844","single_growth":0.11796638932239924,
              "community_member_growth":1.1697202498991868, ...} ]
```

No medium warning is emitted (`warnings` contains only the pFBA fallback).

**Wrong conclusion:** "iYO844 grows 9.9× faster in co-culture with iHN637 (0.118 → 1.170 h⁻¹) —
strong positive cross-feeding." `strain_growth_plot.svg` renders exactly that as a two-bar
comparison.
**Correct:** at least the 0.118 → 0.563 h⁻¹ portion (**≈ 78 % of the log-fold change**) is a
medium change, not an interaction. The remaining 0.563 → 1.170 is the only part that is a
candidate interaction effect, and even that is confounded by micom's abundance normalisation.
The field `single_medium_equals_community_medium: true` is an affirmative false statement of
experimental control.

**Scope:** the same default-medium union applies to `search`, `abundance-impact`,
`gene-ko-search` and `host-microbe-bigg`. For those it is a background assumption; for
`strain-growth` it is the entire quantity being measured.

---

### F4 (P1) — `abundance-impact`: `target_influence_share` mixes bases and reports an **exactly inverted** trend

`cmig/cli/main.py::_cmd_abundance_impact` lines 1721-1728:

```python
total_member_abs = sum(abs(float(ex.get(args.target, 0.0)))
                       for ex in result.member_exchange.values())
influence_share = abs(target_member_exchange) / total_member_abs
```

`result.member_exchange` values are micom **per-taxon** fluxes (mmol gDW_taxon⁻¹ h⁻¹). The
community-level contribution is `flux × abundance`. The abundance weight is missing, and `abs()`
puts consumers in the numerator/denominator alongside producers.

**Repro:**

```bash
uv run cmig abundance-impact --model-dir REVIEW/scratch_r2red/pool2 \
  --member iHN637 --target ac --out runs/r2red/s2_abundance     # exit 0, 42.1 s
```

**Observed (`abundance_impact.csv`), and the correct value recomputed from CMIG's own numbers:**

| `target_abundance` | `target_member_exchange` | CMIG `target_influence_share` | abundance-weighted share (correct) |
|---|---|---|---|
| 0.25 | 7.14445047716 | **0.75** | 0.500 |
| 0.50 | 3.80404525211 | **0.50** | 0.500 |
| 0.75 | 2.71113283097 | **0.25** | 0.500 |

Derivation (exact, two members, `share = |m| / (|m|+|o|)` inverts to give `o`):
`m·a` = 7.14445×0.25 = 1.78611; 3.80405×0.5 = 1.90202; 2.71113×0.75 = 2.03335, and in each case
`|o|·(1−a)` is *numerically identical* to `m·a` — i.e. the two members' community-level acetate
contributions are equal at every sweep point, so the true share is a flat **0.500**.

**Wrong conclusion:** "iHN637's influence on community acetate falls monotonically from 0.75 to
0.25 as its abundance rises from 25 % to 75 % — adding more iHN637 makes it *less* important."
`abundance_impact_plot.svg` plots this declining line as its third panel, labelled `Target share`.
**Correct:** the share is constant at 0.50; the apparent decline is entirely the missing abundance
weight (micom per-taxon fluxes scale as ~1/abundance).

**Second defect in the same number:** at abundances 0.25/0.50/0.75 the community net acetate
export is `0.0` while `target_member_exchange` is 7.14/3.80/2.71 — i.e. the partner is *consuming*
acetate at the matching rate. `abs()` therefore credits the consumer as a contributor to
"target influence". A share of 0.75 in a community whose net target export is zero is not a
production share.

---

### F5 (P1) — pFBA→FBA fallback mixes flux-normalisation bases inside one sweep; `abundance-impact` drops the warning entirely

`cmig/core/engine.py::_delegate_cooperative_tradeoff` retries `pfba=False` when the pFBA stage
throws and attaches `PFBA_FALLBACK_WARNING` ("reporting non-parsimonious flux distribution").

**Observed in `runs/r2red/s2_abundance/abundance_impact.csv`:** row 1 (abundance 0.10) has an
empty `diagnostic`; rows 2–4 (0.25 / 0.50 / 0.75) each carry
`solver_error: pFBA flux stage failed: GurobiError: Unable to retrieve attribute 'X'`.
So **1 of 4 sweep points is a pFBA flux distribution and 3 of 4 are plain FBA** — different flux
vectors at the same growth rate, plotted as one continuous curve.

And:

* every row still reads `status: "optimal"`;
* `abundance_impact_summary.json` top level reads `"status": "ok"`. The derivation
  (`cmig/cli/main.py::_write_abundance_impact_outputs` line 2058) is
  `"ok" if any(row["status"] == "optimal" for row in rows) else "failed"` — **one** optimal point
  out of any number is enough to report `ok`; there is no `degraded` tier on this path;
* the summary has **no `warnings` key at all** (`KEYS: ['artifacts','member_growth_rows','rows',
  'solver','status','target','target_member','tradeoff_f']`) — the engine's fallback warning is
  discarded on this path, unlike `strain-growth`, which does surface it.

**Wrong conclusion:** the `Exchange flux` vs `abundance` curve is a like-for-like sensitivity
scan. **Correct:** three of four points use a different flux-selection rule than the first, which
is exactly the kind of difference the parsimony assumption exists to remove. The user cannot learn
this without JSON-parsing the `diagnostic` column of the CSV.

`strain-growth` has the milder version of the same problem: `warnings` contains the fallback and
`diagnostic` contains the raw `GurobiError`, yet `strain_growth_summary.json` still reports
`"status": "optimal"` and `inspect-run` reports `status: "optimal"` — the top-level status does
not reflect the worst sub-status.

---

### F6 (P1) — the science commands emit no manifest, no `run_hash`, and no record of the parameters that determine the answer

`inspect-run --format json` on every product run in this evaluation returns
`"run_hash": null, "manifest": {}`:
`s1_single_but`, `s1_missing_target`, `s1_scfa_carbon`, `s2_strain_growth`, `s2_abundance`,
`s3_geneko`, `s3_host`, `x_real_topk2`, `x_real_topk10`, `x_mixed_pool`, `x_mixed_topk3`.

By contrast `uv run cmig solve-fixture --out runs/r2red/x_solvefixture` (1.65 s) produces a full
`manifest.json`: `run_hash 29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab`,
`manifest_schema_version 2.0`, `software.dependency_versions {cmig 0.1.0, cobra 0.31.1,
gurobipy 12.0.3, micom …}`, `inputs.medium_checksum`, `inputs.model_checksum`,
`inputs.abundance`, `inputs.namespace_mapping_decisions`.

**What is missing from `search_summary.json` (verified via `inspect-run` `summary_keys`):**
`growth_fraction`, `solver`, `medium` / `medium_checksum`, `seed`, `n_samples`, `strategy`
parameters other than the resolved name, model file checksums, and all software versions.
The multi-target summary adds `weights`/`metric`/`normalizer` but likewise omits
`growth_fraction`, `solver`, and `medium`.

`--growth-fraction` alone changes the answer materially (it is the growth floor of the target-max
LP) and defaults silently to 0.5. **A published `search` result cannot be re-derived from its own
run directory.** Only `pool_taxonomy.csv` (file paths, no hashes) survives.

---

### F7 (P1) — `gene-ko-search` ranks by absolute post-KO score, so rank 1 is a knockout with `delta = 0`, with no tie warning

**Repro:**

```bash
uv run cmig gene-ko-search --model-dir REVIEW/scratch_r2red/pool2 \
  --members iHN637,iYO844 --member iHN637 --target ac \
  --max-genes 6 --top-k 10 --out runs/r2red/s3_geneko          # exit 0, 63.4 s
```

**stdout:** `best: iHN637:CLJU_RS00085 delta=0 score=12.11`

**`gene_ko_rankings.csv`:**

```
1,iHN637,CLJU_RS00085,12.1119592763,0,...              ← knockout changes nothing
2,iHN637,CLJU_RS00300,12.1119592763,0,...              ← knockout changes nothing
3,iHN637,CLJU_RS00330,12.1119592763,0,...              ← knockout changes nothing
4,iHN637,CLJU_RS00320,12.1119272797,-3.19966181621e-05,...
5,iHN637,CLJU_RS00340,11.0294642854,-1.08249499089,...  ← the only genes that matter
6,iHN637,CLJU_RS00465,11.0050986554,-1.10686062088,...
```

`warnings` contains only the (correct, good) truncation notice
`"iHN637: evaluated 6 of 637 genes (selection=id); raise --max-genes (0=all) for full coverage"`.
There is **no all-tied / zero-delta warning** — `_ranking_degeneracy_warnings` was added to
`search_product.py` but not reused here. `search_summary`-equivalent reports `"status": "ok"`;
`inspect-run` → `status: ok`.

**Wrong conclusion:** "`CLJU_RS00085` is the top single-gene knockout target for acetate in
iHN637." It is the alphabetically first gene whose knockout does literally nothing; ranks 1–3 are
an exact three-way tie at the baseline value.
`cmig/cli/main.py::_write_gene_ko_search_outputs` line 1835 also writes `"status": "ok"` as a
literal, the same defect as F2.
**Correct:** no screened knockout increases acetate; the informative result is that
`CLJU_RS00340`/`CLJU_RS00465` *reduce* it by ~1.1 mmol gDW⁻¹ h⁻¹ — and those sit at the *bottom*
of the list.

**Internal inconsistency:** `gene_ko_plot.svg` ranks by `score_delta` (top bar
`iHN637:CLJU_RS00465`, legend explicitly includes `no change`), so **the figure's first entry and
the CSV's rank 1 are different genes**. The figure is the honest artifact; the CSV, JSON and
stdout are not.

Also relevant to S3: `--gene-selection id` (the default) screens genes in locus-tag order, i.e. a
contiguous chromosomal block, not a random sample. The warning says "raise `--max-genes`" but does
not say the truncated subset is systematically biased.

---

### F8 (P1) — `search_plot.svg` misrepresents uptake searches: wrong title, wrong caption, sign encoded by colour alone, label off-canvas

**Repro:**

```bash
uv run cmig search --model-dir REVIEW/scratch_r2red/pool3 --target ac \
  --direction max_uptake --min-size 2 --max-size 2 --top-k 10 \
  --out runs/r2red/s1_uptake_fig                                # exit 0, 37.4 s
```

**Observed in `s1_uptake_fig/search_plot.svg`:**

```
<text ...>Target production search: ac</text>
<text ...>Target exchange flux (EX_ac_m), larger is better for max secretion</text>
<rect x="123" y="130.5" width="817" ... fill="#e6550d"/>   ← flux = −8.88, full-width bar
<rect x="123" y="172.5" width="817" ... fill="#e6550d"/>   ← flux = −8.88, full-width bar
<rect x="123" y="214.5" width="0"   ... fill="#2ca25f"/>   ← flux =  0
<text x="948" ...>-8.88</text>                             ← starts at x=948 on a 980-px canvas
```

Four defects in one figure, all from `cmig/cli/main.py::_write_search_svg`:

1. Title says **"production"** and caption says **"larger is better for max secretion"** — both
   hardcoded; `result.direction` (`max_uptake`) is never consulted or shown.
2. Bar length uses `abs(row.target_flux)`, so the two strongest **consumers** get the longest bars
   in a chart titled "production search".
3. Consequently **sign is carried by colour alone** (`#2ca25f` green vs `#e6550d` orange) — the
   classic red-green confusion pair, so a deuteranopic reader gets no sign information at all.
4. The `-8.88` value label is placed at x=948 on a 980-px canvas and is clipped.

**Wrong conclusion:** from the figure alone, "iAF987+iHN637 and iAF987+iYO844 are the strongest
acetate producers." **Correct:** they are the strongest acetate *consumers*; the run maximised
uptake. (The CLI *does* correctly warn about the top-2 tie here — that fix works.)

---

### F9 (P2) — `host-microbe-bigg` writes a complete interaction figure set from a failed host solve, with no failure annotation, and exits 0

**Repro:**

```bash
uv run cmig host-microbe-bigg --host REVIEW/scratch_r2red/toy_host.xml \
  --model-dir REVIEW/scratch_r2red/pool2 --exchange-suffix _lumen \
  --microbial-biomass-gdw 1.0 --host-biomass-gdw 1.0 \
  --biomass-basis-kind measured \
  --biomass-basis-source "TBD - I have not measured this yet" \
  --out runs/r2red/s3_host                                       # exit 0, 14.3 s
```

**JSON is honest:** `status: "failed"`, `host.status: "infeasible"`, `host.objective_value: 0.0`,
`microbe_to_host: {}`, `matched_exchanges: {}`, and five useful warnings including
`"host solve was not optimal (status=infeasible); the reported host objective is not a result"`.
`microbe_to_host.csv` correctly carries `identifiable=False` on every row.

**The figures are not.** Written anyway: `interaction_circle.svg/.tiff`,
`interaction_heatmap.svg/.tiff`, `interaction_bubble.svg/.tiff`,
`member_contribution.svg/.tiff`. The heatmap is titled *"Aggregate interaction heatmap"* with a
colourbar labelled *"Flux"* (0.0–3.5, **no units**) over 11 metabolites × 2 members; the circle is
titled *"Interaction circle"*. **Nothing on any figure indicates that the host leg was infeasible
or that `used_by_host` is `false` for every single edge** in `interaction_edges.csv`.

Process exit code is **0** despite `status: "failed"`, so a shell pipeline gating on `$?` accepts
the run.

**Wrong conclusion:** a reader handed `interaction_heatmap.tiff` sees a publication-shaped
host–microbe interaction figure. **Correct:** zero metabolites were transferred to the host; the
figure shows only the microbial secretion profile, and the host model was infeasible under the
coupling.

---

### F10 (P2) — multi-target `pareto` is hard-`false` when the target count ≠ 2, and is never flagged as not-computed

`cmig/core/search_product.py::rank_multi_target` computes the Pareto flag only inside
`if len(mets) == 2:`. With `--target-preset scfa` (6 targets) the field stays at its dataclass
default `False` for every row.

**Observed** (`runs/r2red/s1_scfa_carbon`): stdout
`best: iHN637+iYO844 score=24.22 pareto=False`; `search_rankings.csv` has a `pareto` column of
`False` for all rows; `search_summary.json` `top_ranked[*].pareto = false`. No warning states that
the Pareto analysis was not run.

**Wrong conclusion:** "even the top consortium is Pareto-dominated." **Correct:** the Pareto
frontier was never evaluated. `false` here means "not computed", not "dominated" — a boolean whose
two meanings are collapsed.

Two smaller items in the same run:

* The multi-target path writes **only** `pool_taxonomy.csv`, `search_rankings.csv`,
  `search_summary.json` — **no figures at all**, while the single-target path writes four. So the
  headline S1 workflow has no plot.
* Rank 3 (`iAF987+iYO844`, `status: infeasible`) still carries per-target fluxes
  `lac__L 2.352, ppa 1.210, succ 2.293` from the capability pass, and `flux_ac 0.0` where `0.0`
  means *the acetate LP was infeasible*, not *this consortium makes no acetate*. The
  `flux_basis: per_target_capability_not_simultaneous` column is the mitigation and it does its
  job, but the per-target `0.0`-means-unknown collision is not disambiguated anywhere.

---

### F11 (P2) — `inspect-run` status vocabulary is inconsistent, and the fallback path returns `"ok"` for an unknown summary

Observed statuses from the same `inspect-run` command across run kinds:

| run | `status` | `status_source` |
|---|---|---|
| `x_real_topk2` (search) | `ok` | summary |
| `s1_scfa_carbon` (multi-target search) | `degraded` | summary |
| `s2_strain_growth` | **`optimal`** | summary |
| `s3_host` | `failed` | summary |
| `s3_geneko` | `ok` | summary |
| `x_solvefixture` | `ok` | derived |

`optimal` is not a member of `_STATUS_SEVERITY = ("ok","degraded","failed")`, so any automated
gate written against that vocabulary either rejects a good run or, if it uses a whitelist, silently
mis-handles it.

Separately, `cmig/cli/main.py::_resolve_run_status` ends with `if summary: return "ok", "derived"`
— a summary JSON with no `status`, no `top_ranked`, no `reports` and no manifest is reported as
**ok**. The function's own docstring says "모르면 ok 라고 하지 않는다" (*if unknown, do not say ok*).
I did not find a shipped command that hits this branch, so I am reporting it as a code-path risk,
not a confirmed run (see §6).

---

### F12 (P2) — provenance fields accept text that contradicts what the run did

`--biomass-basis-kind measured --biomass-basis-source "TBD - I have not measured this yet"` was
accepted and recorded verbatim in `host_microbe_bigg_summary.json`:

```json
"coupling_scale": {"basis_kind": "measured",
                   "basis_source": "TBD - I have not measured this yet",
                   "microbe_to_host_ratio": 1.0, ...}
```

`cmig/core/host.py::_coupling_scale` only rejects an *empty* source string. The `measured` kind is
the flag that marks a run publication-ready (vs `validation`), so the only guard between
"publication-ready" and "unmeasured" is a non-empty string. This is garbage-in, but the field is
load-bearing for the tool's own publication gate, so it deserves at minimum a shape check
(DOI / accession / method keyword) or a `warnings` entry when the string looks like a placeholder.

---

### F13 (P3) — smaller confirmed defects

* **Mislabelled error class.** `uv run cmig search ... --medium /nope/none.csv` prints
  `failed to write search outputs: medium 파일 없음: /nope/none.csv` — a *read* failure reported
  under the `except OSError` handler labelled "failed to write". Misleads debugging.
  (`cmig/cli/main.py::_cmd_search`.)
* **`n_biomass` diagnostic over-matches.** `pool_diagnostics.csv` reports
  `iAF987, n_reactions 1285, n_biomass 283` — 22 % of all reactions classified as biomass
  reactions, vs `1` for iHN637 and iYO844. This is the field a user checks to confirm each pool
  model has a usable objective. Root cause not investigated.
* **Negative zero in CSV.** `x_real_topk10`-style runs write `score = -0` for a zero-score row
  (`s1_uptake_fig/search_rankings.csv` rank 3). Cosmetic, but it parses as a distinct value in
  some downstream tools.
* **`candidate_combinations` silently clamps `max_size`** to the pool size
  (`search_product.py`), so `--max-size 5` on a 3-model pool quietly becomes `--max-size 3` with
  no note in `search_summary.json`.

---

## 3. Evidence log

| # | Command (abridged) | Exit | Wall | Key numbers | Artifact |
|---|---|---|---|---|---|
| 1 | `search --model-dir pool3 --target but --min-size 2 --max-size 2 --top-k 10` | 0 | 40.0 s | all 3 candidates flux 0; degeneracy warning fired correctly | `runs/r2red/s1_single_but` |
| 2 | `search … --target zzz --top-k 10` | 0 | 33.0 s | 3/3 `missing`; `status ok`; `best:` printed | `runs/r2red/s1_missing_target` |
| 3 | `search … --target-preset scfa --multi-metric carbon_equivalent` | 0 | 153.7 s | best `iHN637+iYO844` 24.2239 mmol C gDW⁻¹ h⁻¹ (ac 12.1120, all others 0); `status degraded`; 2 warnings; carbon numbers 2/4/3/3/3/4 | `runs/r2red/s1_scfa_carbon` |
| 4 | `search … --target ac --direction max_uptake --top-k 10` | 0 | 37.4 s | flux −8.88 ×2 (tie warned); figure caption wrong | `runs/r2red/s1_uptake_fig` |
| 5 | `strain-growth --model-dir pool2` | 0 | 15.9 s | iHN637 0.2245→9.09e-18; iYO844 0.1180→1.1697; `single_medium_equals_community_medium: true` | `runs/r2red/s2_strain_growth` |
| 6 | `abundance-impact --member iHN637 --target ac` | 0 | 42.1 s | share 0.5874/0.75/0.50/0.25; community net ac 0.0 at 3 of 4 points; 3 of 4 rows pFBA-failed | `runs/r2red/s2_abundance` |
| 7 | `gene-ko-search --member iHN637 --target ac --max-genes 6` | 0 | 63.4 s | ranks 1–3 delta exactly 0; ranks 5–6 delta −1.082 / −1.107 | `runs/r2red/s3_geneko` |
| 8 | `host-microbe-bigg --host toy_host.xml --exchange-suffix _lumen` | 0 | 14.3 s | `status failed`; host infeasible; `microbe_to_host {}`; 12 figure/CSV artifacts still written | `runs/r2red/s3_host` |
| 9 | `search --model-dir pool_mixed --target ac --top-k 10` | 0 | 50.4 s | 3 of 6 `infeasible`; `status ok`; `warnings []` | `runs/r2red/x_mixed_pool` |
| 10 | `search --model-dir pool_mixed --target ac --top-k 3` | 0 | 49.9 s | 3 clean rows; failures invisible | `runs/r2red/x_mixed_topk3` |
| 11 | `search --model-dir pool3 --target ac --top-k 10` | 0 | 36.7 s | rank 3 `iAF987+iYO844 infeasible` | `runs/r2red/x_real_topk10` |
| 12 | `search --model-dir pool3 --target ac --top-k 2` | 0 | 37.0 s | same run, failure row gone, `status ok`, `warnings []` | `runs/r2red/x_real_topk2` |
| 13 | `solve-fixture --solver gurobi` | 0 | 1.7 s | `run_hash 29844e29…`, full software/inputs manifest | `runs/r2red/x_solvefixture` |
| 14 | probe: community vs solo medium | 0 | ~35 s | +4 / +13 nutrients; nh4·pi·so4 5→1000 | `REVIEW/scratch_r2red/medium_probe.py` |
| 15 | probe: medium-only growth inflation | 0 | ~40 s | +33.3 % / **+377.4 %** | `REVIEW/scratch_r2red/quantify_medium_effect.py` |
| 16 | probe: joint-LP alternate optima | 0 | ~60 s | all target ranges width ≈ 0 → **hypothesis refuted** | `REVIEW/scratch_r2red/degeneracy_probe.py` |
| 17 | error paths: malformed/absent medium, missing carbon formula | 2 | <5 s each | clean messages, no traceback (one mislabelled, F13) | — |

---

## 4. Figure assessment

Generated and inspected as files: 6 hand-built SVGs (`search_plot`, `search_scatter`,
`interaction_circle/heatmap/bubble`), 4 matplotlib SVGs (`strain_growth_plot`,
`abundance_impact_plot`, `gene_ko_plot`, `member_contribution`), and their TIFF siblings.
Text of matplotlib SVGs reconstructed from glyph references
(`REVIEW/scratch_r2red/svgtext.py`); TIFF headers via PIL
(`REVIEW/scratch_r2red/tiff_probe.py`).

| Criterion | Observed | Call |
|---|---|---|
| **Vector output** | All figures ship `.svg` alongside `.tiff`. Real vector, valid XML, no rasterised text. | **Pass** |
| **Raster resolution** | `dpi=(300.0, 300.0)` on every TIFF checked. | **Pass** |
| **Raster mode / compression** | `mode=RGBA`, `compression=raw` on all: `search_plot.tiff` 2160×1020 = **8.81 MB**, `search_scatter.tiff` 2040×1440 = **11.75 MB**, `strain_growth_plot.tiff` **8.81 MB**. Nature-family submission systems reject alpha channels and require LZW/ZIP. | **Fail** — must be RGB (or CMYK) + LZW |
| **Axis labels with units** | `strain_growth_plot`: x = `Growth rate` (should be h⁻¹). `abundance_impact_plot`: `Growth`, `Exchange flux`, `Target share`, `iHN637 abundance` — none carry units. `gene_ko_plot`: `ac secretion flux delta vs baseline (bar) — color = objective` — no units. `search_plot`: `Target exchange flux (EX_ac_m)` — exchange id but no `mmol gDW⁻¹ h⁻¹`. `interaction_heatmap` colourbar: `Flux`. | **Fail** — 0 of 8 axes carry units |
| **Numeric axis on `search_plot`** | Four gridlines drawn at 0.25/0.5/0.75/1.0 of `max_flux` with **no tick labels at all**; only per-bar value text. When every flux is 0, `max_flux` falls back to `1.0` and the chart is silently rescaled. | **Fail** |
| **Multi-panel + panel letters** | `abundance_impact_plot.svg` is a genuine 3-panel figure but has **no `a`/`b`/`c` panel letters**. All other outputs are single-panel; no command produces a composed multi-panel figure. | **Fail** |
| **Colourblind-safe palette** | Observed fills: `#2ca25f`, `#e6550d`, `#3182bd`, `#2b8cbe`, `#31a354`, `#756bb1`, `#d95f0e`, `#636363`, `#969696`, `#cfcfcf`. ColorBrewer-derived, **not Okabe-Ito**. Worse, `search_plot.svg` encodes **flux sign by colour alone** (green/orange) because bar length is `abs(flux)` — sign is unreadable for red-green CVD (F8). `gene_ko_plot` uses the same green/orange pair but also encodes the same information in bar direction, so it degrades gracefully. | **Fail** on `search_plot`; borderline elsewhere |
| **Legends** | `strain_growth_plot` (`Single model` / `Community`) and `gene_ko_plot` (`improves objective` / `worsens objective` / `no change` / `failed`) are informative. `search_plot` has no legend even though colour is semantic. `interaction_heatmap` colourbar is unlabelled beyond `Flux`. | **Mixed** |
| **Typography** | `font.family: "Arial"` hardcoded in `_load_matplotlib_pyplot` and in the hand-built SVG strings. Arial is absent on most Linux CI images → silent fallback with a matplotlib warning; not reproducible across machines. Sizes (22/14/13/11/10 pt) are internally consistent. | **Marginal** |
| **Data-ink ratio** | Good: `_polish_matplotlib_axes` removes top/right spines, light `#d9dee3` grid, `set_axisbelow`. Hand-built SVGs are similarly clean. | **Pass** |
| **Figure ↔ data fidelity** | Three confirmed violations: (a) uptake runs labelled as production with |flux| bars (F8); (b) full host-interaction figure set rendered from a failed, all-zero host solve with no annotation (F9); (c) `gene_ko_plot` orders by delta while the CSV/JSON/stdout order by absolute score, so the figure's first bar and rank 1 disagree (F7). Additionally the all-zero `s1_single_but` chart renders three zero-width bars with **no on-figure note** that the ranking is arbitrary, even though the CLI does warn on stdout. | **Fail** |
| **Provenance on figures** | `gene_ko_plot` carries an excellent subtitle: `baseline ac flux 12.1 · evaluated 6/637 genes · selection id · goal: max_secretion`. `search_plot` carries `exhaustive · evaluated 3/3 candidates`. Nothing else records medium, solver, or growth fraction. | **Partial** |

**Publication-readiness call: NOT READY.** The vector/300-dpi foundation is sound and
`gene_ko_plot.svg` is close to submittable. But no axis in the tool carries units, no figure has
panel letters, every TIFF is RGBA + uncompressed (~9–12 MB each), the palette is not
colourblind-safe where colour is the sole channel, and — the disqualifying issue — three figure
families can render a confident-looking result from data that is directional-inverted, infeasible,
or degenerate, with no annotation. Fixing units + TIFF mode/compression is mechanical; fixing
figure↔data fidelity (F8/F9) is required before any of these can go into a manuscript.

---

## 5. Prioritized proposals

### P0

1. **`cmig/cli/main.py::_write_search_outputs` (line 3163) and
   `::_write_gene_ko_search_outputs` (line 1835)** — replace the literal `"status": "ok"` with
   `_worst_status(...)` derived from the ranked rows (as `_write_multi_target_outputs` already
   does): `failed` when no rank is `optimal`, `degraded` when any rank is not `optimal`.
   Same treatment for `::_write_abundance_impact_outputs` (line 2058), whose
   `any(... == "optimal")` derivation has no `degraded` tier.
   *(F2, F5, F7)*
2. **`cmig/core/search_product.py::search_model_pool`** — port the multi-target unevaluable
   warning: after ranking and **before** `top_k` truncation, emit
   `"N of M candidates were not evaluable (status=…) and are not scored: …"`, and carry the count
   into `search_summary.json` as `n_candidates_ranked` (the multi-target summary already has this
   field). Also make `_ranking_degeneracy_warnings` emit an explicit warning in the
   `not evaluable` case instead of returning `[]`. *(F1, F2)*
3. **`cmig/cli/main.py::_cmd_search`** — do not print the `best:` line when
   `result.ranks[0].status != "optimal"`, and print warnings **before** the `best:` line.
   *(F2)*
4. **`cmig/cli/main.py::_cmd_strain_growth`** — when `medium_spec is None`, do **not** set
   `single_medium_applied = True`. Either (a) read `community.medium` after
   `engine.build_community(...)` and apply it to each single-model leg (the correct control), or
   (b) set `single_medium_equals_community_medium: false` and emit the existing
   "not attributable to interaction" warning. Option (a) is the scientifically right fix and is a
   ~5-line change. *(F3)*

### P1

5. **`cmig/cli/main.py::_cmd_abundance_impact`** (lines ~1718-1728) — weight member exchange
   fluxes by abundance before computing the share
   (`contribution = flux * result.abundances[member]`), and split the numerator/denominator by
   sign so consumers are not credited as contributors. Rename the field or add
   `target_influence_share_basis: "abundance_weighted_signed"`. *(F4)*
6. **`cmig/cli/main.py::_write_abundance_impact_outputs`** — add a `warnings` key and propagate
   `SolveResult.warnings` (including `PFBA_FALLBACK_WARNING`); add a per-row
   `flux_normalization_method` column (the value already exists on `SolveResult`) and warn when a
   single sweep mixes `pfba` and `fba`. Apply `_worst_status` at the top level. *(F5)*
7. **`cmig/cli/main.py::_write_strain_growth_outputs`** — derive top-level `status` with
   `_worst_status`, mapping `optimal → ok` and downgrading to `degraded` when
   `warnings`/`community_diagnostic` is non-empty. Removes the `optimal` value from the
   `inspect-run` status vocabulary at the same time. *(F5, F11)*
8. **`cmig/cli/main.py::_cmd_gene_ko_search` / `_write_gene_ko_outputs`** — rank by
   `score_delta` (or expose `--rank-by {delta,score}` defaulting to `delta`), and reuse
   `search_product._ranking_degeneracy_warnings` so an all-zero-delta or tied top is warned. Make
   the CSV order match `gene_ko_plot.svg`. *(F7)*
9. **New shared helper, e.g. `cmig/core/manifest.py::product_run_manifest(...)`, called from
   `_write_search_outputs`, `_write_multi_target_outputs`, `_write_strain_growth_outputs`,
   `_write_abundance_impact_outputs`, `_write_gene_ko_outputs`,
   `_write_host_microbe_outputs`** — write a `manifest.json` with `run_hash`, software versions,
   model file checksums, `medium_checksum`, and every resolved CLI parameter (`growth_fraction`,
   `solver`, `direction`, `strategy`, `seed`, `n_samples`, `top_k`, `tradeoff_f`). `solve-fixture`
   already produces exactly this shape — reuse it. *(F6)*
10. **`cmig/cli/main.py::_write_search_svg`** — derive title and caption from `result.direction`
    (`"Target uptake search"` / `"larger is better for max uptake"`), draw signed bars from a zero
    baseline instead of `abs()`, add numeric tick labels to the four gridlines, clamp the value
    label inside the canvas, and stamp the direction + units on the axis caption. *(F8)*

### P2

11. **`cmig/core/search_product.py::rank_multi_target` / `_multi_target_warnings`** — set
    `pareto = None` (serialised as `null`) when `len(mets) != 2` and add a warning
    `"Pareto frontier is only computed for exactly 2 targets; the pareto column is not evaluated"`.
    *(F10)*
12. **`cmig/cli/main.py::_write_multi_target_outputs`** — emit at least
    `search_plot.svg`/`.tiff` for the multi-target path so the headline S1 workflow has a figure.
    *(F10)*
13. **`cmig/core/interaction_figures.py`** — when the host solve is non-optimal or every
    `used_by_host` is false, stamp a visible banner on each figure
    (`"host solve infeasible — no microbe→host transfer"`) or refuse to write and record the
    refusal in `figure_manifest.json`. Encode `used_by_host` visually (e.g. hatched/greyed edges).
    *(F9)*
14. **`cmig/cli/main.py`** — return a non-zero exit code when a run's derived status is `failed`
    (or add `--fail-on-degraded`), so shell pipelines can gate on `$?`. *(F9)*
15. **`cmig/core/host.py::_coupling_scale`** — validate `basis_source` shape for
    `basis_kind in {measured, literature}` (reject obvious placeholders: `TBD`, `TODO`, `N/A`,
    `?`, bare numbers) or attach a warning. *(F12)*
16. **`cmig/cli/main.py::_resolve_run_status`** — remove the terminal `if summary: return "ok"`
    fallback in favour of `"unknown"`, and normalise all writers onto the
    `ok / degraded / failed` vocabulary. *(F11)*
17. **`cmig/cli/main.py::_cmd_search`** — split the `except OSError` handler so read failures are
    not reported as "failed to write search outputs". *(F13)*
18. **`cmig/cli/main.py::_load_matplotlib_pyplot` and the hand-built SVG writers** — add units to
    every axis label (`Growth rate (h⁻¹)`, `Exchange flux (mmol gDW⁻¹ h⁻¹)`), switch the palette
    to Okabe-Ito, save TIFFs with `pil_kwargs={"compression": "tiff_lzw"}` and RGB mode, add panel
    letters to `abundance_impact_plot`, and use a font stack
    (`["Arial", "Helvetica", "DejaVu Sans"]`) instead of bare `"Arial"`. *(figure section)*
19. **`cmig/core/model_pool.py::diagnose_model_pool`** — investigate why iAF987 reports
    `n_biomass = 283`; the count is the readiness signal users check. *(F13)*

---

## 6. What I could not test, and what I suspected but could not confirm

**Refuted by my own probe (honest negative):** I hypothesised that the multi-target joint LP
reports one arbitrary vertex among many alternate optima — i.e. that the winning consortium's
`but/ppa/lac/succ = 0` values are non-identifiable. `REVIEW/scratch_r2red/degeneracy_probe.py`
pins the joint objective at its optimum (24.2235) and re-optimises each target individually. All
six ranges came back with width ≈ 0 (`ac [12.1117, 12.1118]`, everything else `[0, 0]`). **The
reported per-target fluxes are point-identified for this consortium.** The reduction of "SCFA
production" to "acetate production" is a genuine property of a linear carbon-weighted
scalarisation, not a reporting artifact. I found no missing identifiability caveat here.

**Suspected, not confirmed:**

* A taxonomy member literally named `medium` is accepted by micom
  (`REVIEW/scratch_r2red/micom_id_probe.py`), and `engine.py::_solve_result_from_solution` filters
  `str(i) != "medium"` from `member_ids` — so such a member would be silently dropped and the
  environmental profile read from the wrong row. I did **not** run a full search with that id
  because the input is contrived; flagging as a robustness risk only.
* `_resolve_run_status`'s terminal `return "ok", "derived"` branch (F11): I could not find a
  shipped command whose summary lacks `status`, `top_ranked`, `reports` **and** a manifest, so I
  report it as a code-path risk rather than a confirmed run.
* The root cause of `iAF987+iYO844` being `infeasible` for `EX_ac_m` max-secretion while solving
  fine for `EX_but_m` and for `max_uptake` on the same metabolite. It reproduces deterministically
  across four independent runs, but I did not determine whether it is a genuine LP infeasibility
  or a Gurobi numerical artifact. Either way F1/F2 stand — the reporting of the failure is the
  defect I am claiming.

**Not tested at all (out of time / no suitable input):**

* `cmig dfba`, `cmig spatial-preview`, `cmig sweep`, `cmig sandbox-fixture`, `cmig model-review`,
  `cmig host-map`, `cmig host-search-bigg`, `cmig solve` (user taxonomy).
* `--strategy random` and `--strategy ga` in `search` (I read the code — both emit
  "global optimum is not guaranteed" warnings — but ran neither), and `--robustness-fva`.
* The GUI (PySide6 offscreen) and the R `render-figure` export path.
* Host coupling at Human-GEM/Recon3D scale. All S3 evidence uses the bundled 12-reaction
  `cmig.synthetic_host` toy, which its own docstring says is qualitative-only. **The F9 finding
  (figures written from a failed host solve) is structural and does not depend on host scale, but
  I cannot speak to quantitative host behaviour.**
* Any assessment of whether the *biology* of the winning consortia is right — I checked only
  whether CMIG's reported numbers are internally consistent, correctly based, and honestly
  qualified.
