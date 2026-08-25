"""Statistics 5b/5c — seeded, gated dimensionality reduction and clustering.

The low-level PCA, KMeans, and UMAP helpers remain available, while
``run_embedding_pipeline`` is the wire-ready entry point for a sweep-derived
feature table. The pipeline emits tidy rows only after its interpretability
gates pass; a refusal carries a stable machine-readable reason.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any

from cmig.core.stats import ClusteringConfig, DimredConfig, StatsConfig

_MAX_RANDOM_SEED = 2**32 - 1
_INFERRED_FEATURE_EXCLUSIONS = {
    "cache_hit",
    "diagnostic",
    "metric",
    "pvalue",
    "run_hash",
    "schema_version",
    "status",
}


@dataclass(frozen=True)
class EmbedResult:
    method: str
    coords: Any
    explained_variance: list[float] | None = None
    seed: int = 0


@dataclass(frozen=True)
class StatsFeatureTable:
    """Numeric observation-by-feature input plus interpretation metadata."""

    observation_ids: tuple[str, ...]
    feature_names: tuple[str, ...]
    values: Any
    groups: tuple[str, ...]
    independent_replicates: bool = False

    def __post_init__(self) -> None:
        observation_ids = tuple(self.observation_ids)
        feature_names = tuple(self.feature_names)
        groups = tuple(self.groups)
        if not isinstance(self.independent_replicates, bool):
            raise ValueError("independent_replicates must be a boolean confirmation")
        if not observation_ids:
            raise ValueError("feature table must contain at least one observation")
        if len(observation_ids) != len(groups):
            raise ValueError("feature table groups must have one value per observation")
        if any(
            not isinstance(item, str) or not item.strip() for item in observation_ids
        ):
            raise ValueError("feature table observation IDs must be non-empty strings")
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("feature table observation IDs must be unique")
        if not feature_names or any(
            not isinstance(item, str) or not item.strip() for item in feature_names
        ):
            raise ValueError("feature table feature names must be non-empty strings")
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("feature table feature names must be unique")
        if any(not isinstance(item, str) or not item.strip() for item in groups):
            raise ValueError("feature table groups must be non-empty strings")
        object.__setattr__(self, "observation_ids", observation_ids)
        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "groups", groups)


@dataclass(frozen=True)
class EmbeddingPipelineResult:
    """Tidy output tables and the exact configuration/input provenance."""

    embedding_table: tuple[dict[str, object], ...]
    cluster_table: tuple[dict[str, object], ...]
    explained_variance_table: tuple[dict[str, object], ...]
    provenance: dict[str, object]

    @property
    def embedding(self) -> tuple[dict[str, object], ...]:
        return self.embedding_table

    @property
    def clusters(self) -> tuple[dict[str, object], ...]:
        return self.cluster_table


class StatsEmbeddingGateError(ValueError):
    """A fail-closed embedding decision with a stable reason identifier."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def _validate_seed(seed: int) -> None:
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed <= _MAX_RANDOM_SEED
    ):
        raise ValueError(f"seed must be an integer between 0 and {_MAX_RANDOM_SEED}")


def _numeric_matrix(matrix: Any) -> Any:
    import numpy as np

    try:
        values = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("embedding input matrix must contain only numeric values") from error
    if values.ndim != 2:
        raise ValueError("embedding input matrix must be 2-dimensional")
    n_samples, n_features = int(values.shape[0]), int(values.shape[1])
    if n_samples < 1 or n_features < 1:
        raise ValueError("embedding input matrix must have at least one sample and one feature")
    if not bool(np.isfinite(values).all()):
        raise ValueError("embedding input matrix must contain only finite values")
    return values


def _matrix_shape(matrix: Any) -> tuple[int, int]:
    values = _numeric_matrix(matrix)
    return int(values.shape[0]), int(values.shape[1])


