# Reading and reproducing CMIG runs

Every CMIG analysis writes a self-describing run directory under `--out`. This
file explains how to read one back, what `inspect-run` reports, and how to
reproduce or cite a result.

## Always inspect after running

```bash
uv run cmig inspect-run --run-dir runs/<name> --format json
```

`inspect-run` detects the run's summary file and reports a stable payload
(`schema_version: "1.2"`):

- `kind` — the workflow that produced the run (see the table below).
- `status` — the run-level tier: `ok`, `degraded`, `failed`, or `unknown`.
- `status_source` — **where that verdict came from.** This is the field to read
  when you need to know how much the status is worth (see below).
- `run_hash` — **certifies the INPUTS**.
- `result_digest` / `artifact_integrity` — **certifies the ANSWER** (see below).
- `result_digest_absent_reason` — present when there is no digest, naming *why*.
- `summary_file` — which summary JSON was detected.
- `artifacts` — the files present in the run directory.
- `manifest` — compacted manifest fields when a `manifest.json` exists, including
  the three non-hashed **policy markers** (`medium_policy`,
  `boundary_isolation_policy`, `host_isolation_policy` — see below),
  `diagnostic`, `warnings` and `summary`.

Use `--format text` for a quick human read. Report `status`, `status_source`, both
fingerprints, and the headline numbers back to the user — a bare "done" hides
failures and makes the run unciteable.

### `status_source` — how the verdict was reached

The status vocabulary is only meaningful together with its source. Values:

| `status_source` | Meaning |
| --------------- | ------- |
| `manifest` | a workflow manifest stated the run-level tier directly |
| `summary` | the summary JSON carried an explicit `status` field |
| `derived` | inferred from a lower-level signal (e.g. a manifest `diagnostic`) |
| `acceptance.interpretable` | the run **stamped itself uninterpretable**; see the veto below |
| `host_map_counts` | derived from the interface-map match counts |
| `solve.status` | derived from the embedded solve status |
| `namespace.blocked` | the run was blocked by an unresolved namespace decision |
| `inference.status` | derived from an inference sub-result |
| `no_status_signal` | a recognised summary is present but records **no** run-level outcome ⇒ `status: unknown` |
| `unknown` | the directory held nothing recognisable ⇒ `status: unknown` |

**`unknown` is a real answer, not a failure of the tool.** Some runs legitimately
have no pass/fail dimension — `stats-demo` is the clean example — and CMIG now says
`unknown` rather than inventing `ok`. Treat `unknown` as "this artifact does not
tell you how the run went; go look at the run's own fields", and never as a pass.
The rule the resolver follows is *if it does not know, it does not say ok*.

**`acceptance.interpretable` is a veto, not a tie-breaker.** A summary that stamps
itself uninterpretable overrides a rosier derived tier, and it may only make the
verdict **worse**, never better. When it wins it also owns `status_source`, so you
can see which signal condemned the run. The case that motivated it:
`publication-benchmark` derives its dFBA sub-run manifest status from
`dfba_completed` / `dfba_balance_passed` only, so `manifest.json` can read
`status: ok` while `acceptance.interpretable` in `dfba_sensitivity.json` beside it
is `false`. **So `manifest.status` and the reported `status` can legitimately
disagree — the reported one wins, and `status_source` tells you why.**

### `inspect-run` describes a run; it does not re-judge it

- **A failed *scientific* run still exits 0 here**, because the exit contract
  belongs to the command that produced it. **Always check `$?` of the analysis
  command** — that is the verdict; `inspect-run` is the description.
  `inspect-run`'s own non-zero exits are: **3** on `artifact_integrity: mismatch`,
  and **2** on an unusable directory — a missing `--run-dir`, or a `manifest.json`
  that exists but is corrupt or is not a JSON object. So `0` from `inspect-run` means
  "this directory is readable and self-consistent", not "the science succeeded".
- **The status vocabulary is not closed.** `ok`/`degraded`/`failed`/`unknown` are
  the intended tiers, but raw solver words still reach `status`: the legacy alias
  table maps only `optimal` and `completed` to `ok`, so **`infeasible` and
  `stalled` pass straight through**. A gate written against the four tiers will not
  match them. Compare defensively, and treat any unrecognised value as not-ok.
  (Known open item, tracked by the maintainers.)

### The two fingerprints

| Field | Certifies | Notes |
| ----- | --------- | ----- |
| `run_hash` | the **inputs** | identical inputs ⇒ identical hash. It does **not** certify the answer: the round-5 medium fix deliberately changed published numbers under identical hashes. |
| `result_digest` | the **answer** | fingerprints the artifact bytes actually written, **including figures**. `inspect-run` recomputes it and reports `artifact_integrity: verified \| mismatch \| not_recorded`. A mismatch flips `status` to `failed` and exits 3. |

