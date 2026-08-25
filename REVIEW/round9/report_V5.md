# Round-9 V5 report — stats 5b/5c core

## What changed and why

### Validated, deterministic statistics configuration

- Added frozen `StatsConfig` in `cmig/core/stats.py` with canonicalized `groups`
  and `methods`, validated `fdr_method`, a non-boolean uint32-compatible `seed`,
  and nested `DimredConfig` / `ClusteringConfig` values.
- `dimred` supports `none`, `pca`, and `umap`; active parameter provenance is
  explicit (`n_components`, and `n_neighbors` for UMAP). `clustering` supports
  `none` and `kmeans`, with `k` recorded when active.
- Mutable sequences/mappings supplied at construction are copied into immutable
  values. `StatsConfig.as_provenance()` returns a deterministic JSON-ready dict,
  preserving group/method order because group order can define effect direction.
- Known method identifiers are closed and validated: the robust/parametric
  presets plus the currently implemented summary, test, and effect-size methods.

### Seeded, fail-closed embedding and clustering

- `pca_embed`, `kmeans_cluster`, and `umap_embed` now accept `seed`; every
  algorithm passes it through its `random_state` path. UMAP also records it as
  `transform_seed` and runs with `n_jobs=1` for the deterministic path. There
  are no algorithm-level `random_state=0` literals left.
- Added `StatsFeatureTable`, `feature_table_from_rows`, and the single public
  `run_embedding_pipeline` entry point. It accepts a wide Arrow/pandas/list-of-
  mappings table or a normalized feature table, filters to configured groups,
  and emits deterministic tidy long rows:
  - `embedding_table`: observation, group, method, component, value, seed;
  - `cluster_table`: observation, group, kmeans label, k, input basis, seed;
  - `explained_variance_table`: PCA component ratios and seed;
  - `provenance`: canonical `StatsConfig` plus input observation count, feature
    column order, and the independent-replicate confirmation.
- Clustering is sequential: KMeans consumes PCA/UMAP coordinates when dimred is
  active, otherwise the validated feature matrix. Its `basis` column makes this
  explicit.
- Added `StatsEmbeddingGateError`, with stable `reason` and human detail. No
  embedding/cluster rows are returned if an active analysis fails a gate:
  `not_run_no_independent_replicates`,
  `not_run_observations_fewer_than_components`,
  `not_run_features_fewer_than_components`,
  `not_run_umap_requires_three_observations`,
  `not_run_umap_neighbors_exceed_observations`,
  `not_run_clusters_exceed_observations`, or
  `not_run_clusters_exceed_distinct_observations`.
- Matrix values must be numeric and finite; observation/feature IDs are nonempty
  and unique. This prevents an ambiguous tidy output.

### Volcano data preparation

- Added `prepare_volcano_data` (`volcano_data` alias) in `cmig/core/stats.py`.
  It accepts feature-keyed existing `TestResult` values or tidy comparison rows,
  validates finite effect sizes and valid p-values, applies BH/BY with the stated
  method, and returns feature-sorted rows containing raw p-value, adjusted
  p-value, `-log10(adjusted p-value)`, effect size/name, and FDR method.
- `fdr_correct` now rejects unsupported correction methods and non-finite/out-of-
  range p-values before calling statsmodels.

## Verification log

All commands used the required environment prefix
`UV_CACHE_DIR=/tmp/cmig-round9-V5-uv-cache uv run --no-sync`.

- `pytest -q tests/test_stats.py tests/test_round9_stats_config.py`
  - exit 0; 34 tests passed.
  - Covered config immutability/provenance and every field family, low-level seed
    propagation, PCA/KMeans tidy determinism, pipeline reason gates, volcano
    correction, exact same-seed UMAP rows, and different-seed UMAP coordinates
    plus recorded provenance.
  - One non-failing joblib sandbox warning reported that physical-core discovery
    failed and it used the logical-core count. It does not alter the explicit
    algorithm seeds or assertions.
- `ruff check .`
  - exit 0: `All checks passed!`
- `mypy cmig`
  - exit 0: `Success: no issues found in 78 source files`
- `cmig golden verify-envelope`
  - exit 0: all 17 existing workflow kinds `[OK]`, float-normalization probe
    `[OK]`, and `envelope serialization unchanged for 17 workflow kinds`.
- No git command, dependency sync, remote operation, or QtWebEngine invocation
  was performed. The owned test set is non-GUI; the common brief's sandbox GUI
  limitation therefore did not block this track.

## Proposed CHANGELOG entries

### Added

- Add a frozen, validated `StatsConfig` with deterministic provenance for group
  methods, FDR, seed, dimensionality reduction, and clustering.
- Add a seeded, fail-closed sweep-feature embedding pipeline producing tidy PCA/
  UMAP, KMeans, and explained-variance tables with explicit input basis and seed.
- Add volcano-data preparation from per-feature group comparisons with validated
  BH/BY adjusted p-values.