def pca_embed(matrix: Any, *, n_components: int = 2, seed: int = 0) -> EmbedResult:
    """Run seeded PCA and return coordinates plus explained-variance ratios."""
    from sklearn.decomposition import PCA

    _validate_seed(seed)
    values = _numeric_matrix(matrix)
    n_samples, n_features = int(values.shape[0]), int(values.shape[1])
    if (
        isinstance(n_components, bool)
        or not isinstance(n_components, int)
        or n_components < 1
        or n_components > min(n_samples, n_features)
    ):
        raise ValueError(
            "PCA n_components must be between 1 and min(n_samples, n_features)"
        )
    reducer = PCA(n_components=n_components, random_state=seed)
    coords = reducer.fit_transform(values)
    return EmbedResult(
        "pca",
        coords,
        [float(value) for value in reducer.explained_variance_ratio_],
        seed,
    )


def kmeans_cluster(matrix: Any, *, k: int, seed: int = 0) -> list[int]:
    """Run seeded KMeans and return one integer label per observation."""
    import numpy as np
    from sklearn.cluster import KMeans

    _validate_seed(seed)
    values = _numeric_matrix(matrix)
    n_samples = int(values.shape[0])
    if isinstance(k, bool) or not isinstance(k, int) or k < 1 or k > n_samples:
        raise ValueError("KMeans k must be between 1 and n_samples")
    if len(np.unique(values, axis=0)) < k:
        raise ValueError("KMeans k cannot exceed the number of distinct observations")
    model = KMeans(n_clusters=k, random_state=seed, n_init=10)
    return [int(label) for label in model.fit_predict(values)]


def umap_embed(
    matrix: Any,
    *,
    n_components: int = 2,
    n_neighbors: int = 15,
    seed: int = 0,
) -> EmbedResult:
    """Run seeded UMAP without silently clamping an invalid neighbor count."""
    import umap

    _validate_seed(seed)
    values = _numeric_matrix(matrix)
    n_samples, n_features = int(values.shape[0]), int(values.shape[1])
    if n_samples < 3:
        raise ValueError("UMAP requires at least 3 samples")
    if (
        isinstance(n_components, bool)
        or not isinstance(n_components, int)
        or n_components < 1
        or n_components > min(n_samples, n_features)
    ):
        raise ValueError(
            "UMAP n_components must be between 1 and min(n_samples, n_features)"
        )
    if (
        isinstance(n_neighbors, bool)
        or not isinstance(n_neighbors, int)
        or n_neighbors < 2
    ):
        raise ValueError("UMAP n_neighbors must be an integer >= 2")
    if n_neighbors >= n_samples:
        raise ValueError("UMAP n_neighbors must be less than n_samples")
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        random_state=seed,
        transform_seed=seed,
        n_jobs=1,
        init="random",
    )
    return EmbedResult("umap", reducer.fit_transform(values), None, seed)


def _rows_from_table(feature_table: Any) -> list[Mapping[str, object]]:
    if hasattr(feature_table, "to_pylist"):
        raw_rows = feature_table.to_pylist()
    elif hasattr(feature_table, "to_dict"):
        raw_rows = feature_table.to_dict(orient="records")
    else:
        raw_rows = feature_table
    if isinstance(raw_rows, (str, bytes)) or not isinstance(raw_rows, Sequence):
        raise ValueError("feature table must be a sequence of row mappings")
    rows = list(raw_rows)
    if not rows or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("feature table must contain at least one row mapping")
    return rows