`result_digest` is written by the **workflow manifest**, which covers 13 kinds:
`model_pool_search`, `multi_target_model_pool_search`, `strain_growth`,
`abundance_impact`, `gene_ko_search`, `host_microbe_bigg`, `host_search_bigg`,
`host_ko_impact`, `sweep`, `dfba`, `model_quality`, `host_map`,
`publication_benchmark`.

**`cmig solve` is not one of them.** It writes a `manifest_scope: solve` manifest
and never emits a digest, so `result_digest: not recorded` on a brand-new solve is
expected and is **not** tampering.

When there is no digest, `result_digest_absent_reason` names which of four cases
applies, so you never have to guess:

| `result_digest_absent_reason` | What it means |
| ----------------------------- | ------------- |
| `solve_manifest_never_records_one` | `cmig solve` writes a `manifest_scope=solve` manifest and never emits a digest; only the workflow-manifest kinds do. **Expected — not a problem.** |
| `no_manifest` | the run directory has no `manifest.json`, so nothing here ever recorded one |
| `workflow_manifest_predates_result_digests` | a genuine workflow manifest written before digests existed — the only case where "predates" is true |
| `manifest_declares_no_scope` | the manifest declares no `manifest_scope`, so it predates digests |

This field exists because the message used to assert `manifest predates result
digests` for **every** absent digest, including brand-new `cmig solve` runs — a
false temporal cause that invited the reader to think their toolchain was stale.
Read the reason rather than inferring one.

**Do not compare two runs' digests unless `cross_run_comparable` is true.** The
digest payload carries that flag, and it is true only for kinds whose artifacts are
byte-deterministic for identical inputs — currently **`host_map` only**. For every
other kind the digest certifies *those bytes* (which is what `inspect-run` checks),
but two runs with identical inputs can legitimately differ because a figure raster,
a parquet write id or a timestamp is embedded. Comparing digests across runs of a
non-listed kind manufactures false alarms. `result_digest.artifacts` also lists a
per-artifact breakdown and `missing_artifacts` — a run that failed to write half
its declared outputs does not digest the same as one that wrote them all.

### Reading `edges.parquet` — the single most misread artifact

`edges.parquet.weight` is an **unsigned, PER-TAXON** flux in
`mmol gDW_taxon⁻¹ h⁻¹`. It is **not** abundance-weighted and **not** comparable
to `profile.parquet.net_flux`, which is community-basis
(`mmol gDW_community⁻¹ h⁻¹`).

Because per-taxon flux scales roughly as 1/abundance, **comparing raw edge
weights inverts the ranking.** Measured on a 2-member solve (iHN637 abundance
0.1, iML1515 abundance 0.9), acetate secretion:

| member  | abundance | `edges.weight` | × abundance |
| ------- | --------- | -------------- | ----------- |
| iHN637  | 0.1       | 3.876102       | 0.387610    |
| iML1515 | 0.9       | 0.459437       | **0.413494**|

Edge weights say iHN637 dominates by 8.4×; community contribution says iML1515
does. To compare members correctly:

1. keep only `edge_type in {secretion, uptake}` — **exclude `cross_feeding`**,
   which is a mass-conserving *proportional allocation*, not a measured pairwise
   transfer (`identifiable: false`, `allocation_method:
   proportional_shared_pool`);
2. sign each row by direction (`+` secretion, `−` uptake);
3. multiply by the abundance of the member endpoint.

The sum then matches that metabolite's `profile.parquet.net_flux` — 0.801104 for
acetate in the run above. Summing unsigned weights, or including `cross_feeding`,
does not.

**Two honest limits on that identity**, both measured on the same run:

- It is **not exact for every metabolite.** 23 of the 25 overlapping metabolites
  agreed to <1e-9; two did not — `mobd` (diff 6.2e-08) and `btn` (1.8e-08). Both sit
  near the engine's 1e-6 noise floor, where the reconstruction is not reliable. Do
  not use it to audit trace metabolites.
- **Not every edge metabolite has a profile row.** The run had 44 metabolites in
  `edges.parquet` but only 25 rows in `profile.parquet`, so **19 had nothing to
  reconcile against.** An absent profile row is not a zero.

Use the identity to sanity-check the metabolites you actually care about, at fluxes
well above 1e-6 — not as a blanket invariant.

The run states all of this in `manifest.json → edge_attribution`, which
`uv run cmig inspect-run --format text` prints as the `edges.weight basis:` line. Read
it before quoting any edge magnitude, and never build a "top producer" claim from
raw edge weights or from edge width in the interaction figures (the circle plot's
own caption notes edge width is per-taxon flux, not abundance-weighted).

