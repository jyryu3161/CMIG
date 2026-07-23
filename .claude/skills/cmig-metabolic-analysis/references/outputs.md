# Reading and reproducing CMIG runs

Every CMIG analysis writes a self-describing run directory under `--out`. This
file explains how to read one back, what `inspect-run` reports, and how to
reproduce or cite a result.

## Always inspect after running

```bash
uv run cmig inspect-run --run-dir runs/<name> --format json
```

`inspect-run` detects the run's summary file and reports a stable payload:

- `kind` — the workflow that produced the run (see the table below).
- `status` — run status (e.g. `ok`, `failed`, `unknown`).
- `run_hash` — reproducibility hash when the summary/manifest carries one.
- `summary_file` — which summary JSON was detected.
- `artifacts` — the files present in the run directory.
- `manifest` — compacted manifest fields when a `manifest.json` exists.

Use `--format text` for a quick human read. Report `status`, `run_hash`, and
the headline numbers back to the user — a bare "done" hides failures and makes
the run unciteable.

## Summary file → workflow kind

`inspect-run` recognises these summaries (first match wins):

| Summary file                       | kind |
| ---------------------------------- | ---- |
| `manifest.json`                    | community_solve |
| `search_summary.json`              | model_pool_search |
| `host_microbe_bigg_summary.json`   | host_microbe_bigg |
| `host_search_summary.json`         | host_search_bigg |
| `strain_growth_summary.json`       | strain_growth |
| `abundance_impact_summary.json`    | abundance_impact |
| `gene_ko_summary.json`             | gene_ko_search |
| `dfba_summary.json`                | dfba |
| `spatial_summary.json`             | spatial_preview |
| `model_review.json`                | model_review |
| `sweep_summary.json`               | sweep |
| `stats_summary.json`               | stats_demo |
| `stats_sweep_summary.json`         | stats_sweep |
| `sandbox_summary.json`             | sandbox_fixture |

If none is present, `kind` is `unknown` — that usually means the run failed
before writing a summary, or `--out` points at the wrong directory.

## What to look at, by workflow

- **search** — `search_rankings.csv` for the ranked combinations,
  `search_member_matrix.csv` for which models are in each combination,
  `pool_diagnostics.csv` for per-model feasibility, `search_plot.svg` /
  `search_scatter.svg` for the ranking and growth-vs-production views.
- **strain-growth** — `strain_growth.csv`: compare `single_growth` vs
  `community_member_growth` per strain; a strain that grows alone but not in
  community is doing (or receiving) cross-feeding.
- **abundance-impact** — `abundance_impact.csv` and
  `member_growth_by_abundance.csv`: track `target_influence_share` and
  `community_target_exchange` across `--fractions`. Read as sensitivity.
- **gene-ko-search** — `gene_ko_summary.json` carries `baseline`, `ko_level`,
  `gene_selection`, `seed`, `n_genes_total`, and any `warnings`; check these
  before trusting the ranking in `gene_ko_rankings.csv`. A `warnings` entry
  about truncation means the screen was not exhaustive.
- **host-microbe-bigg** — `interaction_edges.csv` / `interaction_matrix.csv` are
  the cross-feeding edges; `member_contribution.csv` attributes transfer to
  members; the SVGs (circle / heatmap / bubble / member contribution) are the
  publication figures. Confirm the summary's biomass-basis fields and whether an
  interface map was reviewed.
- **host-search-bigg** — `host_search_rankings.csv`; confirm which `--metric`
  was used and, for `weighted`, that reference scales were set.
- **dfba** — `dfba_timecourse.csv` / `.parquet` and the figures; pair with a
  `dfba-sensitivity` run before quoting an endpoint.
- **solve / sweep** — `nodes.parquet`, `edges.parquet`, `profile.parquet`, and
  `manifest.json`; sweeps add `sweep.parquet` and `sweep_profiles.parquet`.

## Reproducing or citing a run

1. Keep the `--out` directory intact — it holds the manifest, summary, tidy
   tables, and figures.
2. Record the `run_hash` and the solver used (see
   `references/scientific-validity.md` §4).
3. For a publication run, prefer `cmig publication-benchmark`, which produces a
   single checksummed manifest with a `publication_ready` flag combining the
   quality audit, community solve, search, optional dFBA sensitivity, and
   optional host coupling.
4. When the environment changes (new MICOM, new solver), run
   `cmig golden verify` to confirm results still match the golden fixture before
   trusting or re-citing prior numbers.