def feature_table_from_rows(
    rows: Any,
    *,
    observation_column: str = "condition_id",
    group_column: str = "group",
    feature_columns: Sequence[str] | None = None,
    independent_replicates: bool = False,
) -> StatsFeatureTable:
    """Normalize a wide Arrow/pandas/list-of-mappings feature table."""
    row_mappings = _rows_from_table(rows)
    if not isinstance(independent_replicates, bool):
        raise ValueError("independent_replicates must be a boolean confirmation")
    if feature_columns is None:
        excluded = _INFERRED_FEATURE_EXCLUSIONS | {observation_column, group_column}
        candidates = set(row_mappings[0]) - excluded
        features = tuple(sorted(
            name
            for name in candidates
            if all(
                name in row
                and isinstance(row[name], Real)
                and not isinstance(row[name], bool)
                for row in row_mappings
            )
        ))
    else:
        if isinstance(feature_columns, str):
            raise ValueError("feature_columns must be a sequence, not a string")
        features = tuple(feature_columns)
    if not features:
        raise ValueError("feature table has no numeric feature columns")
    if len(features) != len(set(features)):
        raise ValueError("feature_columns must not contain duplicates")

    observation_ids: list[str] = []
    groups: list[str] = []
    matrix: list[list[float]] = []
    for row_index, row in enumerate(row_mappings):
        if observation_column not in row or not str(row[observation_column]).strip():
            raise ValueError(
                f"feature table row {row_index} is missing non-empty {observation_column!r}"
            )
        if group_column not in row or not str(row[group_column]).strip():
            raise ValueError(
                f"feature table row {row_index} is missing non-empty {group_column!r}"
            )
        values: list[float] = []
        for feature in features:
            try:
                raw_value = row[feature]
                if isinstance(raw_value, bool):
                    raise TypeError
                value = float(raw_value)  # type: ignore[arg-type]
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"feature table row {row_index} has non-numeric feature {feature!r}"
                ) from error
            if not math.isfinite(value):
                raise ValueError(
                    f"feature table row {row_index} has non-finite feature {feature!r}"
                )
            values.append(value)
        observation_ids.append(str(row[observation_column]))
        groups.append(str(row[group_column]))
        matrix.append(values)
    return StatsFeatureTable(
        tuple(observation_ids),
        features,
        matrix,
        tuple(groups),
        independent_replicates,
    )


def _refuse(reason: str, detail: str) -> None:
    raise StatsEmbeddingGateError(reason, detail)