## Summary file → workflow kind

`inspect-run` recognises these summaries (first match wins):

| Summary file                       | kind |
| ---------------------------------- | ---- |
| `manifest.json`                    | community_solve |
| `search_summary.json`              | model_pool_search |
| `host_microbe_bigg_summary.json`   | host_microbe_bigg |
| `host_search_summary.json`         | host_search_bigg |
| `host_ko_impact_summary.json`      | host_ko_impact |
| `strain_growth_summary.json`       | strain_growth |
| `abundance_impact_summary.json`    | abundance_impact |
| `gene_ko_summary.json`             | gene_ko_search |
| `dfba_summary.json`                | dfba |
| `dfba_sensitivity.json`            | dfba_sensitivity |
| `spatial_summary.json`             | spatial_preview |
| `model_review.json`                | model_review |
| `model_quality.json`               | model_quality |
| `sweep_summary.json`               | sweep |
| `stats_summary.json`               | stats_demo |
| `stats_sweep_summary.json`         | stats_sweep |
| `sandbox_summary.json`             | sandbox_fixture |

A run that carries a **workflow manifest** (`manifest_scope: "workflow"`) names
its own kind, and that name wins over this table — so a workflow run is never
mislabelled `community_solve` just because it has a `manifest.json`.

If none is present, `kind` is `unknown` — that usually means the run failed
before writing a summary, or `--out` points at the wrong directory. A `manifest.json`
that exists but is corrupt is an **error**, not `unknown`.

## What to look at, by workflow

- **search (single-target)** — `search_rankings.csv` for the ranked
  combinations, `search_member_matrix.csv` for which models are in each
  combination, `pool_diagnostics.csv` for per-model feasibility,
  `search_plot.svg` / `search_scatter.svg` for the ranking and
  growth-vs-production views.
- **search (multi-target)** writes a **different artifact set**:
  `pool_taxonomy.csv`, `search_rankings.csv`, `search_summary.json`,
  `search_plot.svg`, `search_plot.tiff`, `pool_diagnostics.csv`, and
  `search_unevaluated.csv` *when any candidate could not be evaluated*. There is
  **no `search_member_matrix.csv` and no `search_scatter.svg`** in this mode — do
  not wait for them.
  - **Read `search_unevaluated.csv` before the ranking.** Candidates that could
    not be evaluated get `rank` 0 / blank and are excluded from `top_ranked`, so a
    combination absent from the ranking is not "low scoring". A common
    value is `flux_basis: per_target_capability_not_simultaneous` — **the
    `flux_basis` column, not `diagnostic`** — meaning the pair can make each target
    individually but not all at once. `diagnostic` holds the solver-level message
    beside it (e.g. `target LP returned no solution object
    (solver_status=infeasible)`), and `missing_targets` names which target failed.
    In a measured run over the bundled pool, the *most metabolically diverse* pair
    (`iAF987+iYO844`, which alone shows lac__L 2.35, ppa 1.21, succ 2.29) was the one
    excluded — so reading only the ranking hides the most interesting candidate.
  - **`status: degraded` is the *normal* outcome for a search with any unevaluable
    candidate**, not a warning sign about the ranked rows. The measured
    `--target-preset scfa` run reported `status: degraded (source: manifest)` purely
    because 1 of 10 candidates could not be evaluated; the 9 ranked rows were all
    `optimal`. Read the unevaluated partition to see why it degraded before treating
    it as a problem with the result.
  - Check `flux_basis` and `missing_targets` per row. A target with no exchange in
    that combination contributes flux 0 rather than disqualifying it, which
    depresses the score for a reason that is not biology.
- **strain-growth** — `strain_growth.csv`: compare `single_growth` vs
  `community_member_growth` per strain. **This is only an interaction effect if
  `--single-medium community` was used** (the default); under `model_default` the
  delta also contains the medium change. A strain that grows alone but not in
  community is doing (or receiving) cross-feeding. A **blank** `single_growth` is
  a failed alone-solve, not a zero — it is excluded from the figure with the count
  stated, and must not be read as obligate syntrophy.
- **abundance-impact** — `abundance_impact.csv` and
  `member_growth_by_abundance.csv`: track `target_influence_share` (already
  abundance-weighted) and `community_target_exchange` across `--fractions`. Read
  as sensitivity. With `--fva`, compare each point's FVA interval before calling a
  change a dose response — overlapping intervals mean alternate optima, not a
  trend. Rows with a non-`ok` `status` carry NaN and are excluded from the figure.
