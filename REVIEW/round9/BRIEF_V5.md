# Round-9 Track V5 — `feat/stats-5b5c-core`

Read `REVIEW/round9/COMMON_BRIEF.md` first. Spec §15 MVP-5b/5c: the embedding/
clustering layer (`cmig/core/stats_embed.py` — `pca_embed`, `kmeans_cluster`,
`umap_embed`) has been orphaned since round 1 (consumers are tests only), and
there is no `StatsConfig`, so stats runs carry ad-hoc flags and hard-coded
seeds. Library-level track: make the layer real, reproducible, and wire-ready.

## Goal

1. **`StatsConfig`** (frozen dataclass in `cmig/core/stats.py`): groups,
   methods, `fdr_method`, `seed`, `dimred` (none/pca/umap with parameters),
   `clustering` (none/kmeans with k), each field validated with honest errors.
   It must serialize deterministically (`as_provenance()`-style dict) so the
   coordinator/V1-successor can hash it into the stats workflow manifest later
   — propose the manifest component in your report; do NOT touch
   workflow-manifest code.
2. **Seeded, gated embedding pipeline.** A single entry point that takes the
   sweep-derived feature table `cmig stats-sweep` already builds, applies the
   configured dimred/clustering with the recorded seed (no hard-coded seeds
   left), and returns tidy embedding/cluster tables. Honesty gates in the
   spirit of the existing stats module: refuse (with a named reason) when
   observations < components, when replicates are pseudo-replicates the
   existing gate already flags, or when UMAP's neighbor count exceeds the data;
   never emit an embedding whose interpretability conditions failed.
3. **Volcano data preparation**: effect size vs adjusted p-value table from the
   existing per-group stats, ready for a matplotlib/R figure — data
   preparation only; figure writers belong to other owners (note the handoff).
4. **Determinism tests**: same seed → identical tables (UMAP included, using
   its random_state path); different seed → recorded difference. Extend
   `tests/test_stats.py` and add `tests/test_round9_stats_config.py`.

## Ownership

- `cmig/core/stats.py`, `cmig/core/stats_embed.py`
- tests: `tests/test_stats.py` (additive), new `tests/test_round9_stats_config.py`

## Constraints

- No CLI flags (`cmig/cli/main.py` is V1-owned) — write the exact proposed
  `stats-sweep` extensions in your report.
- No new dependencies; scipy/statsmodels/scikit-learn/umap-learn are already
  in the stats extra.
- `cmig golden verify-envelope` untouched (17 kinds; V1 may add an 18th —
  yours is not it this round).