def run_embedding_pipeline(
    feature_table: Any,
    config: StatsConfig,
    *,
    observation_column: str = "condition_id",
    group_column: str = "group",
    feature_columns: Sequence[str] | None = None,
    independent_replicates: bool | None = None,
) -> EmbeddingPipelineResult:
    """Apply configured dimensionality reduction/clustering to a feature table.

    Only configured groups are analyzed. Activating PCA, UMAP, or KMeans requires
    an explicit independent-replicate confirmation. This deliberately rejects a
    deterministic parameter sweep as inferential cohort data.
    """
    import numpy as np

    if not isinstance(config, StatsConfig):
        raise TypeError("config must be a StatsConfig")
    if independent_replicates is not None and not isinstance(independent_replicates, bool):
        raise ValueError("independent_replicates must be a boolean confirmation")
    if isinstance(feature_table, StatsFeatureTable):
        normalized = feature_table
    else:
        normalized = feature_table_from_rows(
            feature_table,
            observation_column=observation_column,
            group_column=group_column,
            feature_columns=feature_columns,
            independent_replicates=bool(independent_replicates),
        )
    confirmed_independent = (
        normalized.independent_replicates
        if independent_replicates is None
        else independent_replicates
    )

    configured_groups = set(config.groups)
    selected = [
        index for index, group in enumerate(normalized.groups) if group in configured_groups
    ]
    present_groups = {normalized.groups[index] for index in selected}
    missing_groups = [group for group in config.groups if group not in present_groups]
    if missing_groups:
        raise ValueError(f"feature table is missing configured groups: {missing_groups}")
    values = _numeric_matrix(normalized.values)[selected, :]
    observation_ids = tuple(normalized.observation_ids[index] for index in selected)
    groups = tuple(normalized.groups[index] for index in selected)
    n_observations, n_features = int(values.shape[0]), int(values.shape[1])

    dimred = config.dimred
    clustering = config.clustering
    assert isinstance(dimred, DimredConfig)
    assert isinstance(clustering, ClusteringConfig)
    analysis_requested = dimred.method != "none" or clustering.method != "none"
    if analysis_requested and not confirmed_independent:
        _refuse(
            "not_run_no_independent_replicates",
            "deterministic sweep conditions are pseudo-replicates; explicitly confirm "
            "independent replicates before embedding or clustering",
        )
    if dimred.method != "none" and n_observations < dimred.n_components:
        _refuse(
            "not_run_observations_fewer_than_components",
            f"observations={n_observations}, components={dimred.n_components}",
        )
    if dimred.method != "none" and n_features < dimred.n_components:
        _refuse(
            "not_run_features_fewer_than_components",
            f"features={n_features}, components={dimred.n_components}",
        )
    if dimred.method == "umap" and n_observations < 3:
        _refuse(
            "not_run_umap_requires_three_observations",
            f"UMAP requires at least 3 observations; got {n_observations}",
        )
    if dimred.method == "umap" and dimred.n_neighbors >= n_observations:
        _refuse(
            "not_run_umap_neighbors_exceed_observations",
            f"n_neighbors={dimred.n_neighbors} must be less than observations={n_observations}",
        )
    if clustering.method == "kmeans" and clustering.k > n_observations:
        _refuse(
            "not_run_clusters_exceed_observations",
            f"k={clustering.k}, observations={n_observations}",
        )
    if clustering.method == "kmeans" and len(np.unique(values, axis=0)) < clustering.k:
        _refuse(
            "not_run_clusters_exceed_distinct_observations",
            f"k={clustering.k} exceeds the number of distinct observations",
        )

    embedding_rows: list[dict[str, object]] = []
    variance_rows: list[dict[str, object]] = []
    cluster_basis = "features"
    clustering_values = values
    if dimred.method == "pca":
        embedded = pca_embed(
            values, n_components=dimred.n_components, seed=config.seed
        )
        component_prefix = "PC"
    elif dimred.method == "umap":
        embedded = umap_embed(
            values,
            n_components=dimred.n_components,
            n_neighbors=dimred.n_neighbors,
            seed=config.seed,
        )
        component_prefix = "UMAP"
    else:
        embedded = None
        component_prefix = ""

    if embedded is not None:
        cluster_basis = embedded.method
        clustering_values = embedded.coords
        for row_index, (observation_id, group) in enumerate(
            zip(observation_ids, groups, strict=True)
        ):
            for component_index in range(dimred.n_components):
                embedding_rows.append({
                    "observation_id": observation_id,
                    "group": group,
                    "method": embedded.method,
                    "component": f"{component_prefix}{component_index + 1}",
                    "value": float(embedded.coords[row_index, component_index]),
                    "seed": config.seed,
                })
        for component_index, ratio in enumerate(embedded.explained_variance or []):
            variance_rows.append({
                "method": embedded.method,
                "component": f"{component_prefix}{component_index + 1}",
                "explained_variance_ratio": float(ratio),
                "seed": config.seed,
            })

    cluster_rows: list[dict[str, object]] = []
    if clustering.method == "kmeans":
        labels = kmeans_cluster(
            clustering_values, k=clustering.k, seed=config.seed
        )
        for observation_id, group, label in zip(
            observation_ids, groups, labels, strict=True
        ):
            cluster_rows.append({
                "observation_id": observation_id,
                "group": group,
                "method": "kmeans",
                "cluster": label,
                "k": clustering.k,
                "basis": cluster_basis,
                "seed": config.seed,
            })

    provenance = config.as_provenance()
    provenance["input"] = {
        "observation_count": n_observations,
        "feature_columns": list(normalized.feature_names),
        "independent_replicates_confirmed": confirmed_independent,
    }
    return EmbeddingPipelineResult(
        tuple(embedding_rows),
        tuple(cluster_rows),
        tuple(variance_rows),
        provenance,
    )


# Concise aliases for callers and future CLI wiring.
embedding_pipeline = run_embedding_pipeline
StatsEmbeddingResult = EmbeddingPipelineResult