- **gene-ko-search** — `gene_ko_summary.json` carries `baseline`, `ko_level`,
  `gene_selection`, `seed`, `n_genes_total`, and any `warnings`; check these
  before trusting the ranking in `gene_ko_rankings.csv`. A `warnings` entry
  about truncation means the screen was not exhaustive.
- **host-microbe-bigg** — `interaction_edges.csv` / `interaction_matrix.csv` are
  the cross-feeding edges; `member_contribution.csv` attributes transfer to
  members (use this, not raw edge magnitudes, for "who contributes most"); the
  SVGs (circle / heatmap / bubble / member contribution) are the publication
  figures. Confirm the summary's biomass-basis fields, that
  `biomass_basis_kind` is not `validation`, and whether the interface map was
  reviewed or waived with `--accept-unreviewed-map`.
- **host-search-bigg** — `host_search_rankings.csv`; confirm which `--metric`
  was used and, for `weighted`, that reference scales were set. Check each row's
  `evaluation_status` and the summary's `n_candidates_failed`: a non-optimal host
  LP is published as NaN, not a ranked 0.0. `host_search_unevaluated.csv` holds
  the excluded candidates.
- **host-ko-impact** — `host_ko_impact_summary.json`: the host-objective and
  target-delivery delta between the knockout and wild-type arms, with every other
  input held identical. The same biomass-basis and interface-map checks apply.
- **dfba** — `dfba_timecourse.csv` / `.parquet` and the figures. **First check
  `n_untracked_uptake` and `warnings`** in `dfba_summary.json`: a non-zero count
  means growth was fed by never-depleting substrates and the run is not a
  substrate/Km experiment, regardless of `status: completed`. Then pair with a
  `dfba-sensitivity --close-untracked-uptake` run before quoting an endpoint.
- **dfba-sensitivity** — `dfba_sensitivity.json` / `.csv`. Read
  `acceptance.interpretable` and `acceptance.not_interpretable_because`; the
  command exits 3 when the grid is not interpretable. Do **not** rely on
  `inspect-run`'s `status` for this kind (see above).
- **solve / sweep** — `nodes.parquet`, `edges.parquet`, `profile.parquet`, and
  `manifest.json`; sweeps add `sweep.parquet` and `sweep_profiles.parquet`. See
  *Reading `edges.parquet`* above before comparing edges. For a sweep, check each
  condition's own `status` — a sweep whose every condition failed exits 3.

## Reproducing or citing a run

1. Keep the `--out` directory intact — it holds the manifest, summary, tidy
   tables, and figures. `result_digest` covers the **bytes**, so editing a figure
   in place invalidates the run.
2. Record the `run_hash`, the `result_digest`, and the solver used (see
   `references/scientific-validity.md` §4).
3. **Check the three policy markers.** Each records a semantics change that moved
   published answers **without moving `run_hash`**, so the hash cannot reveal it
   and the marker is the only mechanical signal. All three are non-hashed and all
   three reach `inspect-run`; a missing one means the run predates that fix.

   | marker | trustworthy value | if absent / older |
   | ------ | ----------------- | ----------------- |
   | `medium_policy` | `exchange_reactions_by_metabolite_v2` | `open_uptakes_exact_key_v1` or absent ⇒ the `--medium` file never took effect; **re-do the run** |
   | `boundary_isolation_policy` | `boundary_reactions_v1` | absent ⇒ closure enumerated `model.exchanges`/`model.medium`, so sinks and demands stayed open. Only matters on a model that *has* them: the bundled microbial GEMs have none, the human GEMs have 95 |
   | `host_isolation_policy` | `all_boundary_uptake_v2` | `model_exchanges_only_v1` or absent ⇒ a host coupling run's `host_objective` may have been fed by the host's own sinks rather than by the community. Measured on Recon3D: `368.010247546` before, `0.0` after, **same `run_hash`** |

   On a host-coupling run also read `host.boundary_isolation` and
   `summary.host_boundary_isolated` in the summary JSON: an objective computed
   with the background left open (`--keep-host-uptake`) is **not** attributable to
   the microbes, and the `warnings` list says so with the count.
4. For a publication run, prefer `cmig publication-benchmark`, which produces a
   single checksummed manifest with a `publication_ready` flag combining the
   quality audit, community solve, search, optional dFBA sensitivity, and
   optional host coupling. Its bundle hash **includes its children's hashes** and
   is order-insensitive, so a bundle identifies the exact set of sub-runs.
5. When the environment changes (new MICOM, new solver), run **both**
   `cmig golden verify` (numeric regression gate) and
   `cmig golden verify-envelope` (workflow-manifest serialization drift gate)
   before trusting or re-citing prior numbers.
6. `match_behavior`, where present, is a best-effort **input-side** signal.
   `result_digest` is the guarantee — prefer it.