### Changed

- PCA, KMeans, and UMAP helpers now accept and record caller-provided seeds.
- UMAP now rejects `n_neighbors >= n_samples` instead of silently reducing the
  requested neighbor count. This is an intentional honesty change: the result
  can no longer claim the configured neighborhood when a different one ran.
- FDR correction now fails clearly on unsupported methods or invalid p-values.

## Integration notes and risks

### Exact `stats-sweep` CLI proposal for its owner

Do not translate active dimred/clustering into ad-hoc calls. Construct one
`StatsConfig` and pass its seed and nested values to `run_embedding_pipeline`.
Proposed additive flags:

- `--group GROUP` (repeatable; default is all values discovered on the existing
  `--group-axis`; preserve the selected order in `StatsConfig.groups`)
- `--method {robust,parametric}` (repeatable; default `robust`)
- `--fdr-method {fdr_bh,fdr_by}` (default `fdr_bh`)
- `--seed INT` (default `0`; use `StatsConfig` validation)
- `--feature METRIC` (repeatable; selects the metrics pivoted into numeric
  feature columns)
- `--dimred {none,pca,umap}` (default `none`)
- `--n-components INT` (default `2`; relevant to PCA/UMAP)
- `--umap-neighbors INT` (default `15`; relevant only to UMAP)
- `--clustering {none,kmeans}` (default `none`)
- `--kmeans-k INT` (default `2`; relevant only to KMeans)

For any active dimred/clustering, retain the current joint requirement for
`--replicate-column` plus `--confirm-independent-replicates`. Build the wide
feature table with exactly one row per configured group × confirmed replicate,
using the current `--replicate-aggregate` rule before pivoting selected metrics.
Do not mark deterministic condition IDs as independent observations. A missing
group/metric or incomplete pivot cell must fail before the core pipeline rather
than impute a number without a declared basis.

Proposed additive artifacts under `--out`:

- `stats_embedding.parquet`
- `stats_clusters.parquet`
- `stats_explained_variance.parquet` (PCA only)
- `stats_volcano.parquet` (when per-feature inference completed)
- extend `stats_sweep_summary.json` with `stats_config`, input-feature metadata,
  artifact names, and either `completed` or the exact pipeline gate reason.

Do not emit empty placeholder parquet files after a gate refusal; the summary's
named status/reason should be the authoritative disclosure.

### Exact workflow-manifest proposal for the manifest owner

Add two component vocabulary entries, `source_sweep_checksum` and `stats_spec`,
then add a `stats_sweep` workflow kind with the ordered determining components:

```text
workflow_kind
cmig_core_version
dependency_versions
source_sweep_checksum
stats_spec
```

`stats_spec` is exactly `StatsConfig.as_provenance()`. `source_sweep_checksum`
must hash the input sweep artifact bytes (and, if feature-table construction is
materialized separately, its bytes too under a documented composite record).
The dependency record must include the actually imported numpy/scipy,
statsmodels, scikit-learn, and umap-learn versions because numerical identity is
not promised across library versions. This is a new additive workflow kind and
must use the owner-controlled generator/envelope evolution; it must not change
the frozen 11-component solve `run_hash`.

### Figure-writer handoff

Matplotlib/R owners can consume `prepare_volcano_data` directly: x is
`effect_size`, y is `neg_log10_adjusted_pvalue`, and captions/legends must carry
`effect_name` plus `fdr_method`. Embedding plots should pivot
`embedding_table.component/value`; cluster color comes from `cluster_table`, and
PCA captions can cite `explained_variance_table`. Cluster integer IDs are stable
for the same input/config/locked dependencies but are categorical labels, not an
ordered biological quantity.

### Risks

- Repeatability is tested byte-for-value within the current locked environment;
  sklearn/UMAP numerical outputs are not asserted portable across dependency
  versions or architectures. The proposed manifest dependency component is
  therefore required for honest comparison.
- The generic row adapter expects a wide table. CLI wiring must aggregate and
  pivot the long sweep store first and must surface missing feature cells rather
  than silently filling them.
- PCA may be mathematically seed-invariant for a selected solver/data shape; the
  configured seed is still recorded. UMAP exercises the random-state path and
  the tests establish both same-seed identity and a different-seed coordinate
  change on the owned fixture.

## Proposals deliberately not implemented

- No CLI/parser/output changes: `cmig/cli/main.py` is V1-owned.
- No workflow kind, component vocabulary, golden Python/JSON, or envelope
  re-bless: all are V1-owned and the existing 17-kind gate remains unchanged.
- No matplotlib, R, GUI, documentation, README, CHANGELOG, or skill edits; those
  surfaces are coordinator/other-owner handoffs.
- No dependency or lockfile changes.
- No imputation, scaling/standardization policy, batch correction, advanced
  cohort modeling, or cross-version embedding equivalence claim was introduced;
  each needs an explicit scientific policy and provenance before implementation.
